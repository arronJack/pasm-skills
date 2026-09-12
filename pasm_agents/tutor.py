"""学习陪伴产品智能体。

直连 PASM 的"知识强化量"（``LearningEngine.learn(action, delta)``），
能做到：

- **薄弱点定位**：从 ``knowledge_state`` 找分最低的知识点
- **自适应选题**：每次 ``pick_next()`` 返回接下来该练的知识点
- **进度跟踪**：错题入库 salience=3，便于复盘
- **鼓励**式回复：温和、不贬低、给出具体下一步

快速开始：

.. code-block:: python

    from pasm_agents import LearningTutor

    t = LearningTutor(agent_id="xiaoya", persona={
        "name": "小雅", "grade": "五年级",
        "tone": "温柔、耐心、偶尔讲个数学家笑话",
        "topics": ["分数加减", "面积计算", "行程问题", "鸡兔同笼", "质因数分解"],
    })
    t.report("分数加减", score=0.7)        # 答对 70%
    print(t.pick_next())                    # -> "面积计算"（最弱）
    print(t.chat("分数加减好难"))
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .base import BaseAgent


# 默认 6 个五年级知识点（可由 persona.topics 覆盖）
DEFAULT_TOPICS: List[str] = [
    "分数加减", "面积计算", "行程问题", "鸡兔同笼", "质因数分解", "图形对称",
]


class LearningTutor(BaseAgent):
    """学习陪伴产品智能体。"""

    def __init__(self, agent_id: str, persona: Dict[str, Any], **kw):
        # 合并默认
        p = dict(persona or {})
        p.setdefault("topics", list(p.get("topics") or DEFAULT_TOPICS))
        p.setdefault("tone", "温柔、耐心")
        super().__init__(agent_id=agent_id, persona=p, **kw)
        # 初始化 knowledge_state
        if "knowledge_state" not in self.state.notes:
            self.state.notes["knowledge_state"] = {t: 0.0 for t in p["topics"]}
            self.state.notes["history"] = []

    # ------- 行为池 -----------------------------------------------

    def action_pool(self) -> List[str]:
        return ["ask", "explain", "encourage", "drill", "review"]

    # ------- 引导 -------------------------------------------------

    def bootstrap_event(self) -> List[Dict[str, Any]]:
        return [{
            "title": f"我陪{self.persona.get('name','你')}学数学",
            "brief": "今天也要加油哦",
            "tags": ["陪伴", "学习"],
            "salience": 1,
            "category": "陪伴",
        }]

    # ------- 学情报告 --------------------------------------------

    def report(self, topic: str, score: float) -> Dict[str, Any]:
        """学生报告一次作答（``score`` ∈ [0, 1]）。"""
        score = max(0.0, min(1.0, float(score)))
        ks = self.state.notes.setdefault("knowledge_state", {})
        if topic not in ks:
            ks[topic] = 0.0
        # EMA 平滑
        prev = ks[topic]
        ks[topic] = round(prev * 0.7 + score * 0.3, 3)
        # 写入历史 + 记忆（错题 salience 高）
        hist = self.state.notes.setdefault("history", [])
        hist.append({"topic": topic, "score": score, "ts": time.time()})
        if len(hist) > 200:
            self.state.notes["history"] = hist[-200:]
        salience = 3 if score < 0.6 else 2
        self.observe(
            title=f"{topic} 答对 {int(score*100)}%",
            brief=f"得分 {score:.2f}",
            tags=[topic, "错题" if score < 0.6 else "进步"],
            salience=salience,
            category="错题" if score < 0.6 else "进步",
        )
        # 直接驱动学习层（如果可用）
        if self._core_ok and hasattr(self._core, "learn_topic"):
            try:
                self._core.learn_topic(topic, delta=score - 0.5)
            except Exception:
                pass
        return {"topic": topic, "new_mastery": ks[topic]}

    def pick_next(self) -> str:
        """挑下一题要练的知识点（最弱优先 + 抖动）。"""
        ks = self.state.notes.get("knowledge_state") or {}
        if not ks:
            return random.choice(self.persona["topics"])
        # 80% 概率选最弱，20% 随机防刷
        if random.random() < 0.8:
            return min(ks, key=ks.get)
        return random.choice(list(ks))

    # ------- 聊天渲染 --------------------------------------------

    def _render_reply(
        self,
        text: str,
        facts: List[Dict[str, Any]],
        mood: float,
    ) -> str:
        p = self.persona
        name = p.get("name", "你")
        tone = p.get("tone", "温柔")
        weakest = self.pick_next()
        ks = self.state.notes.get("knowledge_state") or {}
        wm = ks.get(weakest, 0)

        # 学生在抱怨 → 先安抚 + 给个具体下一步
        if any(k in text for k in ("难", "不会", "搞不懂", "烦")):
            return (
                f"别急，{name}～咱们一点点来。"
                f"要不今天先做 3 道「{weakest}」？"
                f"（{weakest} 当前掌握度 {int(wm*100)}%）"
            )

        # 学生说"懂了/会了" → 鼓励 + 推荐巩固
        if any(k in text for k in ("懂了", "会了", "明白了", "OK")):
            return f"太棒了！要不要再练两道「{weakest}」巩固一下？"

        # 学生问"我哪里不行" → 直接说最弱项
        if any(k in text for k in ("哪里不行", "哪里差", "最弱", "短板")):
            return f"从最近记录看，**{weakest}** 还需要多练（{int(wm*100)}%）。"

        # 默认
        return (
            f"好的，咱们接着来。"
            f"今天聚焦「{weakest}」怎么样？"
        )


import time  # noqa: E402  末尾 import 仅为控制 IDE 顺序