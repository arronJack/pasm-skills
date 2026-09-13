"""一键跑完所有步骤，并汇总「应用效果」。

运行：
    python -m demo.run_all
    python demo/run_all.py

它会依次执行 step_01 → step_06，再跑 step_07 的应用演示，
最后打印一份**真实跑出来的效果对照**（反馈塑形 / 记忆 / 持久化 / 学情）。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import demo.step_01_minimal as s1  # noqa: E402
import demo.step_02_memory as s2  # noqa: E402
import demo.step_03_feedback as s3  # noqa: E402
import demo.step_04_emotion as s4  # noqa: E402
import demo.step_05_state as s5  # noqa: E402
import demo.step_06_growth as s6  # noqa: E402
import demo.step_07_apply as s7  # noqa: E402
from demo.agent import StudyBuddy  # noqa: E402


def _banner(title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def main() -> int:
    _banner("PASM 智能体 Demo —— 分步走查（实现）")
    s1.run(); s2.run(); s3.run(); s4.run(); s5.run(); s6.run()

    _banner("应用演示（实现后怎么用）")
    s7.run()

    _banner("应用效果汇总（真实跑出来的数字）")
    _effects()
    return 0


def _effects() -> None:
    # ① 反馈塑形：复算一组 before/after（seed=0 可复现）
    a = StudyBuddy(agent_id="demo_effects", persona={"name": "小墨",
                   "temper": 0.6, "energy": 0.5, "play": 0.4},
                   persist_dir=tempfile.mkdtemp(), seed=0)
    pool = a.action_pool()
    before = {x: 0 for x in pool}
    for _ in range(400):
        before[a.act()] += 1
    for _ in range(60):
        a.feedback("praise", action="teach")
        a.feedback("scold", action="peek")
    after = {x: 0 for x in pool}
    for _ in range(400):
        after[a.act()] += 1

    print("① 反馈塑形（被夸的 teach 变多、被凶的 peek 变少）：")
    print("   动作    反馈前 → 反馈后")
    for x in pool:
        print("     %-6s %5.1f%% → %5.1f%%" % (x, before[x] / 4, after[x] / 4))

    # ② 记忆检索精度
    b = StudyBuddy(agent_id="demo_effects_mem", persona={"name": "小墨"},
                   persist_dir=tempfile.mkdtemp())
    b.observe("小明每周三卡在行程问题", tags=["行程问题", "弱点"], salience=4)
    b.observe("下雨天没去图书馆", salience=1)
    hits = [f["title"] for f in b.recall("行程问题", k=3)]
    print("\n② 记忆检索：recall('行程问题') 命中 ->", hits)

    # ③ 持久化 / 跨进程恢复
    d = tempfile.mkdtemp()
    c1 = StudyBuddy(agent_id="demo_effects_persist", persona={"name": "小墨"}, persist_dir=d)
    c1.report("行程问题", 0.3)
    c1.observe("学生爱画图", tags=["方法"], salience=3)
    c1.save()
    c2 = StudyBuddy(agent_id="demo_effects_persist", persona={"name": "小墨"}, persist_dir=d)
    print("\n③ 持久化恢复：新实例 interactions =", c2.state.total_interactions,
          "weakest =", c2.snapshot()["weakest"])

    # ④ 学情跟踪
    print("\n④ 学情跟踪：snapshot =", c2.snapshot())
    print("\n全部跑通。下一步：把你的类放进一个包，参考 tools/build_skill.py 打成技能包。")


if __name__ == "__main__":
    raise SystemExit(main())
