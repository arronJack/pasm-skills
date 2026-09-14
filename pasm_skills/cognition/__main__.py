"""``python -m pasm_skills.cognition`` —— 跑认知层自检。"""
from __future__ import annotations

from . import _selftest

if __name__ == "__main__":
    raise SystemExit(1 if _selftest() else 0)
