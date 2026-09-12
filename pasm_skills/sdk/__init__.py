"""pasm_skills.sdk —— 写 PASM 产品智能体的底座。

这一层只做一件事：**让"记忆 / 情绪 / 动作 / 反馈 / 持久化"开箱可用**，
写智能体的人只需要关心三件事 —— persona、动作池、回复模板。

```python
from pasm_skills.sdk import BaseAgent

class TeaHouseOwner(BaseAgent):
    def action_pool(self):
        return ["greet", "brew", "gossip", "rest"]

    def _render_reply(self, text, facts, mood):
        return "……"

a = TeaHouseOwner(agent_id="owner", persona={"name": "王掌柜"})
a.observe("客人夸茶好", salience=3)
print(a.act(), a.chat("生意怎么样"), a.mood)
a.save()
```

档位（`agent.tier`）如实反映当前跑在哪一层，**降级永不隐藏**：

| tier | 含义 |
|---|---|
| `bionic` | 完整 PASM 核心 + emotion 模块（需 torch） |
| `core`   | PASM 核心（`memory_layers` + `learning`，不需要 torch） |
| `light`  | 纯内置实现（重要度淘汰 + 字面检索 + 性格/反馈加权） |

> 两个档位走**同一套语义**：性格基线（天生偏好）+ 学习权重（反馈塑形）。
> 具体智能体见独立仓 `pasm-agents`。
"""
from __future__ import annotations

from .base import (  # noqa: F401
    BaseAgent,
    AgentState,
    _core_available,
    _now,
    _torch_available,
)

__all__ = [
    "BaseAgent", "AgentState",
    "_core_available", "_now", "_torch_available",
]
