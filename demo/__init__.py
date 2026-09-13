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
