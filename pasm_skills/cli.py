"""命令行入口。

    python -m pasm_skills list                      # 智能体清单 + 三仓定位
    python -m pasm_skills repos                     # 只看仓库定位
    python -m pasm_skills run core-verifier         # 跑一个智能体
    python -m pasm_skills run --all                 # 跑全部
    python -m pasm_skills run regression --update   # 刷新事实基线
    python -m pasm_skills selftest                  # 自检（零依赖，随时可跑）

退出码：0 = 全部通过；1 = 有 FAIL；2 = 用法/定位错误。
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
from . import agents as _builtin_agents  # noqa: F401  触发内置智能体注册


def _load_user_agents() -> None:
    """加载 `PASM_SKILLS_PATH` 里用户自带的智能体模块（可选）。"""
    import importlib.util
    import os
    raw = os.environ.get("PASM_SKILLS_PATH", "")
    for entry in [p for p in raw.split(os.pathsep) if p.strip()]:
        p = Path(entry)
        files = [p] if p.is_file() and p.suffix == ".py" else list(p.glob("*.py"))
        for f in files:
            try:
                spec = importlib.util.spec_from_file_location("pasm_skills_user_%s" % f.stem, f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)          # noqa: S301
            except Exception as ex:                   # noqa: BLE001
                print("[WARN] 用户智能体加载失败 %s: %s" % (f, ex), file=sys.stderr)


def _ctx() -> RepoContext:
    return RepoContext()


def cmd_list(args) -> int:
    ctx = _ctx()
    print("PASM Skills v%s" % __version__)
    print()
    print("仓库定位：")
    for key, path in ctx.describe().items():
        flag = "[OK]  " if path else "[MISS]"
        print("  %s %-7s %s" % (flag, key, path or "未找到（可用 %s 指定）" % REPO_SPEC[key][0]))
    print()
    print("可用智能体 %d 个：" % len(names()))
    for item in catalog():
        print("  · %-14s %s" % (item["name"], item["goal"]))
        if item["needs"]:
            print("    %-14s 需要仓库：%s" % ("", ", ".join(item["needs"])))
    return 0


def cmd_repos(args) -> int:
    ctx = _ctx()
    print(json.dumps(ctx.describe(), ensure_ascii=False, indent=2))
    return 0


def cmd_run(args) -> int:
    ctx = _ctx()
    targets: List[str] = names() if args.all else list(args.agents or [])
    if not targets:
        print("请指定智能体名，或用 --all。可用：%s" % ", ".join(names()))
        return 2

    options = {"update": bool(args.update), "baseline": args.baseline}
    results = []
    for name in targets:
        if name not in AGENTS:
            print("[FAIL] 未知智能体 %s" % name, file=sys.stderr)
            return 2
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
    p = argparse.ArgumentParser(prog="pasm_skills",
                                description="PASM 智能体工坊 —— 对核心内容做长期验证")
    p.add_argument("--version", action="version", version="pasm-skills %s" % __version__)
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出智能体与仓库定位").set_defaults(func=cmd_list)
    sub.add_parser("repos", help="只打印仓库定位").set_defaults(func=cmd_repos)
    sub.add_parser("selftest", help="框架自检").set_defaults(func=cmd_selftest)

    r = sub.add_parser("run", help="运行智能体")
    r.add_argument("agents", nargs="*", help="智能体名（可多个）")
    r.add_argument("--all", action="store_true", help="运行全部智能体")
    r.add_argument("--json", action="store_true", help="输出 JSON")
    r.add_argument("--out", default="", help="把 JSON 结论写到文件")
    r.add_argument("--quiet", action="store_true", help="只显示非 OK 结论")
    r.add_argument("--baseline", default="", help="regression：基线名（默认 core）")
    r.add_argument("--update", action="store_true", help="regression：刷新基线")
    r.set_defaults(func=cmd_run)
    return p


def main(argv: List[str] | None = None) -> int:
    _load_user_agents()
    args = build_parser().parse_args(argv)
    if not getattr(args, "cmd", None):
        build_parser().print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
