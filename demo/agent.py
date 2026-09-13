"""学习陪伴智能体「小墨」—— 用 pasm-skills SDK 写出来的**完整**产品智能体。

它是 demo 各 step 演变到最后的样子：会记忆、被夸更爱讲、有情绪、能跟踪学情、
随成长解锁新动作。可以直接 import 拿去用：

    from demo.agent import StudyBuddy
    b = StudyBuddy(agent_id="xiaoming", persona={"name": "小墨", "temper": 0.6})
    print(b.chat("我今天分数加减又错了"))
    print(b.snapshot())

从源码直接跑（没 pip install 时）：本文件会自动把仓根加进 sys.path。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# 从源码直接跑时用：把仓根加进 sys.path，才能 import pasm_skills
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_skills.sdk import BaseAgent  # noqa: E402


class StudyBuddy(BaseAgent):
    """会记住学生弱点、被夸更爱讲、有情绪、能跟踪学情、随成长解锁动作。"""

    #: 成长阶段 → 动作池（阶段越高，可做的越多）
    ACTS = {
        0: ["greet", "teach", "peek", "rest"],
        1: ["greet", "teach", "peek", "rest", "quiz", "give"],
        2: ["greet", "teach", "peek", "rest", "quiz", "give", "report"],
    }

    # -------------------------------------------------- 必填钩子 1：能做什么
    def action_pool(self) -> List[str]:
        stage = min(self.state.growth_stage, max(self.ACTS))
        return list(self.ACTS[stage])

    # -------------------------------------------------- 必填钩子 2：怎么回
    def _render_reply(self, text, facts, mood) -> str:
        name = self.persona.get("name", "小墨")
        low = mood < -0.2
        pre = "（打起精神）" if low else ""
        if facts:
            top = facts[0]
            return f"{pre}{name}：我记得你说过「{top.get('title', '')}」，我们再练练？"
        if low:
            return f"{name}：（有点累）……这道题我们慢慢来，不急。"
        return f"{name}：好呀，你想先攻克哪个知识点？"

    # -------------------------------------------------- 可选钩子：首次初始记忆
    def bootstrap_event(self) -> List[Dict[str, Any]]:
        return [{"title": "今天开始当你的学习小老师", "tags": ["开学"],
                 "salience": 3, "category": "里程碑"}]

    # -------------------------------------------------- 学情跟踪（结构化状态）
    def report(self, topic: str, score: float) -> Dict[str, Any]:
        """记录一次做题结果，用 EMA 平滑更新掌握度，并写进记忆。"""
        ks = self.state.notes.setdefault("knowledge_state", {})
        prev = ks.get(topic, 0.0)
        ks[topic] = round(prev * 0.7 + score * 0.3, 3)
        # 关键学情用 salience=4，容量触顶不会被日常挤掉
        self.observe(f"【学情】{topic} 掌握度 {ks[topic]}",
                     brief=f"最新一次 {score}", tags=["学情", topic],
                     salience=4, category="学情")
        return {"topic": topic, "new_mastery": ks[topic]}

    def mastery(self, topic: str) -> float:
        return (self.state.notes.get("knowledge_state") or {}).get(topic, 0.0)

    def pick_next(self) -> str:
        """最弱优先（带 20% 抖动防刷同一题）。"""
        import random
        ks = self.state.notes.get("knowledge_state") or {}
        if not ks:
            return "先随便聊聊，你最近在学什么？"
        items = sorted(ks.items(), key=lambda kv: kv[1])
        weakest = items[: max(1, len(items) // 3)]
        return weakest[0][0] if random.random() < 0.8 else random.choice(list(ks))[0]

    def snapshot(self) -> Dict[str, Any]:
        """给外部一个稳定的机读出口（别让调用方读 state.notes）。"""
        ks = self.state.notes.get("knowledge_state") or {}
        return {
            "mastery": ks,
            "weakest": min(ks, key=ks.get) if ks else None,
            "average": round(sum(ks.values()) / len(ks), 3) if ks else 0.0,
            "tier": self.tier,
            "growth_stage": self.state.growth_stage,
        }
