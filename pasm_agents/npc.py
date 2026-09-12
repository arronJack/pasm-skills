"""游戏 NPC 产品智能体。

设定一个角色 + 性格，让它能：

- **记住** 玩家的名字、来过几次、做过什么（持久化）
- **回应** 玩家的对话（基于 persona + 检索 + 情绪，纯模板渲染）
- **做出** 当前阶段解锁的动作（动作池随 ``growth_stage`` 升级）
- **被反馈** 调整行为（夸/戳/训都会改变动作权重）

快速开始：

.. code-block:: python

    from pasm_agents import NpcAgent

    npc = NpcAgent(agent_id="herbalist", persona={
        "name": "陈伯", "role": "河边摆摊的草药老头",
        "temper": 0.55, "energy": 0.40, "play": 0.30,
        "tone": "慢悠悠、爱讲道理、说话带点草药味",
    })
    npc.observe("玩家来买跌打药", salience=3, tags=["玩家"])
    print(npc.act())                 # 'wave'
    print(npc.chat("有跌打药吗"))     # '陈伯笑呵呵……'
    npc.feedback("praise", action="talk")
    npc.save()
"""

from __future__ import annotations

import random
from typing import Any, Dict, List

from .base import BaseAgent


# 动作池随成长阶段解锁 —— 与 pet_behavior.ARCH_META 的阶段思路对齐
# 0: wave / hop / peek
# 1: + ball
# 2: + dance / spin
# 3: + think
NPC_ACTIONS: Dict[int, List[str]] = {
    0: ["wave", "hop", "peek", "talk"],
    1: ["wave", "hop", "peek", "talk", "ball"],
    2: ["wave", "hop", "peek", "talk", "ball", "dance", "spin"],
    3: ["wave", "hop", "peek", "talk", "ball", "dance", "spin", "think"],
}


NPC_PERSONA_TEMPLATE: Dict[str, Any] = {
    "name": "未命名 NPC",
    "role": "村民",
    "temper": 0.5,   # 主动性
    "energy": 0.5,   # 活跃度
    "play":   0.5,   # 俏皮度
    "tone":   "平和",
}


class NpcAgent(BaseAgent):
    """可装载的游戏 NPC。

    persona 必填项：``name``、``role``。其余有合理默认值。
    """

    def __init__(self, agent_id: str, persona: Dict[str, Any], **kw):
        # 用模板补齐缺失键
        merged = dict(NPC_PERSONA_TEMPLATE)
        merged.update(persona or {})
        super().__init__(agent_id=agent_id, persona=merged, **kw)

    # ------- 阶段 / 动作 --------------------------------------------

    def action_pool(self) -> List[str]:
        stage = self.state.growth_stage
        # 不超过表里最大的阶段
        stage = min(stage, max(NPC_ACTIONS))
        return list(NPC_ACTIONS.get(stage, NPC_ACTIONS[0]))

    def grow(self) -> int:
        """升级一档（按交互数自动触发也可手动调）。"""
        if self.state.growth_stage < max(NPC_ACTIONS):
            self.state.growth_stage += 1
        return self.state.growth_stage

    # ------- 引导 ---------------------------------------------------

    def bootstrap_event(self) -> List[Dict[str, Any]]:
        p = self.persona
        return [{
            "title": f"我{'' if p['role'].startswith('是') else '是'}{p['role']}",
            "brief": f"我叫{p['name']}，{p.get('tone','')}。",
            "tags": ["我", p["name"], p["role"]],
            "salience": 3,
            "category": "自我",
        }]

    # ------- 聊天渲染 ----------------------------------------------

    def _render_reply(
        self,
        text: str,
        facts: List[Dict[str, Any]],
        mood: float,
    ) -> str:
        p = self.persona
        name = p["name"]
        role = p["role"]

        # 命中了"自我"标签 → 介绍自己
        if any(k in text for k in ("你叫什么", "你是谁", "你叫啥", "名字")):
            return f"{name}道：{role}，{p.get('tone','')}。"

        # 命中了"第一次遇见玩家"这种重要记忆 → 表达记得
        for f in facts:
            if f.get("sal", 0) >= 4 and any(t in (f.get("tags") or []) for t in ("玩家", "救命", "重大")):
                return f"{name}眯起眼：上次{ f.get('brief','')[:16] }，老朽还记着呢。"

        # 命中任何事 → 提及
        if facts:
            top = facts[0]
            brief = top.get("brief") or top.get("title") or ""
            if brief:
                return f"{name}点头道：{ brief[:24] }，记得。"

        # 情绪温度调节
        if mood > 0.4:
            lead = random.choice([f"{name}笑呵呵", f"{name}热情招呼", f"{name}迎上来"])
        elif mood < -0.3:
            lead = random.choice([f"{name}皱眉", f"{name}没好气地", f"{name}冷冷"])
        else:
            lead = random.choice([f"{name}应声", f"{name}抬头看", f"{name}慢悠悠答"])

        # 兜底句
        defaults = [
            f"……这事{role}我也说不准。",
            f"你问这个啊，让我想想……",
            f"（摆摆手）下次再说吧。",
        ]
        return f"{lead}：" + random.choice(defaults)