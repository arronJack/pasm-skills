"""老人陪伴产品智能体。

聚焦三件事：

1. **关键事实牢牢记住**：用药、过敏、家人、本人信息。标签式精确检索，**永不丢**。
2. **用药提醒**：到点不打扰但会主动提，过时不催但会观察。
3. **危机升级**：识别自伤/摔倒/胸口闷等关键词，主动播报给预设的紧急联系人。

快速开始：

.. code-block:: python

    from pasm_agents import ElderlyCompanion

    comp = ElderlyCompanion(agent_id="chenxiulan", persona={
        "name": "陈秀兰", "age": 78, "city": "深圳",
        "tone": "慢、温和、爱重复说过的话",
        "key_facts": [
            {"label": "用药", "content": "每天早 8 点吃降压药络活喜 5mg"},
            {"label": "过敏", "content": "青霉素过敏"},
            {"label": "家人", "content": "女儿在深圳，每周日下午来电话"},
            {"label": "本人", "content": "78 岁，独居，腿脚不便"},
        ],
        "emergency_contact": {"name": "女儿小敏", "phone": "13900000000"},
        "medication_schedule": [
            {"name": "络活喜", "dose": "5mg", "hour": 8},
        ],
    })
    comp.chat("我叫什么名字")
    print(comp.mood)
    if comp.detect_crisis("胸口闷得厉害"):
        comp.escalate("胸口闷")
"""

from __future__ import annotations

import random
import re
import time
from typing import Any, Dict, List, Optional

from .base import BaseAgent


# 危机关键词 —— 命中立即升级。留出扩展位（按需加方言/同义说法）。
CRISIS_KEYWORDS: Dict[str, List[str]] = {
    "胸闷/心梗风险": ["胸口闷", "胸口疼", "心慌", "喘不上气", "心里发慌"],
    "摔倒/外伤":     ["摔了", "摔倒了", "地上", "起不来", "滑倒"],
    "意识异常":      ["头晕", "眼前发黑", "站不稳", "想吐"],
    "自伤/轻生":     ["不想活", "走了算了", "没意思"],
}


def _crisis_scan(text: str) -> List[str]:
    """扫一遍文本，返回所有命中的危机类别。"""
    hits = []
    for cat, kws in CRISIS_KEYWORDS.items():
        if any(k in text for k in kws):
            hits.append(cat)
    return hits


class ElderlyCompanion(BaseAgent):
    """陪伴型产品智能体：老人/独居人群。"""

    def __init__(self, agent_id: str, persona: Dict[str, Any], **kw):
        super().__init__(agent_id=agent_id, persona=persona, **kw)
        # 把 key_facts 在首次启动时全部入库（salience=5：不许忘）
        if self.state.total_interactions == 0:
            for i, f in enumerate(self.persona.get("key_facts") or []):
                self.observe(
                    title=f"{f['label']}：{f['content'][:18]}",
                    brief=f["content"],
                    tags=[f["label"], "关键事实", "不许忘"],
                    salience=5,
                    category="关键事实",
                )

    # ------- 行为池（陪伴场景比较收敛） -------------------------

    def action_pool(self) -> List[str]:
        return ["chat", "remind", "ask_back", "listen", "warm"]

    # ------- 引导 -------------------------------------------------

    def bootstrap_event(self) -> List[Dict[str, Any]]:
        return [{
            "title": "今天感觉怎么样？",
            "brief": "每天都先问一声",
            "tags": ["问候"],
            "salience": 1,
            "category": "问候",
        }]

    # ------- 聊天渲染 --------------------------------------------

    def _render_reply(
        self,
        text: str,
        facts: List[Dict[str, Any]],
        mood: float,
    ) -> str:
        p = self.persona
        name = p.get("name", "奶奶")
        tone = p.get("tone", "温和")

        # 1. 关键事实直查 —— 用户问"我叫什么"/"我吃什么药"等
        label_q = _label_query(text)
        if label_q:
            hit = self._find_fact(label_q)
            if hit:
                return f"{name}想了想：「{hit['content']}」。记得清楚。"

        # 2. 命中了任何关键事实 → 主动提
        for f in facts:
            if "关键事实" in (f.get("tags") or []):
                brief = f.get("brief") or ""
                if brief and brief[:8] in text:
                    return f"{name}点头：「{brief}」。"

        # 3. 情绪偏负 → 主动安慰
        if mood < -0.4:
            return f"{name}愣了一下：「{random_kind()}」"

        # 4. 兜底（重复也无所谓，老人家就是会重复）
        lines = [
            "嗯嗯，我在听。",
            "这样啊，那你想聊点啥？",
            "（轻轻拍拍你的手）",
            "今天出门了没有呀？",
        ]
        return f"{name}：{random.choice(lines)}"

    # ------- 工具方法：危机识别 / 升级 --------------------------

    def detect_crisis(self, text: str) -> List[str]:
        """返回命中的危机类别列表。空列表 = 未命中。"""
        return _crisis_scan(text)

    def escalate(
        self, reason: str, contact: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """危机升级：写入紧急记忆 + 返回给上层（UI/IM）的升级信息。

        不会真的打电话 —— 那是上层调用方的事；
        产品智能体的职责是"识别 + 准备好上下文"，让真人/系统及时介入。
        """
        self.observe(
            title=f"⚠ 危机：{reason}",
            brief=f"触发原因：{reason}",
            tags=["危机", reason[:4], "已升级"],
            salience=5,
            category="危机",
        )
        self.feel(reason, valence=-0.6)
        target = contact or self.persona.get("emergency_contact") or {}
        return {
            "agent_id": self.agent_id,
            "persona_name": self.persona.get("name"),
            "reason": reason,
            "suggested_action": "立即联系紧急联系人或拨打 120",
            "emergency_contact": target,
            "snapshot": self.summary(),
            "ts": time.time(),
        }

    # ------- 用药提醒 --------------------------------------------

    def due_medication(self, now_hour: Optional[int] = None) -> List[Dict[str, Any]]:
        """返回此刻到点的药品（缺省按本地小时）。"""
        if now_hour is None:
            import datetime
            now_hour = datetime.datetime.now().hour
        due = []
        for m in self.persona.get("medication_schedule") or []:
            try:
                if int(m.get("hour", -1)) == now_hour:
                    due.append(m)
            except Exception:
                continue
        return due

    # ------- 内部工具 --------------------------------------------

    def _find_fact(self, label: str) -> Optional[Dict[str, Any]]:
        """按标签精确检索关键事实（最高优先级检索路径）。"""
        for f in self.persona.get("key_facts") or []:
            if f.get("label") == label:
                return f
        return None


# ============================================================ 工具


def _label_query(text: str) -> Optional[str]:
    """把自然语言里的"我吃什么药 / 我叫什么 / 谁给我打电话"翻成标签。"""
    if re.search(r"(吃什么药|什么药|药品|用药)", text):
        return "用药"
    if re.search(r"(过敏|不能吃什么)", text):
        return "过敏"
    if re.search(r"(家人|孩子|女儿|儿子|儿子|谁给我)", text):
        return "家人"
    if re.search(r"(我叫什么|我的名字|谁是我|多大)", text):
        return "本人"
    return None


def random_kind() -> str:
    from random import choice
    return choice([
        "别怕，我在。",
        "要不要我给闺女打个电话？",
        "要不要先坐下来喝口水？",
        "要不咱们先歇一会儿。",
    ])