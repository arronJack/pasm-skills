"""PASM 产品智能体：以 PASM 引擎为基座的可装载、可记忆、可对话的智能体。

包内三个开箱即用的产品：

- :class:`NpcAgent`            游戏 NPC（河边草药老头、市集算命师、酒馆老板娘……）
- :class:`ElderlyCompanion`    老人陪伴（用药提醒、危机升级、关键事实记忆）
- :class:`LearningTutor`       学习陪伴（薄弱点定位、巩固计划、进度跟踪）

每一个都基于同一个 :class:`BaseAgent` 实现，差异只在 persona、行为池和聊天模板。

快速上手：

.. code-block:: python

    from pasm_agents import NpcAgent

    npc = NpcAgent(agent_id="herbalist", persona={
        "name": "陈伯",
        "role": "河边摆摊的草药老头",
        "temper": 0.55, "energy": 0.40, "play": 0.30,
    })
    npc.observe("玩家来买药", salience=3)
    print(npc.act())         # -> "wave" / "talk" / "peek" 等
    print(npc.chat("有跌打药吗"))
    npc.save()

数据落盘位置：``~/.pasm-agents/<agent_id>/``。Agent 可被反复加载、上次的状态/记忆自动恢复。
"""

from .base import BaseAgent, AgentState, _now, _core_available, _torch_available
from .npc import NpcAgent, NPC_ACTIONS, NPC_PERSONA_TEMPLATE
from .companion import ElderlyCompanion, CRISIS_KEYWORDS
from .tutor import LearningTutor

__version__ = "0.1.0"
__all__ = [
    "BaseAgent", "AgentState", "NpcAgent", "ElderlyCompanion", "LearningTutor",
    "NPC_ACTIONS", "NPC_PERSONA_TEMPLATE", "CRISIS_KEYWORDS",
    "_core_available", "_torch_available",
]