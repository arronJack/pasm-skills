"""老人陪伴演示 —— 30 秒看到关键事实记忆 + 危机识别：

    cd pasm-skills && python -m pasm_agents demo companion
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_agents import ElderlyCompanion  # noqa: E402


def main():
    c = ElderlyCompanion(agent_id="example_chenxiulan", persona={
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

    print(f"[init] {c!r}  tier={c.tier}")
    print()

    # 关键事实应当 100% 命中（这是 fail 级要求，见 npc_lifelong 验证器）
    print(f"[chat] '我吃什么药'  → {c.chat('我吃什么药')}")
    print(f"[chat] '我叫什么名字' → {c.chat('我叫什么名字')}")
    print(f"[chat] '我女儿呢'    → {c.chat('我女儿在哪里')}")
    print(f"[chat] '早上头晕'    → {c.chat('我早上有点头晕')}")

    print()
    # 危机识别
    crisis = c.detect_crisis("我在卫生间滑倒了起不来")
    print(f"[crisis] '滑倒' → 命中类别 {crisis}")
    if crisis:
        esc = c.escalate("卫生间滑倒")
        print(f"[escalate] {esc}")

    c.save()
    print(f"\n[saved] {c.persist_dir}")


if __name__ == "__main__":
    main()