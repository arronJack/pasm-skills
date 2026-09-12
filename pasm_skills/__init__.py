"""pasm-skills —— PASM 智能体工坊。

用途：把「对 PASM 核心内容的长期验证」做成**可重复运行的智能体**，
而不是每次靠人回忆"上次好像是对的"。

三分钟上手：
    python -m pasm_skills list
    python -m pasm_skills run core-verifier
    python -m pasm_skills run regression --update     # 存一次事实基线
    python -m pasm_skills run --all

零依赖：只用标准库，不需要 torch / 不需要 API key / 不需要服务器。
"""
from __future__ import annotations

__version__ = "0.2.1"

from .agent import (  # noqa: F401
    AGENTS, FAIL, HOOKS, OK, SKIP, WARN,
    Agent, AgentResult, Finding,
    agent, catalog, names, register, run_agent,
)
from . import scenarios  # noqa: F401  领域场景仿真底座（PRELUDE / 解释器择优 / 指标判定）
from .context import REPO_SPEC, RepoContext  # noqa: F401

__all__ = [
    "__version__", "selftest",
    "Agent", "AgentResult", "Finding", "AGENTS", "HOOKS",
    "OK", "WARN", "FAIL", "SKIP",
    "agent", "catalog", "names", "register", "run_agent",
    "RepoContext", "REPO_SPEC", "scenarios",
]


def selftest() -> bool:
    """框架自检：不依赖任何 PASM 仓，纯本地可跑。"""
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        if not cond:
            ok = False
            print("  x %s" % msg)
        else:
            print("  v %s" % msg)

    print("pasm-skills selftest v%s" % __version__)

    # 结论对象
    check(Finding(OK, "t").line().startswith("[OK]"), "Finding.line 带等级标签")
    r = AgentResult(agent="a", ok=True,
                    findings=[Finding(OK, "1"), Finding(FAIL, "2")])
    check(r.counts()[FAIL] == 1 and r.worst() == FAIL, "AgentResult 统计与最差等级正确")
    check(r.to_dict()["worst"] == FAIL, "AgentResult.to_dict 可序列化")

    # 智能体与注册表
    from . import agents as _agents  # noqa: F401

    class _T(Agent):
        name = "_selftest_agent"
        goal = "自检用"

        def run(self):
            self.ok("收集一条结论")

    register(_T)
    check("_selftest_agent" in names(), "注册表能登记自定义智能体")
    check(agent("_selftest_agent") is _T, "按名字取回正确类")
    check(len(_agents.__all__) >= 3, "内置智能体已随包注册")

    class _Boom(Agent):
        name = "_selftest_boom"
        goal = "抛异常也要被兜住"

        def run(self):
            raise RuntimeError("boom")

    register(_Boom)
    res = _Boom().execute()
    check(res.worst() == FAIL and "boom" in res.error, "run() 异常被兜住并计为 FAIL")

    # 上下文
    ctx = RepoContext(roots=[])
    check(isinstance(ctx.describe(), dict), "RepoContext 可描述三仓定位")
    check(ctx.has() is True, "空 needs 视为满足")

    AGENTS.pop("_selftest_agent", None)
    AGENTS.pop("_selftest_boom", None)
    print("pasm-skills selftest:", "通过" if ok else "失败")
    return ok
