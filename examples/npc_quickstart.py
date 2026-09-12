"""30 秒 NPC 演示 —— 一行命令看到效果：

    cd pasm-skills && python -m pasm_agents demo npc
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_agents import NpcAgent  # noqa: E402


def main():
    npc = NpcAgent(agent_id="example_herbalist", persona={
        "name": "陈伯", "role": "河边摆摊的草药老头",
        "temper": 0.55, "energy": 0.40, "play": 0.30,
        "tone": "慢悠悠、爱讲道理",
    })

    print(f"[init] {npc!r}  tier={npc.tier}  persist={npc.persist_dir}")
    print()

    npc.observe("玩家第一次来买跌打药",
                salience=5, tags=["玩家", "第一次", "救命"], category="重大")
    print(f"[observe] 已写入 5★ 关键记忆 → {npc._core.counts()}")

    print(f"[act]   当前动作 → {npc.act()}")
    print(f"[chat]  '你叫什么' → {npc.chat('你叫什么名字')}")
    print(f"[chat]  '跌打药'  → {npc.chat('有跌打药吗')}")

    npc.feedback("praise", action="talk")
    print(f"[feedback praise/talk] weights={getattr(npc._core, '_weights', 'core-mode')}")

    npc.save()
    print(f"\n[saved] {npc.persist_dir}")
    print("[done] 再跑一次会恢复到刚才的状态 —— 同一个 agent_id 会"接着记"")


if __name__ == "__main__":
    main()