"""校验命令的测试：重点是退出码。

CI 靠退出码判断成败，所以 0/1 这两个数字本身就是契约，必须测。
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from netverify.validate import main


def write_case(root: Path, name: str, data: dict) -> Path:
    p = root / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


GOOD = {
    "id": "a-1",
    "title": "标题",
    "intent": "意图",
    "steps": [
        {"action": "send", "proto": "dhcp"},
        {"action": "expect", "proto": "dhcp", "timeout_s": 3},
    ],
    "assertions": [{"field": "x", "equals": 1}],
}


def run_cli(path: str) -> tuple[int, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([path])
    return code, out.getvalue() + err.getvalue()


class TestValidateCli(unittest.TestCase):
    def test_all_good_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(3):
                write_case(root, f"c{i}.json", {**GOOD, "id": f"a-{i}"})
            code, text = run_cli(tmp)
            self.assertEqual(code, 0)
            self.assertIn("通过 3 个", text)

    def test_one_bad_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_case(root, "good.json", GOOD)
            write_case(root, "bad.json", {**GOOD, "id": "a-2", "assertions": []})
            code, text = run_cli(tmp)
            self.assertEqual(code, 1)
            self.assertIn("✗", text)
            self.assertIn("no_assertions", text)

    def test_missing_dir_exits_one(self):
        code, text = run_cli("根本不存在的目录")
        self.assertEqual(code, 1)
        self.assertIn("不存在", text)

    def test_empty_dir_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = run_cli(tmp)
            self.assertEqual(code, 1)
            self.assertIn("没有", text)

    def test_bad_file_reported_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_case(root, "good.json", GOOD)
            (root / "broken.json").write_text("{,,}", encoding="utf-8")
            code, text = run_cli(tmp)
            self.assertEqual(code, 1)
            self.assertIn("bad_json", text)
            # 一个坏文件不能带崩整批：好文件仍要被统计
            self.assertIn("通过 1 个", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
