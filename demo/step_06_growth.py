"""第 6 步：加成长 —— 用 `growth_stage` 随阶段解锁更多动作。

运行：
    python demo/step_06_growth.py

动作池不是写死的：阶段越高，能做的越多。配合 `state.growth_stage` 即可，
基座的 `act()` 会自动从「当前阶段解锁的池子」里选动作。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_skills.sdk import BaseAgent  # noqa: E402


class StudyBuddy(BaseAgent):
    # 阶段 → 动作池
    ACTS = {
        0: ["greet", "teach", "peek", "rest"],
        1: ["greet", "teach", "peek", "rest", "quiz", "give"],
        2: ["greet", "teach", "peek", "rest", "quiz", "give", "report"],
    }

    def action_pool(self):
        stage = min(self.state.growth_stage, max(self.ACTS))
        return list(self.ACTS[stage])

    def _render_reply(self, text, facts, mood):
        return f"{self.persona.get('name', '小墨')}：好呀。"


def run() -> None:
    a = StudyBuddy(agent_id="demo_step6", persona={"name": "小墨"},
                   persist_dir=tempfile.mkdtemp())
    print("阶段 0 动作池：", a.action_pool())
    a.state.growth_stage = 1
    print("阶段 1 动作池：", a.action_pool())
    a.state.growth_stage = 2
    print("阶段 2 动作池：", a.action_pool())
    a.save()


if __name__ == "__main__":
    run()
