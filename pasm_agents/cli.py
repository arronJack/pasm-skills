"""``pasm-agents`` 命令行：让产品智能体可一行启动、可检视。

命令
----

``pasm-agents demo npc``         30 秒预置剧本 NPC 演示
``pasm-agents demo companion``   老人陪伴（含危机识别）
``pasm-agents demo tutor``       学习陪伴

``pasm-agents run npc --id=xxx --persona-file=personas/herbalist.json``
       加载/创建指定 NPC，进入交互式命令行（输入 quit 退出并 save）

``pasm-agents inspect <id>``     打印某 agent 的当前快照
``pasm-agents list``             列出本机全部 agent
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_persona(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"persona file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _print(obj: Any) -> None:
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(obj)


# ============================================================ demos


def demo_npc() -> int:
    from .npc import NpcAgent
    npc = NpcAgent(agent_id="demo_herbalist", persona={
        "name": "陈伯", "role": "河边摆摊的草药老头",
        "temper": 0.55, "energy": 0.40, "play": 0.30,
        "tone": "慢悠悠、爱讲道理",
    })
    print(f"[init] {npc!r}  tier={npc.tier}")
    npc.observe("玩家第一次来买跌打药", salience=5,
                tags=["玩家", "第一次", "救命"], category="重大")
    print(f"[observe] written 5-star episode; memory={npc._core.counts() if hasattr(npc._core, 'counts') else 'n/a'}")
    print(f"[act] {npc.act()}")
    print(f"[chat 问名字] {npc.chat('你叫什么')}")
    print(f"[chat 买药] {npc.chat('有跌打药吗')}")
    npc.feedback("praise", action="talk")
    print(f"[feedback praise/talk] weights={npc._core._weights if not npc._core_ok else 'core'}")
    npc.save()
    print(f"[save] -> {npc.persist_dir}")
    print("[ok] demo_npc")
    return 0


def demo_companion() -> int:
    from .companion import ElderlyCompanion
    c = ElderlyCompanion(agent_id="demo_chenxiulan", persona={
        "name": "陈秀兰", "age": 78, "city": "深圳",
        "tone": "慢、温和",
        "key_facts": [
            {"label": "用药", "content": "每天早 8 点吃降压药络活喜 5mg"},
            {"label": "过敏", "content": "青霉素过敏"},
            {"label": "家人", "content": "女儿在深圳，每周日下午来电话"},
            {"label": "本人", "content": "78 岁，独居，腿脚不便"},
        ],
        "emergency_contact": {"name": "女儿小敏", "phone": "13900000000"},
        "medication_schedule": [{"name": "络活喜", "dose": "5mg", "hour": 8}],
    })
    print(f"[init] {c!r}")
    print(f"[chat 我吃什么药] {c.chat('我吃什么药')}")
    print(f"[chat 我叫什么] {c.chat('我叫什么名字')}")
    print(f"[detect crisis 摔倒] {c.detect_crisis('我在卫生间滑倒了')}")
    esc = c.escalate("卫生间滑倒")
    print(f"[escalate] -> {_print_dict(esc)}")
    c.save()
    print("[ok] demo_companion")
    return 0


def demo_tutor() -> int:
    from .tutor import LearningTutor
    t = LearningTutor(agent_id="demo_xiaoya", persona={
        "name": "小雅", "grade": "五年级",
        "tone": "温柔、耐心",
    })
    print(f"[init] {t!r}")
    t.report("分数加减", 0.4)
    t.report("分数加减", 0.6)
    t.report("面积计算", 0.9)
    print(f"[state] {t.state.notes['knowledge_state']}")
    print(f"[pick_next] {t.pick_next()}")
    print(f"[chat 难] {t.chat('分数加减好难')}")
    print(f"[chat 哪里差] {t.chat('我哪里不行')}")
    t.save()
    print("[ok] demo_tutor")
    return 0


def _print_dict(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False)


# ============================================================ run / inspect / list


def run_agent(agent_kind: str, agent_id: str, persona_file: Optional[str]) -> int:
    persona = _load_persona(persona_file)
    cls = _kind_to_class(agent_kind)
    if cls is None:
        raise SystemExit(f"unknown agent kind: {agent_kind}")
    agent = cls(agent_id=agent_id, persona=persona)
    print(f"[ready] {agent!r}  tier={agent.tier}")
    print("(输入内容直接对话；'act' 看动作；'mood' 看情绪；'quit' 退出并 save)")
    try:
        while True:
            line = input(f"{agent.persona.get('name','agent')}> ").strip()
            if not line:
                continue
            if line in ("quit", "exit", ":q"):
                break
            if line == "act":
                print("  ", agent.act()); continue
            if line == "mood":
                print("  ", round(agent.mood, 3)); continue
            if line.startswith("observe "):
                # 简化：observe 后面整行作为 title
                agent.observe(line[8:].strip(), salience=2); continue
            if line.startswith("feedback "):
                # feedback praise talk
                parts = line.split()
                if len(parts) >= 2:
                    agent.feedback(parts[1], action=parts[2] if len(parts) >= 3 else None)
                continue
            print(" ", agent.chat(line))
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        agent.save()
        print(f"[saved] {agent.persist_dir}")
    return 0


def inspect_agent(agent_id: str) -> int:
    """通过直接读盘展示快照（不实例化，避免副作用）。"""
    persist_dir = Path.home() / ".pasm-agents" / agent_id
    sf = persist_dir / "agent_state.json"
    if not sf.exists():
        raise SystemExit(f"no agent_state.json at {sf}")
    data = json.loads(sf.read_text(encoding="utf-8"))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def list_agents() -> int:
    root = Path.home() / ".pasm-agents"
    if not root.exists():
        print("(no .pasm-agents directory yet)")
        return 0
    rows = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        sf = d / "agent_state.json"
        if not sf.exists():
            continue
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            st = data.get("state", {})
            rows.append({
                "id": data.get("agent_id"),
                "class": data.get("agent_class"),
                "tier": data.get("tier"),
                "interactions": st.get("total_interactions", 0),
                "last_active": st.get("last_active", 0),
                "saved_at": data.get("saved_at", 0),
            })
        except Exception:
            rows.append({"id": d.name, "error": "state.json unreadable"})
    _print(rows)
    return 0


def _kind_to_class(kind: str):
    if kind == "npc":
        from .npc import NpcAgent
        return NpcAgent
    if kind in ("companion", "elderly"):
        from .companion import ElderlyCompanion
        return ElderlyCompanion
    if kind == "tutor":
        from .tutor import LearningTutor
        return LearningTutor
    return None


# ============================================================ main


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="pasm-agents", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="跑预设剧本")
    demo.add_argument("kind", choices=["npc", "companion", "tutor"])

    run = sub.add_parser("run", help="启动一个 agent 进入交互模式")
    run.add_argument("kind", choices=["npc", "companion", "tutor"])
    run.add_argument("--id", required=True)
    run.add_argument("--persona-file", default=None)

    sub.add_parser("list", help="列出本机全部 agent")
    insp = sub.add_parser("inspect", help="查看 agent 快照")
    insp.add_argument("id")

    args = ap.parse_args(argv)
    if args.cmd == "demo":
        return {"npc": demo_npc, "companion": demo_companion, "tutor": demo_tutor}[args.kind]()
    if args.cmd == "run":
        return run_agent(args.kind, args.id, args.persona_file)
    if args.cmd == "list":
        return list_agents()
    if args.cmd == "inspect":
        return inspect_agent(args.id)
    return 1


if __name__ == "__main__":
    sys.exit(main())