"""用例（Case）的数据结构与校验。

这一层不碰模型、不碰网络，只做一件事：**判断一份用例草稿是不是「形状正确」**。

为什么要有这一层？因为用例是 agent 生成的。agent 会写出字段名拼错、缺了期望值、
超时是负数、断言引用了不存在的字段这类草稿。如果直接拿去执行，报错会出现在很远的地方
（执行器崩了 / 抓包对比全失败），根本分不清是「设备坏了」还是「用例写错了」。

所以校验放在执行之前，并且错误信息必须能直接告诉写作者「哪一行、缺什么、该怎么改」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


class CaseError(Exception):
    """用例不合法。code 供程序判断，message 供人或 agent 阅读。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------- 常量

#: 支持的协议。加协议时同时要加执行器，所以这里刻意写死。
PROTOCOLS = ("dhcp", "arp", "icmp", "pppoe", "vlan")

#: 支持的步骤动作。
ACTIONS = ("send", "expect")

#: 断言支持的比较方式。
COMPARATORS = ("equals", "matches", "contains", "in_range")

#: 必填字段。
REQUIRED_CASE_FIELDS = ("id", "title", "intent", "steps", "assertions")


# ---------------------------------------------------------------- 数据类


@dataclass
class Step:
    action: str
    proto: str
    type: str | None = None
    timeout_s: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(d: Any, idx: int) -> "Step":
        if not isinstance(d, dict):
            raise CaseError("step_not_object", f"steps[{idx}] 应该是一个对象，实际是 {type(d).__name__}")

        action = d.get("action")
        if action not in ACTIONS:
            raise CaseError(
                "bad_action",
                f"steps[{idx}].action = {action!r} 不合法，只能是 {' / '.join(ACTIONS)}",
            )

        proto = d.get("proto")
        if proto not in PROTOCOLS:
            raise CaseError(
                "bad_proto",
                f"steps[{idx}].proto = {proto!r} 不在支持列表里（{' / '.join(PROTOCOLS)}）",
            )

        timeout = d.get("timeout_s")
        if timeout is not None:
            if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
                raise CaseError("bad_timeout", f"steps[{idx}].timeout_s 必须是数字，实际是 {timeout!r}")
            if timeout <= 0:
                raise CaseError("bad_timeout", f"steps[{idx}].timeout_s 必须大于 0，实际是 {timeout}")

        return Step(action=action, proto=proto, type=d.get("type"), timeout_s=timeout, raw=dict(d))


@dataclass
class Assertion:
    field: str
    comparator: str
    expected: Any

    @staticmethod
    def from_dict(d: Any, idx: int) -> "Assertion":
        if not isinstance(d, dict):
            raise CaseError("assertion_not_object", f"assertions[{idx}] 应该是一个对象")

        name = d.get("field")
        if not isinstance(name, str) or not name.strip():
            raise CaseError(
                "missing_field",
                f'assertions[{idx}] 缺少 field。要写成 tshark 的字段名，例如 "bootp.option.dhcp"',
            )

        # 允许 {"field": ..., "equals": ...} 这种简写，比较方式从键名推断。
        given = [k for k in COMPARATORS if k in d]
        if not given:
            raise CaseError(
                "missing_comparator",
                f"assertions[{idx}]（field={name}）没有任何比较方式，必须是 {' / '.join(COMPARATORS)} 之一",
            )
        if len(given) > 1:
            raise CaseError(
                "ambiguous_comparator",
                f"assertions[{idx}]（field={name}）同时给了 {given}，一条断言只能有一个比较方式",
            )

        comparator = given[0]
        expected = d[comparator]
        if comparator == "equals" and expected is None:
            raise CaseError("bad_expected", f"assertions[{idx}]（field={name}）的 equals 值是 null")

        return Assertion(field=name, comparator=comparator, expected=expected)


