"""内置智能体集合。

导入本包即完成注册（`agent.register` 装饰器在导入时生效）。
新增智能体：在本目录放一个 `.py`，用 `@register` 装饰类，然后在下面 import 一次。
"""
from __future__ import annotations

from . import core_verifier, parity_guard, regression   # noqa: F401

__all__ = ["core_verifier", "parity_guard", "regression"]
