"""命令行入口。

    python -m pasm_skills list                      # 已发现的智能体 + 三仓定位
    python -m pasm_skills repos                     # 只看仓库定位
    python -m pasm_skills run core-verifier         # 跑一个智能体
    python -m pasm_skills run --all                 # 跑全部（发现的全部）
    python -m pasm_skills run regression --update   # 刷新事实基线
    python -m pasm_skills selftest                  # 自检（零依赖，随时可跑）
    python -m pasm_skills agents                    # 只列出智能体加载来源（排障用）

退出码：0 = 全部通过；1 = 有 FAIL；2 = 用法/定位错误。

**基座不内置智能体**：具体智能体由外部包通过 entry points
（组名 `pasm_skills.agents`）或 `PASM_SKILLS_PATH` / `PASM_SKILLS_AGENT_MODULES` 提供。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from . import __version__
from .agent import AGENTS, catalog, names, run_agent
from .context import REPO_SPEC, RepoContext
from .discovery import ENTRY_POINT_GROUP, load_agents


def _ctx() -> RepoContext:
    return RepoContext()


def cmd_list(args) -> int:
    ctx = _ctx()
    print("PASM Skills v%s（基座）" % __version__)
    print()
    print("仓库定位：")
    for key, path in ctx.describe().items():
        flag = "[OK]  " if path else "[MISS]"
        print("  %s %-7s %s" % (flag, key, path or "未找到（可用 %s 指定）" % REPO_SPEC[key][0]))
    print()
    found = names()
    print("已发现的智能体 %d 个：" % len(found))
    if not found:
        print("  （无）基座不内置智能体。装一个智能体包即可：")
        print("      pip install pasm-agents       # 官方智能体集（NPC / 陪伴 / 教学 / 验证）")
        print("  或指向本地目录：")
        print("      PASM_SKILLS_PATH=/path/to/my_agents python -m pasm_skills list")
    for item in catalog():
        print("  · %-14s %s" % (item["name"], item["goal"]))
        if item["needs"]:
            print("    %-14s 需要仓库：%s" % ("", ", ".join(item["needs"])))
    return 0


def cmd_agents(args) -> int:
    """只报告智能体是从哪儿加载进来的（排障用）。"""
    loaded, _ = load_agents()
    print("entry point 组名：%s" % ENTRY_POINT_GROUP)
    print("已加载 %d 个来源：" % len(loaded))
    for src in loaded:
        print("  · %s" % src)
    print()
    print("注册表中的智能体 %d 个：%s" % (len(names()), ", ".join(names()) or "（无）"))
    return 0


def cmd_repos(args) -> int:
    ctx = _ctx()
    print(json.dumps(ctx.describe(), ensure_ascii=False, indent=2))
    return 0


def _missing(name: str) -> int:
    """智能体找不到时的自救指引。

    这里刻意写得啰嗦。两种最常见的翻车 —— "只装了基座"、
    "照着 2026-09 拆仓前的旧文档去 clone 了基座仓" —— 症状都是"未知智能体"，
    用户却完全看不出发生了什么。一句话指路能省掉一轮求助。
    """
    import difflib

    found = names()
    print("[FAIL] 未知智能体 %s" % name, file=sys.stderr)
    print(file=sys.stderr)
    if not found:
        print("当前发现的智能体数量：0 —— 你只装了基座。", file=sys.stderr)
        print("基座刻意不内置任何智能体，这是正常现象，不是你装错了。", file=sys.stderr)
        print("装上智能体包即可：", file=sys.stderr)
        print("    pip install pasm-agents        # 官方智能体集（NPC / 陪伴 / 教学 / 验证）", file=sys.stderr)
        print("    PASM_SKILLS_PATH=/path/to/dir  # 或指向本地智能体目录", file=sys.stderr)
    else:
        print("当前可用（%d 个）：%s" % (len(found), ", ".join(found)), file=sys.stderr)
        near = difflib.get_close_matches(name, found, n=3, cutoff=0.5)
        if near:
            print("是不是想跑：%s ？" % "  ".join(near), file=sys.stderr)
    print(file=sys.stderr)
    print("排障：python -m pasm_skills agents     # 看智能体是从哪儿加载进来的", file=sys.stderr)
    return 2


def cmd_run(args) -> int:
    ctx = _ctx()
    targets: List[str] = names() if args.all else list(args.agents or [])
    if not targets:
        print("请指定智能体名，或用 --all。可用：%s" % (", ".join(names()) or "（无）"))
        return 2

    options = {"update": bool(args.update), "baseline": args.baseline}
    results = []
    for name in targets:
        if name not in AGENTS:
            return _missing(name)
        res = run_agent(name, ctx, options)
        results.append(res)
        if not args.json:
            print(res.text(verbose=not args.quiet))
            print()

    if args.json or args.out:
        payload = [r.to_dict() for r in results]
        blob = json.dumps(payload if len(payload) > 1 else payload[0],
                          ensure_ascii=False, indent=2)
        if args.out:
            out_path = Path(args.out)
            if out_path.parent and not out_path.parent.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(blob, encoding="utf-8")
            if not args.json:
                print("已写入：%s" % args.out)
        if args.json:
            print(blob)

    return 1 if any(r.worst() == "fail" or r.error for r in results) else 0


def cmd_selftest(args) -> int:
    from . import selftest
    return 0 if selftest() else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pasm-skills",
        description="PASM 智能体基座 —— 写/跑基于 PASM 引擎的智能体（框架、SDK、打包工具）")
    p.add_argument("--version", action="version", version="pasm-skills %s" % __version__)
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出已发现的智能体与仓库定位").set_defaults(func=cmd_list)
    sub.add_parser("agents", help="只报告智能体加载来源（排障）").set_defaults(func=cmd_agents)
    sub.add_parser("repos", help="只打印仓库定位").set_defaults(func=cmd_repos)
    sub.add_parser("selftest", help="框架自检").set_defaults(func=cmd_selftest)

    r = sub.add_parser("run", help="运行智能体")
    r.add_argument("agents", nargs="*", help="智能体名（可多个）")
    r.add_argument("--all", action="store_true", help="运行全部已发现的智能体")
    r.add_argument("--json", action="store_true", help="输出 JSON")
    r.add_argument("--out", default="", help="把 JSON 结论写到文件")
    r.add_argument("--quiet", action="store_true", help="只显示非 OK 结论")
    r.add_argument("--baseline", default="", help="regression：基线名（默认 core）")
    r.add_argument("--update", action="store_true", help="regression：刷新基线")
    r.set_defaults(func=cmd_run)
    return p


def main(argv: List[str] | None = None) -> int:
    load_agents()                       # 先发现外部智能体，再解析参数
    args = build_parser().parse_args(argv)
    if not getattr(args, "cmd", None):
        build_parser().print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
