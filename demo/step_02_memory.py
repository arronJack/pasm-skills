"""第 2 步：加记忆 —— 重要度（salience）决定一条记忆容不容易被挤掉。

运行：
    python demo/step_02_memory.py

要点：
  * `observe(title, ..., salience=, tags=, category=)` 写一条经历
  * `recall(query, k=)` 检索；**检索是字面匹配**，想被搜到就在 tags 里带人们会说的词
  * 容量上限 200 条，触顶按 (salience, 新旧) 淘汰 —— 重要度优先
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
        if facts:
            return f"{name}：我记得你说过「{facts[0].get('title', '')}」，我们再练练？"
        return f"{name}：好呀，你想先攻克哪个知识点？"

    def bootstrap_event(self):
        # 首次启动写入一条初始记忆（tags 里带「开学」才能被 recall('开学') 命中）
        return [{"title": "今天开始当你的学习小老师", "tags": ["开学"],
                 "salience": 3, "category": "里程碑"}]


def run() -> None:
    a = StudyBuddy(agent_id="demo_step2", persona={"name": "小墨"},
                   persist_dir=tempfile.mkdtemp())
    print("首次启动自动写入的初始记忆：",
          [f["title"] for f in a.recall("开学", k=3)] or "（轻量档检索按字面匹配）")

    # salience：1 日常 / 3 值得记 / 5 关键（里程碑、安全事实）
    a.observe("小雅每周三都卡在行程问题", brief="画图就懂",
              tags=["行程问题", "弱点"], salience=4, category="学情")
    a.observe("上次月考面积计算满分", tags=["面积计算"], salience=3, category="学情")
    a.observe("今天下雨，没去图书馆")                 # 默认 salience=1，最先被淘汰

    print("recall('行程问题') ->",
          [f["title"] for f in a.recall("行程问题", k=3)])
    print("recall('面积')      ->",
          [f["title"] for f in a.recall("面积", k=3)])
    a.save()


if __name__ == "__main__":
    run()
