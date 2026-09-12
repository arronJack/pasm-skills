"""智能体骨架 —— 复制这个文件，改三处（persona 默认值 / action_pool / _render_reply）就能跑。

用法：
    cp templates/agent_template.py my_agent.py
    python my_agent.py            # 自带一个最小冒烟，看到效果

设计要点（都是踩过坑的）：
  * 只实现两个必填钩子：`action_pool()` 与 `_render_reply()`
  * 动作名带 §4 的关键词，性格特质才会自动影响它；否则覆盖 `_fallback_weights()`
  * `feedback(kind, action=)` 一定要传 action，否则反馈只作用在"当前最偏好"的动作上
  * 关键记忆用 `salience=5`，否则容量触顶时会被日常琐事挤掉
  * 额外结构化状态放 `self.state.notes`（随 state 一起落盘），不要另开文件
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# 复制到仓里直接跑时用；已 pip install pasm-skills 的话这两行可以删
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_skills.sdk import BaseAgent  # noqa: E402


class MyAgent(BaseAgent):
    """把这里改成你的角色。"""

    # ---- 必填钩子 1：能做什么 --------------------------------------
    def action_pool(self) -> List[str]:
        """动作名里的关键词决定它受哪个性格特质影响（见 SKILL 文档 §4）。

        wave/talk/share/teach/give -> temper
        hop/dance/spin/ball/run    -> energy
        peek/play/joke/boast       -> play
        """
        return ["greet", "work", "peek", "rest"]

    # ---- 必填钩子 2：怎么回 ----------------------------------------
    def _render_reply(self, text: str, facts: List[Dict[str, Any]], mood: float) -> str:
        """`facts` = 检索到的记忆（可能为空），`mood` = 当前情绪 [-1, 1]。"""
        name = self.persona.get("name", "我")
        low = mood < -0.2
        if facts:
            top = facts[0]
            return ("（低声）" if low else "") + f"{name}想起了「{top.get('title','')}」……"
        return f"{name}：嗯，你说。" if not low else f"{name}：……（没什么精神）"

    # ---- 可选钩子：首次启动的初始记忆 ------------------------------
    def bootstrap_event(self) -> List[Dict[str, Any]]:
        return [{
            "title": "我今天第一天开张",
            "brief": "门口挂了个木牌",
            "tags": ["开张"],
            "salience": 3,
            "category": "里程碑",
        }]


def _smoke() -> None:
    """最小冒烟：确认能记忆、能选动作、能对话、能落盘、档位正确。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        a = MyAgent(agent_id="_template_smoke",
                    persona={"name": "测试", "temper": 0.6, "energy": 0.4, "play": 0.3},
                    persist_dir=td)
        print("tier      :", a.tier)
        a.observe("客人第一次上门", salience=4, tags=["客人"])
        print("act()     :", a.act())
        print("chat()    :", a.chat("还记得我吗"))
        print("recall()  :", [f.get("title") for f in a.recall("客人", k=3)])
        print("mood      :", a.mood)
        a.feedback("praise", action=a.action_pool()[0])
        a.feel("被夸了", valence=0.5)
        a.save()
        print("saved to  :", a.persist_dir)
        print("summary   :", {k: a.summary()[k] for k in ("tier", "total_interactions", "mood")})


if __name__ == "__main__":
    _smoke()
