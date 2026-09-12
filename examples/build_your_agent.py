"""从零写一个智能体：一个完整的、可跑的走查（不依赖任何成品智能体）。

运行：
    python examples/build_your_agent.py

它会依次演示 SDK 的全部能力：建智能体 → 写记忆 → 选动作 → 对话 →
反馈塑形 → 情绪 → 落盘恢复 → 档位。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

# 没 pip install 也能直接跑：把仓根加进 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_skills.sdk import BaseAgent  # noqa: E402


# ============================================================ 1. 定义我的智能体

class NightMarketVendor(BaseAgent):
    """夜市摊主：记得住熟客，被夸了更爱招呼人，被凶了就蔫。"""

    #: 阶段 0/1 的动作池 —— 用成长阶段解锁更多动作（这里演示 stage 机制）
    ACTS = {
        0: ["greet", "grill", "peek", "rest"],
        1: ["greet", "grill", "peek", "rest", "dance"],
    }

    def action_pool(self):
        stage = min(self.state.growth_stage, max(self.ACTS))
        return list(self.ACTS[stage])

    def _render_reply(self, text, facts, mood):
        name = self.persona.get("name", "摊主")
        if facts:
            top = facts[0]
            return f"{name}（眼睛一亮）：「{top.get('title', '')}」—— 记得记得！"
        if mood < -0.2:
            return f"{name}：（没什么精神）……要点什么。"
        return f"{name}：「来了您呐，老样子？」"

    def bootstrap_event(self):
        return [{"title": "今晚在老地方支起了摊", "tags": ["夜市"], "salience": 2}]


# ============================================================ 2. 用起来

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pasm-agent-demo-"))
    try:
        print("=== 1. 建一个智能体 ===")
        v = NightMarketVendor(
            agent_id="vendor",
            persona={"name": "老陈", "temper": 0.7, "energy": 0.5, "play": 0.4},
            persist_dir=tmp,
        )
        print("  tier =", v.tier, "（light=纯内置 / core=PASM 核心 / bionic=+情绪模块）")
        print("  首次启动自动写入的初始记忆：",
              [f["title"] for f in v.recall("夜市", k=3)] or "（轻量档下检索按字面匹配）")

        print()
        print("=== 2. 写记忆（重要度决定容不容易被挤掉）===")
        v.observe("小姑娘每周三都来买烤面筋", brief="不要辣", tags=["熟客"],
                  salience=3, category="熟客")
        v.observe("上周帮隔壁摊主挡了一次醉汉", tags=["大事"], salience=5, category="里程碑")
        v.observe("今天下雨，人少")
        print("  recall('面筋') ->", [f["title"] for f in v.recall("面筋", k=3)])

        print()
        print("=== 3. 对话（会带上检索到的记忆 + 当前情绪）===")
        print("  ", v.chat("老板还记得我不"))
        print("  ", v.chat("今天有什么"))

        print()
        print("=== 4. 反馈塑形：夸谁，谁就变多 ===")
        pool = v.action_pool()
        before = {a: 0 for a in pool}
        for _ in range(300):
            before[v.act()] += 1
        for _ in range(40):
            v.feedback("praise", action="grill")     # 夸"烤串"
            v.feedback("scold", action="peek")       # 凶"偷看"
        after = {a: 0 for a in pool}
        for _ in range(300):
            after[v.act()] += 1
        print("  动作   反馈前 → 反馈后")
        for a in pool:
            print("    %-6s %.0f%% → %.0f%%" % (a, before[a] / 3, after[a] / 3))

        print()
        print("=== 5. 情绪 ===")
        print("  mood =", v.mood)
        v.feel("被醉汉掀了摊子", valence=-0.8)
        print("  受了委屈后 mood =", v.mood)
        print("  ", v.chat("老板"))

        print()
        print("=== 6. 落盘 + 换进程恢复 ===")
        v.save()
        print("  落盘目录：", v.persist_dir)
        for f in sorted(Path(v.persist_dir).glob("*.json")):
            print("    %-20s %6d B" % (f.name, f.stat().st_size))
        v2 = NightMarketVendor(agent_id="vendor",
                               persona={"name": "老陈"},
                               persist_dir=tmp)
        print("  新实例恢复后：交互数 =", v2.state.total_interactions,
              "（persona 以本次传入的为准）")

        print()
        print("=== 7. summary() ===")
        print(" ", json.dumps({k: v.summary()[k] for k in
                             ("agent_id", "tier", "total_interactions", "mood", "feedback_count")},
                            ensure_ascii=False))

        print()
        print("=== 8. 成长：解锁新动作 ===")
        print("  阶段 0 动作池：", NightMarketVendor.ACTS[0])
        v.state.growth_stage = 1
        print("  阶段 1 动作池：", v.action_pool())

        print()
        print("全部跑通。下一步：把你的类放进一个包，参考 tools/build_skill.py 打成技能包。")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