@dataclass
class Case:
    id: str
    title: str
    intent: str
    steps: list[Step]
    assertions: list[Assertion]
    tags: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Any) -> "Case":
        if not isinstance(d, dict):
            raise CaseError("case_not_object", "用例根节点必须是一个对象")

        missing = [k for k in REQUIRED_CASE_FIELDS if k not in d]
        if missing:
            raise CaseError("missing_case_fields", f"用例缺少必填字段：{missing}")

        case_id = d["id"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise CaseError("bad_id", f"id 必须是非空字符串，实际是 {case_id!r}")

        for name in ("title", "intent"):
            value = d[name]
            if not isinstance(value, str) or not value.strip():
                raise CaseError("empty_text", f"{name} 必须是非空字符串，实际是 {value!r}")

        steps_raw = d["steps"]
        if not isinstance(steps_raw, list) or not steps_raw:
            raise CaseError("no_steps", "steps 必须是非空列表——一条用例至少要做一件事")

        asserts_raw = d["assertions"]
        if not isinstance(asserts_raw, list) or not asserts_raw:
            raise CaseError(
                "no_assertions",
                "assertions 必须是非空列表——没有断言的用例只能证明「跑完了」，不能证明「跑对了」",
            )

        steps = [Step.from_dict(s, i) for i, s in enumerate(steps_raw)]
        assertions = [Assertion.from_dict(a, i) for i, a in enumerate(asserts_raw)]

        tags = d.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            raise CaseError("bad_tags", "tags 必须是字符串列表")

        case = Case(
            id=case_id.strip(),
            title=d["title"].strip(),
            intent=d["intent"].strip(),
            steps=steps,
            assertions=assertions,
            tags=list(tags),
        )
        case._check_semantics()
        return case

    def _check_semantics(self) -> None:
        """形状对了之后，再查「意思对不对」。这一层是执行器会踩的坑。"""
        has_send = any(s.action == "send" for s in self.steps)
        has_expect = any(s.action == "expect" for s in self.steps)

        if not has_send:
            raise CaseError(
                "no_send",
                "用例里没有任何 send 步骤——只期待收到包、却不主动发，只有在监听被动流量时才有意义",
            )
        if not has_expect:
            raise CaseError(
                "no_expect",
                "用例里没有任何 expect 步骤——发了包却不检查收到什么，这个用例永远会通过",
            )

        # expect 必须说清等多久。缺了它，执行器要么用默认值（可能太短，误判成设备不回包），
        # 要么无限等（用例卡死）。这个决定不该由执行器的默认值替用例作者做。
        for i, s in enumerate(self.steps):
            if s.action == "expect" and s.timeout_s is None:
                raise CaseError(
                    "missing_timeout",
                    f"steps[{i}] 是 expect，但没有写 timeout_s。"
                    f"必须明确「等多久算超时」（例如 5），否则执行器只能替你猜",
                )

        # send 必须在 expect 之前，否则期待的是「还没发出去的回包」。
        first_send = min(i for i, s in enumerate(self.steps) if s.action == "send")
        first_expect = min(i for i, s in enumerate(self.steps) if s.action == "expect")
        if first_expect < first_send:
            raise CaseError(
                "expect_before_send",
                f"steps[{first_expect}] 是 expect，但它之前没有 send。"
                f"第一个 send 在 steps[{first_send}]——顺序反了",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "intent": self.intent,
            "tags": self.tags,
            "steps": [s.raw for s in self.steps],
            "assertions": [
                {"field": a.field, a.comparator: a.expected} for a in self.assertions
            ],
        }


# ---------------------------------------------------------------- 载入


def load_case(path: str | Path) -> Case:
    """从磁盘读一条用例。v0.1 用 JSON 承载，v0.2 再加 YAML。"""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise CaseError("io_error", f"读不到文件 {p}：{exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CaseError("bad_json", f"{p.name} 不是合法 JSON：{exc.msg}（第 {exc.lineno} 行第 {exc.colno} 列）") from exc

    return Case.from_dict(data)


def load_cases(paths: Iterable[str | Path]) -> list[Case]:
    """批量载入。一条坏用例就整体失败——不做静默跳过。

    静默跳过会让「12 条用例通过」这句话失去意义：你可能以为跑了 12 条，
    实际只有 4 条被载入，8 条写错了但没人知道。
    """
    cases = [load_case(p) for p in paths]
    seen: dict[str, str] = {}
    for c in cases:
        if c.id in seen:
            raise CaseError("duplicate_id", f"用例 id {c.id!r} 重复出现了两次")
        seen[c.id] = c.id
    return cases


def validate(data: Any) -> list[str]:
    """给 agent 用的宽松入口：返回错误列表，而不是抛异常。

    agent 需要「失败的形状」，直接抛异常它会拿不到细节。返回列表让它能逐条改。
    """
    try:
        Case.from_dict(data)
    except CaseError as exc:
        return [f"[{exc.code}] {exc.message}"]
    return []
