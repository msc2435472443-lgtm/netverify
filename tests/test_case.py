"""case.py 的测试。

原则：**错误路径必须显式测**。正常用例通过是应该的，写错的用例被拦住才是这一层的价值。
每条错误测试都断言 code，不只断言「抛了异常」——code 是给 agent 看的，它决定重写方向。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from netverify.case import Case, CaseError, load_case, load_cases, validate


def good_dict(**over) -> dict:
    """一条形状正确的最小用例，供各测试覆盖单个字段。"""
    base = {
        "id": "dhcp-001",
        "title": "DHCP 四步握手完整性",
        "intent": "客户端应能在 30 秒内通过 DHCP 获得地址",
        "steps": [
            {"action": "send", "proto": "dhcp", "type": "DISCOVER"},
            {"action": "expect", "proto": "dhcp", "type": "OFFER", "timeout_s": 5},
        ],
        "assertions": [{"field": "bootp.option.dhcp", "equals": 2}],
    }
    base.update(over)
    return base


class TestHappyPath(unittest.TestCase):
    def test_minimal_case_loads(self):
        c = Case.from_dict(good_dict())
        self.assertEqual(c.id, "dhcp-001")
        self.assertEqual(len(c.steps), 2)
        self.assertEqual(c.assertions[0].comparator, "equals")

    def test_roundtrip(self):
        c = Case.from_dict(good_dict())
        again = Case.from_dict(c.to_dict())
        self.assertEqual(again.to_dict(), c.to_dict())

    def test_all_comparators(self):
        for comp, val in [
            ("equals", 2),
            ("matches", r"^192\.168\."),
            ("contains", "OFFER"),
            ("in_range", [0, 100]),
        ]:
            with self.subTest(comparator=comp):
                d = good_dict(assertions=[{"field": "bootp.yiaddr", comp: val}])
                c = Case.from_dict(d)
                self.assertEqual(c.assertions[0].comparator, comp)

    def test_strip_whitespace(self):
        c = Case.from_dict(good_dict(id="  dhcp-001  ", title="  标题  "))
        self.assertEqual(c.id, "dhcp-001")
        self.assertEqual(c.title, "标题")

    def test_optional_tags(self):
        c = Case.from_dict(good_dict(tags=["dhcp", "smoke"]))
        self.assertEqual(c.tags, ["dhcp", "smoke"])
        self.assertEqual(Case.from_dict(good_dict()).tags, [])


class TestRootShape(unittest.TestCase):
    def test_not_object(self):
        for bad in (None, [], "x", 42):
            with self.subTest(value=bad):
                with self.assertRaises(CaseError) as ctx:
                    Case.from_dict(bad)
                self.assertEqual(ctx.exception.code, "case_not_object")

    def test_missing_fields(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict({"id": "a"})
        self.assertEqual(ctx.exception.code, "missing_case_fields")
        # 错误信息必须点名缺了哪些字段，否则 agent 只能瞎猜
        for name in ("title", "intent", "steps", "assertions"):
            self.assertIn(name, ctx.exception.message)

    def test_bad_id(self):
        for bad in ("", "   ", 123, None):
            with self.subTest(value=bad):
                with self.assertRaises(CaseError) as ctx:
                    Case.from_dict(good_dict(id=bad))
                self.assertEqual(ctx.exception.code, "bad_id")

    def test_empty_title_or_intent(self):
        for name in ("title", "intent"):
            with self.subTest(field=name):
                with self.assertRaises(CaseError) as ctx:
                    Case.from_dict(good_dict(**{name: "  "}))
                self.assertEqual(ctx.exception.code, "empty_text")

    def test_bad_tags(self):
        for bad in ("dhcp", [1, 2], [None]):
            with self.subTest(value=bad):
                with self.assertRaises(CaseError) as ctx:
                    Case.from_dict(good_dict(tags=bad))
                self.assertEqual(ctx.exception.code, "bad_tags")


class TestSteps(unittest.TestCase):
    def test_not_object(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(steps=["send dhcp"]))
        self.assertEqual(ctx.exception.code, "step_not_object")
        self.assertIn("steps[0]", ctx.exception.message)

    def test_bad_action(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(steps=[{"action": "发送", "proto": "dhcp"}]))
        self.assertEqual(ctx.exception.code, "bad_action")

    def test_bad_proto(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(
                good_dict(steps=[{"action": "send", "proto": "smtp"},
                             {"action": "expect", "proto": "dhcp"}])
            )
        self.assertEqual(ctx.exception.code, "bad_proto")
        self.assertIn("smtp", ctx.exception.message)

    def test_bad_timeout(self):
        # 注意：timeout_s 缺省（None）不是「坏值」，而是「没写」——那是另一条错误
        # missing_timeout，见 TestSemantics.test_expect_needs_timeout
        for bad in ("5", True, 0, -1):
            with self.subTest(value=bad):
                steps = [
                    {"action": "send", "proto": "dhcp"},
                    {"action": "expect", "proto": "dhcp", "timeout_s": bad},
                ]
                with self.assertRaises(CaseError) as ctx:
                    Case.from_dict(good_dict(steps=steps))
                self.assertEqual(ctx.exception.code, "bad_timeout")

    def test_no_steps(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(steps=[]))
        self.assertEqual(ctx.exception.code, "no_steps")


class TestAssertions(unittest.TestCase):
    def test_no_assertions(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(assertions=[]))
        self.assertEqual(ctx.exception.code, "no_assertions")
        # 这条错误信息的措辞要解释「为什么必须有」，不然 agent 会想办法绕过
        self.assertIn("跑对了", ctx.exception.message)

    def test_missing_field(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(assertions=[{"equals": 2}]))
        self.assertEqual(ctx.exception.code, "missing_field")
        self.assertIn("bootp.option.dhcp", ctx.exception.message)

    def test_blank_field(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(assertions=[{"field": "   ", "equals": 2}]))
        self.assertEqual(ctx.exception.code, "missing_field")

    def test_missing_comparator(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(assertions=[{"field": "bootp.option.dhcp"}]))
        self.assertEqual(ctx.exception.code, "missing_comparator")

    def test_ambiguous_comparator(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(
                good_dict(assertions=[{"field": "x", "equals": 1, "contains": "y"}])
            )
        self.assertEqual(ctx.exception.code, "ambiguous_comparator")

    def test_null_equals(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(assertions=[{"field": "x", "equals": None}]))
        self.assertEqual(ctx.exception.code, "bad_expected")

    def test_assertion_not_object(self):
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(assertions=["bootp.option.dhcp == 2"]))
        self.assertEqual(ctx.exception.code, "assertion_not_object")


class TestSemantics(unittest.TestCase):
    def test_no_send(self):
        steps = [{"action": "expect", "proto": "dhcp", "type": "OFFER"}]
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(steps=steps))
        self.assertEqual(ctx.exception.code, "no_send")

    def test_no_expect(self):
        steps = [{"action": "send", "proto": "dhcp", "type": "DISCOVER"}]
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(steps=steps))
        self.assertEqual(ctx.exception.code, "no_expect")
        # 这条是四个语义检查里最重要的一条：没有 expect 的用例永远通过
        self.assertIn("永远会通过", ctx.exception.message)

    def test_expect_before_send(self):
        steps = [
            {"action": "expect", "proto": "dhcp", "type": "OFFER", "timeout_s": 5},
            {"action": "send", "proto": "dhcp", "type": "DISCOVER"},
        ]
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(steps=steps))
        self.assertEqual(ctx.exception.code, "expect_before_send")
        self.assertIn("steps[0]", ctx.exception.message)

    def test_expect_needs_timeout(self):
        """expect 不写 timeout_s 会被拦住——但不许让执行器替用例作者猜。"""
        steps = [
            {"action": "send", "proto": "dhcp", "type": "DISCOVER"},
            {"action": "expect", "proto": "dhcp", "type": "OFFER"},
        ]
        with self.assertRaises(CaseError) as ctx:
            Case.from_dict(good_dict(steps=steps))
        self.assertEqual(ctx.exception.code, "missing_timeout")
        self.assertIn("timeout_s", ctx.exception.message)

    def test_interleaved_is_fine(self):
        # 多个 send/expect 交替是正常的（DHCP 四步就是 DORA 四次一来一回）
        steps = [
            {"action": "send", "proto": "dhcp", "type": "DISCOVER"},
            {"action": "expect", "proto": "dhcp", "type": "OFFER", "timeout_s": 5},
            {"action": "send", "proto": "dhcp", "type": "REQUEST"},
            {"action": "expect", "proto": "dhcp", "type": "ACK", "timeout_s": 5},
        ]
        c = Case.from_dict(good_dict(steps=steps))
        self.assertEqual(len(c.steps), 4)


class TestLoad(unittest.TestCase):
    def test_load_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dhcp-001.json"
            p.write_text(json.dumps(good_dict(), ensure_ascii=False), encoding="utf-8")
            c = load_case(p)
            self.assertEqual(c.id, "dhcp-001")

    def test_missing_file(self):
        with self.assertRaises(CaseError) as ctx:
            load_case("不存在的文件.json")
        self.assertEqual(ctx.exception.code, "io_error")

    def test_bad_json_points_at_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text('{"id": "a",,}', encoding="utf-8")
            with self.assertRaises(CaseError) as ctx:
                load_case(p)
            self.assertEqual(ctx.exception.code, "bad_json")
            self.assertIn("行", ctx.exception.message)

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i in range(2):
                p = Path(tmp) / f"c{i}.json"
                p.write_text(json.dumps(good_dict(), ensure_ascii=False), encoding="utf-8")
                paths.append(p)
            with self.assertRaises(CaseError) as ctx:
                load_cases(paths)
            self.assertEqual(ctx.exception.code, "duplicate_id")

    def test_validate_returns_list_not_raise(self):
        # agent 要的是「失败清单」，不是异常
        self.assertEqual(validate(good_dict()), [])
        errors = validate(good_dict(assertions=[]))
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("[no_assertions]"))

    def test_validate_catches_every_kind(self):
        """validate 对每一种坏输入都返回非空列表，绝不抛异常。"""
        bad_inputs = [
            None,
            {},
            good_dict(assertions=[]),
            good_dict(steps=[]),
            good_dict(id=""),
            good_dict(tags=[1]),
            good_dict(assertions=[{"field": "x"}]),
            good_dict(steps=[{"action": "send", "proto": "smtp"},
                             {"action": "expect", "proto": "dhcp"}]),
        ]
        for bad in bad_inputs:
            with self.subTest(value=bad):
                errors = validate(bad)
                self.assertIsInstance(errors, list)
                self.assertGreaterEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
