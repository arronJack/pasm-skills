"""第 4 步：加情绪 —— mood 会被传进 `_render_reply`，同一句话高兴/生气说得不一样。

运行：
    python demo/step_04_emotion.py

  * `a.mood` 是**属性**（写 `a.mood`，别写 `a.mood()`），取值范围 [-1, 1]
  * `a.feel(event, valence)` 注入一次情绪事件（valence ∈ [-1, 1]）
  * 有 torch 时接真人格模块（tier=bionic），否则用内置回退 —— 接口完全一致
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_skills.sdk import BaseAgent  # noqa: E402


class StudyBuddy(BaseAgent):
    def action_pool(self):
        return ["greet", "teach", "peek", "rest"]

    def _render_reply(self, text, facts, mood):
        name = self.persona.get("name", "小墨")
        if mood < -0.2:
            return f"{name}：（有点累）这道题我们慢慢来，不急。"
        return f"{name}：好呀，我们继续！"


def run() -> None:
    a = StudyBuddy(agent_id="demo_step4", persona={"name": "小墨"},
                   persist_dir=tempfile.mkdtemp())
    print("mood（初始）      =", round(a.mood, 3))
    print("chat（开心时）    =", a.chat("我们做题吧"))
    a.feel("学生今天骂了人", valence=-0.8)
    print("mood（受委屈后）  =", round(a.mood, 3))
    print("chat（低落时）    =", a.chat("我们做题吧"))
    a.save()


if __name__ == "__main__":
    run()
