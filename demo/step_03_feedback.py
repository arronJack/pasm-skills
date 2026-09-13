"""第 3 步：加反馈塑形 —— 夸谁，谁以后就更多出现（行为会被学习改变）。

运行：
    python demo/step_03_feedback.py

⚠️ 关键：`feedback(kind, action=)` **一定要传 action**。不传的话反馈会作用在
「当前最偏好的动作」上，偏好越高越加码，长期行为会极端化。

本步用 seed=0 复现一组「反馈前 vs 反馈后」的动作分布对比（应用效果之一）。
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
        return f"{self.persona.get('name', '小墨')}：好呀。"


def run() -> None:
    a = StudyBuddy(agent_id="demo_step3", persona={"name": "小墨",
                   "temper": 0.6, "energy": 0.5, "play": 0.4},
                   persist_dir=tempfile.mkdtemp(), seed=0)
    pool = a.action_pool()

    # —— 反馈前：采样 400 次，记录各动作占比 ——
    before = {x: 0 for x in pool}
    for _ in range(400):
        before[a.act()] += 1

    # —— 用户反馈：夸「teach」、凶「peek」 ——
    for _ in range(60):
        a.feedback("praise", action="teach")   # +0.3
        a.feedback("scold", action="peek")     # -0.3

    # —— 反馈后 ——
    after = {x: 0 for x in pool}
    for _ in range(400):
        after[a.act()] += 1

    print("动作    反馈前 → 反馈后（占比，seed=0 可复现）")
    for x in pool:
        print("  %-6s %5.1f%% → %5.1f%%" % (x, before[x] / 4, after[x] / 4))
    print("结论：被夸的 teach 变多、被凶的 peek 变少 —— 智能体真的「学到了」。")
    a.save()


if __name__ == "__main__":
    run()
