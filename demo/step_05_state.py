"""第 5 步：加结构化状态 —— 用 `state.notes` 跟踪学情，并给外部一个 `snapshot()` 出口。

运行：
    python demo/step_05_state.py

原则：
  * 按知识点记分、记进度这类结构化数据，放 `self.state.notes`（随 agent_state.json 落盘，不用另开文件）
  * 外部要读的，给一个 `snapshot()` 机读出口；`state.notes` 是内部状态，别让调用方伸手进去
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_skills.sdk import BaseAgent  # noqa: E402


class StudyBuddy(BaseAgent):
    def action_pool(self):
        return ["greet", "teach", "peek", "rest"]

    def _render_reply(self, text, facts, mood):
        return f"{self.persona.get('name', '小墨')}：好呀。"

    # —— 学情：EMA 平滑更新掌握度 ——
    def report(self, topic: str, score: float) -> Dict[str, Any]:
        ks = self.state.notes.setdefault("knowledge_state", {})
        prev = ks.get(topic, 0.0)
        ks[topic] = round(prev * 0.7 + score * 0.3, 3)
        return {"topic": topic, "new_mastery": ks[topic]}

    def mastery(self, topic: str) -> float:
        return (self.state.notes.get("knowledge_state") or {}).get(topic, 0.0)

    def snapshot(self) -> Dict[str, Any]:
        ks = self.state.notes.get("knowledge_state") or {}
        return {
            "mastery": ks,
            "weakest": min(ks, key=ks.get) if ks else None,
            "average": round(sum(ks.values()) / len(ks), 3) if ks else 0.0,
            "tier": self.tier,
        }


def run() -> None:
    a = StudyBuddy(agent_id="demo_step5", persona={"name": "小墨"},
                   persist_dir=tempfile.mkdtemp())
    for topic, score in [("分数加减", 0.4), ("面积计算", 0.9), ("行程问题", 0.2)]:
        print("report:", a.report(topic, score))
    print("mastery('行程问题') =", a.mastery("行程问题"))
    print("snapshot() =", a.snapshot())
    a.save()


if __name__ == "__main__":
    run()
