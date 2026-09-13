"""第 7 步：实现之后怎么用 —— 把智能体接进真实产品。

运行：
    python demo/step_07_apply.py

本文件做三件事：
  1) 跑一段「脚本化对话」，让你看到成品智能体在真实交互里的样子（应用效果）；
  2) 演示「跨进程恢复」：同一 agent_id 再实例化，记忆/学情都还在；
  3) 给出 3 种把智能体塞进产品的集成骨架（CLI / FastAPI / 游戏循环）——
     这些都是可直接抄的模板，复制即用。

智能体是普通 Python 对象，可以放进任何东西里：Web 服务、游戏、桌面、定时任务。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo.agent import StudyBuddy  # noqa: E402


def _demo_session() -> None:
    print("--- 一段真实对话（学习陪伴·小墨）---")
    b = StudyBuddy(agent_id="demo_apply_xiaoming",
                   persona={"name": "小墨", "temper": 0.6, "energy": 0.4, "play": 0.3},
                   persist_dir=tempfile.mkdtemp())
    # 学生先暴露弱点
    b.observe("小明说行程问题老是错", tags=["行程问题", "弱点"], salience=4, category="学情")
    for turn in ["在吗", "我今天行程问题又错了", "面积计算我好像会了"]:
        print("  小明:", turn)
        print("  小墨:", b.chat(turn))
    # 学情跟踪
    b.report("行程问题", 0.3)
    b.report("面积计算", 0.9)
    print("  学情快照:", b.snapshot())
    b.save()


def _demo_recovery() -> None:
    print("\n--- 跨进程恢复：同 id 再实例化，记忆/学情都在 ---")
    d = tempfile.mkdtemp()
    b1 = StudyBuddy(agent_id="demo_apply_recover", persona={"name": "小墨"}, persist_dir=d)
    b1.report("行程问题", 0.3)
    b1.observe("学生喜欢用画图法", tags=["方法"], salience=3)
    b1.save()
    b2 = StudyBuddy(agent_id="demo_apply_recover", persona={"name": "小墨"}, persist_dir=d)
    print("  新实例 interactions =", b2.state.total_interactions, "(记忆已恢复)")
    print("  新实例 weakest      =", b2.snapshot()["weakest"])


def _show_integration_templates() -> None:
    print("\n--- 集成骨架（复制即用）---")
    print("""
# ① 命令行 / 桌面交互
def loop(agent_id, persona):
    b = StudyBuddy(agent_id=agent_id, persona=persona)   # 自动恢复状态
    while True:
        text = input("你: ")
        if text.strip().lower() in ("quit", "exit"):
            b.save(); break
        print("小墨:", b.chat(text))

# ② FastAPI（Web 服务）
from fastapi import FastAPI
app = FastAPI()
@app.post("/chat")
def chat(agent_id: str, text: str, persona: dict):
    b = StudyBuddy(agent_id=agent_id, persona=persona)
    return {"reply": b.chat(text), "tier": b.tier, "snapshot": b.snapshot()}

# ③ 游戏 / 模拟循环
def tick(npc, world_event: str):
    npc.observe(world_event, tags=["世界"], salience=3)
    play_animation(npc.act())      # 选一个动作并播放
""")


def run() -> None:
    _demo_session()
    _demo_recovery()
    _show_integration_templates()


if __name__ == "__main__":
    run()
