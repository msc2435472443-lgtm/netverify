"""校验用例目录。用法：

    python -m netverify.validate cases/

退出码：0 = 全部通过，1 = 有用例不合法。

这个命令是这个项目的第一道闸门：agent 生成一批用例后，先跑它，
坏的那些会被连编号带原因打印出来，agent 拿着错误信息重写。
"""

from __future__ import annotations

import sys
from pathlib import Path

from .case import CaseError, load_cases


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0]) if args else Path("cases")

    if not root.exists():
        print(f"目录不存在：{root}", file=sys.stderr)
        return 1

    paths = sorted(root.glob("*.json"))
    if not paths:
        print(f"{root} 里没有 .json 用例文件", file=sys.stderr)
        return 1

    print(f"找到 {len(paths)} 个用例文件，开始校验\n")

    ok = 0
    failed = 0
    for p in paths:
        try:
            cases = load_cases([p])
        except CaseError as exc:
            failed += 1
            print(f"✗ {p.name}")
            print(f"    {exc.code}: {exc.message}\n")
            continue

        case = cases[0]
        ok += 1
        print(f"✓ {p.name}  ({case.id}) {case.title}")
        print(f"    {len(case.steps)} 步 / {len(case.assertions)} 条断言")

    print(f"\n通过 {ok} 个，失败 {failed} 个")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
