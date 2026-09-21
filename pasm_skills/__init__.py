"""pasm-skills —— PASM 智能体基座。

**基座只提供能力，不提供具体智能体。** 它给你三样东西：

1. **SDK**（`pasm_skills.sdk`）—— `BaseAgent`：观测 / 记忆 / 情绪 / 动作 / 反馈 / 持久化开箱可用，
   写智能体的人只需要关心 persona、动作池、回复模板；
2. **框架**（`pasm_skills.agent` / `context` / `scenarios` / `checks`）——
   智能体基类 + 注册表、仓库隔离探测、场景仿真底座、核心契约检查工具箱；
3. **打包**（`pasm_skills.build`）—— 把智能体打成平台可直接上传的技能包（两种归档形态）。

> **应用开发框架已独立成仓**：`BaseApplication` / `CapabilityDiscovery` / `BaseSkill`
> / `CognitiveAssembler` 等「产品应用」层已抽到独立包
> [`pasm-framework`](https://gitee.com/arronzheng/pasm-framework)（pasm-framework>=0.1.0）。
> 写产品智能体/应用请改用 `import pasm_framework`，本基座只保留 SDK / 验证器框架 / 打包库。

三分钟上手：

    python -m pasm_skills selftest            # 自检（零依赖，随时可跑）
    python -m pasm_skills list                # 看已发现的智能体 + 三仓定位

具体智能体由外部包提供（本基座**不内置**），发现方式见 `pasm_skills.discovery`：
entry points 组 `pasm_skills.agents`，或 `PASM_SKILLS_PATH` / `PASM_SKILLS_AGENT_MODULES`。
官方智能体集在独立公开仓 **pasm-agents**（NPC / 老人陪伴 / 学习陪伴 / 长期验证）。

零依赖：只用标准库，不需要 torch / 不需要 API key / 不需要服务器。
"""
from __future__ import annotations

__version__ = "0.6.2"

from .agent import (  # noqa: F401
    AGENTS, FAIL, HOOKS, OK, SKIP, WARN,
    Agent, AgentResult, Finding,
    agent, catalog, names, register, run_agent,
)
from . import discovery  # noqa: F401  智能体发现（entry points / 环境变量）
from . import scenarios  # noqa: F401  领域场景仿真底座（PRELUDE / 解释器择优 / 指标判定）
from . import sdk  # noqa: F401  产品智能体 SDK（BaseAgent）
from .context import REPO_SPEC, RepoContext  # noqa: F401

__all__ = [
    "__version__", "selftest",
    "Agent", "AgentResult", "Finding", "AGENTS", "HOOKS",
    "OK", "WARN", "FAIL", "SKIP",
    "agent", "catalog", "names", "register", "run_agent",
    "RepoContext", "REPO_SPEC", "scenarios", "sdk", "discovery",
]


def selftest() -> bool:
    """框架自检：不依赖任何 PASM 仓、也不依赖任何具体智能体，纯本地可跑。"""
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        if not cond:
            ok = False
            print("  x %s" % msg)
        else:
            print("  v %s" % msg)

    print("pasm-skills selftest v%s（基座）" % __version__)

    # 结论对象
    check(Finding(OK, "t").line().startswith("[OK]"), "Finding.line 带等级标签")
    r = AgentResult(agent="a", ok=True,
                    findings=[Finding(OK, "1"), Finding(FAIL, "2")])
    check(r.counts()[FAIL] == 1 and r.worst() == FAIL, "AgentResult 统计与最差等级正确")
    check(r.to_dict()["worst"] == FAIL, "AgentResult.to_dict 可序列化")

    # 智能体与注册表（基座不再内置智能体，这里现造一个）
    class _T(Agent):
        name = "_selftest_agent"
        goal = "自检用"

        def run(self):
            self.ok("收集一条结论")

    register(_T)
    check("_selftest_agent" in names(), "注册表能登记自定义智能体")
    check(agent("_selftest_agent") is _T, "按名字取回正确类")

    class _Boom(Agent):
        name = "_selftest_boom"
        goal = "抛异常也要被兜住"

        def run(self):
            raise RuntimeError("boom")

    register(_Boom)
    res = _Boom().execute()
    check(res.worst() == FAIL and "boom" in res.error, "run() 异常被兜住并计为 FAIL")

    # 智能体发现：没有任何外部智能体时也必须安静地成功
    try:
        loaded, _warns = discovery.load_agents()
        check(isinstance(loaded, list), "智能体发现机制可用（无外部智能体也不报错）")
    except Exception as ex:                          # noqa: BLE001
        check(False, "智能体发现机制可用（异常：%s）" % ex)

    # SDK：不依赖 PASM 核心也能建、能记、能选动作、能落盘
    import tempfile
    try:
        from .sdk import BaseAgent
        with tempfile.TemporaryDirectory() as td:
            class _A(BaseAgent):
                def action_pool(self):
                    return ["a1", "a2"]

                def _render_reply(self, text, facts, mood):
                    return "ok:%s" % text

            a = _A(agent_id="_selftest_sdk", persona={"name": "自检"}, persist_dir=td)
            a.observe("第一条记忆", salience=3)
            check(a.act() in ("a1", "a2"), "SDK：act() 从动作池里选")
            check(a.chat("hi").startswith("ok:"), "SDK：chat() 走 _render_reply")
            check(a.mood.__class__ is float, "SDK：mood 是 float 属性（不是方法）")
            check(isinstance(a.feedback("praise", action="a1"), dict), "SDK：feedback 返回权重字典")
            check(a.tier in ("light", "core", "bionic"), "SDK：tier 标注当前档位")
            a.save()
            check((a.persist_dir / "agent_state.json").exists(), "SDK：save() 落盘")
    except Exception as ex:                          # noqa: BLE001
        check(False, "SDK：建/记/选/存全链路可跑（异常：%s）" % ex)

    # 上下文
    ctx = RepoContext(roots=[])
    check(isinstance(ctx.describe(), dict), "RepoContext 可描述三仓定位")
    check(ctx.has() is True, "空 needs 视为满足")

    AGENTS.pop("_selftest_agent", None)
    AGENTS.pop("_selftest_boom", None)

    # 注：应用开发框架（BaseApplication/CapabilityDiscovery/BaseSkill/...）已独立成仓
    # pasm-framework（v0.1.0）。其表面由 pasm-framework 自带 selftest 与 pasm-agents 的
    # surface-guard 共同守护，本基座 selftest 不再重复覆盖。

    print("pasm-skills selftest:", "通过" if ok else "失败")
    return ok
