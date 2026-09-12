"""core-verifier —— PASM 核心全量体检。

它是"长期验证"的主力：一次运行就把核心包的关键事实全查一遍
（引擎契约 / 认知层是否真的落盘 / 符号闭环接线 / 学习层两档 / 环境插件 / 冒烟），
结论可落 JSON 归档，前后对比即可发现"哪一天悄悄退化了"。
"""
from __future__ import annotations

from .. import checks
from ..agent import Agent, register


@register
class CoreVerifierAgent(Agent):
    """对 PASM 核心做一次全量契约 / 落盘 / 闭环 / 学习层体检。

    用法：
        python -m pasm_skills run core-verifier
        python -m pasm_skills run core-verifier --json
    """

    name = "core-verifier"
    goal = "一次运行查清核心包是否完好：契约、落盘、闭环、学习层、冒烟"
    needs = ("core",)

    def run(self):
        checks.all_checks(self)
        return None
