"""PASM 智能体 Demo 包。

一个**手把手教你从零写出智能体**的分步教程：从只写两个钩子的最小智能体，
一路加记忆、反馈塑形、情绪、学情跟踪、成长解锁，最后演示怎么把它接进真实产品
（CLI / FastAPI / 游戏循环），并给出**真实跑出来的应用效果**。

运行入口：

    python -m demo.run_all          # 一键跑完 6 步 + 汇总效果
    python demo/step_01_minimal.py  # 单步可独立运行

想看「怎么一步步写出来的」，按文件名顺序读 step_01 → step_06；
想看「写出来之后怎么用、效果如何」，读 step_07_apply.py 与本包 README。
"""
from __future__ import annotations

__all__ = []

# 本 demo 教程**钉死**在 SDK 自带的 light 档（use_core=False）：
# 这样无论运行环境有没有装私有 PASM 核心引擎，教程展示的「反馈塑形 / 记忆检索」
# 等应用效果数字都是确定且正确的。私有核心在某些环境下反馈/检索尚有缺陷，
# 不应在教程里把错误行为暴露给学习者。
#
# 注意：这只是 demo 包内的局部行为——它发生在 import demo 时，对 demo 自身进程负责，
# 不会影响把 pasm_skills 当作库使用的其他代码（教程本就是独立运行入口）。
import pasm_skills.sdk.base as _sdk_base

_orig_base_init = _sdk_base.BaseAgent.__init__


def _demo_base_init(self, *args, use_core: bool = False, **kwargs):
    return _orig_base_init(self, *args, use_core=use_core, **kwargs)


_sdk_base.BaseAgent.__init__ = _demo_base_init
