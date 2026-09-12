"""parity-guard —— 跨仓漂移守门。

由来（真实事故）：符号推理层 / 记忆路由 / 向量检索曾经**只落在 Studio 桌面端**，
核心包 `pasm/cognitive/` 从未包含，导致"只有 pasm-qclaw 实现了"。
这个智能体就是那类事故的守门人：核心仓与 Studio 仓的认知层必须逐字一致。

方向是**单向的**：核心是单一真相源 ⇒ 核心有、Studio 缺 = FAIL（桌面会掉功能）；
Studio 有、核心缺 = WARN（正是上面那类事故的前兆）。
"""
from __future__ import annotations

from .. import checks
from ..agent import Agent, register


@register
class ParityGuardAgent(Agent):
    """核心仓 vs Studio 仓 `pasm/cognitive/` 逐字一致性守门。

    用法：
        python -m pasm_skills run parity-guard
    """

    name = "parity-guard"
    goal = "防「只在 Studio 实现、核心没落盘」——认知层两仓必须逐字一致"
    needs = ("core", "studio")

    def run(self):
        checks.check_parity(self)
        return None
