"""第 1 步：最小智能体 —— 只写**两个钩子**就能跑。

运行：
    python demo/step_01_minimal.py

你会看到：一个智能体被创建、能选动作、能对话、能落地档位。
其余（记忆淘汰、情绪、动作采样、落盘）全部由基座 `BaseAgent` 包办。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# 从源码直接跑时用：把仓根加进 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_skills.sdk import BaseAgent  # noqa: E402


class StudyBuddy(BaseAgent):
    """学习陪伴小老师（最简版）。"""

    # 钩子 1：这个角色此刻能做什么
    def action_pool(self):
        return ["greet", "teach", "peek", "rest"]

    # 钩子 2：基于用户输入 + 检索到的记忆 + 当前情绪，渲染回复
    def _render_reply(self, text, facts, mood):
        name = self.persona.get("name", "小墨")
        return f"{name}：你好呀，我是你的学习小老师～"


def run() -> None:
    a = StudyBuddy(
        agent_id="demo_step1",
        persona={"name": "小墨", "temper": 0.6, "energy": 0.4, "play": 0.3},
        persist_dir=tempfile.mkdtemp(),
    )
    print("tier  =", a.tier, "（light=纯内置 / core=PASM核心 / bionic=+情绪模块）")
    print("act() =", a.act(), "  # 从动作池里挑一个（性格基线驱动）")
    print("chat()=", a.chat("你好"))
    a.save()
    print("save() 已落盘到:", a.persist_dir)


if __name__ == "__main__":
    run()
