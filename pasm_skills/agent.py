"""智能体骨架 —— 零依赖（纯标准库）。

一个「智能体」在这里的定义很克制：**一段可被反复运行、产出结构化结论的检查逻辑**。

    class MyAgent(Agent):
        name = "my-agent"
        goal = "一句话说清它替你把关什么"
        def run(self) -> AgentResult: ...

它不持有 LLM、不常驻、不需要服务器。这样设计是刻意的：

  · 长期验证要的是**可重复、可比较、可归档**，不是"看起来很智能"；
  · 无 LLM 依赖 ⇒ 断网、无 key、无显卡也能跑，结论只由代码事实决定；
  · 结论落成 JSON ⇒ 天然可做基线对比（今天 vs 上周有没有退化）。

需要"会思考"的智能体时，在 `run()` 里自己调 LLM 即可，框架不拦。
"""
from __future__ import annotations

import os
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

# ---------------------------------------------------------------- 结论对象
OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
_LEVEL_ORDER = {OK: 0, SKIP: 1, WARN: 2, FAIL: 3}

_ICON = {OK: "[OK]  ", WARN: "[WARN]", FAIL: "[FAIL]", SKIP: "[SKIP]"}


@dataclass
class Finding:
    """一条结论。level 用 OK/WARN/FAIL/SKIP 四个常量。"""

    level: str
    title: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {"level": self.level, "title": self.title, "detail": self.detail}

    def line(self) -> str:
        tag = _ICON.get(self.level, "[????]")
        return "%s %s%s" % (tag, self.title,
                            ("  -- %s" % self.detail) if self.detail else "")


@dataclass
class AgentResult:
    """一个智能体一次运行的完整结论。"""

    agent: str
    ok: bool
    findings: List[Finding] = field(default_factory=list)
    elapsed: float = 0.0
    error: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    # ---- 统计 ----
    def counts(self) -> Dict[str, int]:
        out = {OK: 0, WARN: 0, FAIL: 0, SKIP: 0}
        for f in self.findings:
            out[f.level] = out.get(f.level, 0) + 1
        return out

    def worst(self) -> str:
        if self.error:
            return FAIL
        worst = OK
        for f in self.findings:
            if _LEVEL_ORDER.get(f.level, 0) > _LEVEL_ORDER.get(worst, 0):
                worst = f.level
        return worst

    # ---- 输出 ----
    def to_dict(self) -> dict:
        return {"agent": self.agent, "ok": bool(self.ok), "worst": self.worst(),
                "elapsed": round(self.elapsed, 3), "error": self.error,
                "counts": self.counts(),
                "findings": [f.to_dict() for f in self.findings],
                "extra": self.extra}

    def text(self, verbose: bool = True) -> str:
        c = self.counts()
        head = "%s  %s  (%.2fs | ok %d / warn %d / fail %d / skip %d)" % (
            _ICON.get(self.worst(), "[????]"), self.agent, self.elapsed,
            c[OK], c[WARN], c[FAIL], c[SKIP])
        lines = [head]
        if self.error:
            lines.append("     运行异常: %s" % self.error)
        for f in self.findings:
            if not verbose and f.level == OK:
                continue
            lines.append("     " + f.line())
        return "\n".join(lines)


# ---------------------------------------------------------------- 智能体基类
class Agent:
    """所有智能体的基类。

    子类需要覆盖 `name` / `goal` / `run()`。
    `run()` 里请用 `self.ok()/self.warn()/self.fail()/self.skip()` 收集结论，
    或直接返回一个 AgentResult。
    """

    name: str = "agent"
    goal: str = ""
    #: 需要的仓库键（由 RepoContext 保证存在）；缺失时框架会跳过本智能体
    needs: tuple = ()

    def __init__(self, ctx: Any = None, options: Optional[dict] = None):
        self.ctx = ctx
        self.options = options or {}
        self._findings: List[Finding] = []

    # ---- 结论收集 ----
    def add(self, level: str, title: str, detail: str = "") -> None:
        self._findings.append(Finding(level, title, detail))

    def ok(self, title: str, detail: str = "") -> None:
        self.add(OK, title, detail)

    def warn(self, title: str, detail: str = "") -> None:
        self.add(WARN, title, detail)

    def fail(self, title: str, detail: str = "") -> None:
        self.add(FAIL, title, detail)

    def skip(self, title: str, detail: str = "") -> None:
        self.add(SKIP, title, detail)

    # ---- 子类实现 ----
    def run(self) -> AgentResult:                     # pragma: no cover
        raise NotImplementedError

    # ---- 框架调用入口 ----
    def execute(self) -> AgentResult:
        """带计时与异常兜底的执行；子类不要覆盖。"""
        t0 = time.perf_counter()
        self._findings = []
        error = ""
        try:
            result = self.run()
            if isinstance(result, AgentResult):
                result.agent = result.agent or self.name
                result.elapsed = time.perf_counter() - t0
                if self._findings:
                    result.findings = self._findings + list(result.findings)
                return result
            if result is None:
                result = AgentResult(agent=self.name, ok=True)
        except Exception as ex:                       # noqa: BLE001
            error = "%s: %s" % (type(ex).__name__, ex)
            if os.environ.get("PASM_SKILLS_DEBUG"):
                traceback.print_exc()
            result = AgentResult(agent=self.name, ok=False)

        result.agent = result.agent or self.name
        result.elapsed = time.perf_counter() - t0
        if self._findings:
            result.findings = self._findings + list(result.findings)
        result.error = error
        result.ok = bool(result.ok) and not error and result.worst() != FAIL
        return result

    # ---- 文档 ----
    @classmethod
    def describe(cls) -> dict:
        return {"name": cls.name, "goal": cls.goal,
                "needs": list(cls.needs), "doc": (cls.__doc__ or "").strip()}


# ---------------------------------------------------------------- 注册表
AGENTS: Dict[str, Type[Agent]] = {}


def register(cls: Type[Agent]) -> Type[Agent]:
    """类装饰器：把智能体登记进全局注册表。"""
    if not getattr(cls, "name", None) or cls.name == "agent":
        raise ValueError("智能体必须有唯一的 name：%r" % cls)
    AGENTS[cls.name] = cls
    return cls


def agent(name: str) -> Type[Agent]:
    """按名字取智能体类，取不到抛出带可选清单的 KeyError。"""
    if name not in AGENTS:
        raise KeyError("未知智能体 %r（可用：%s）"
                       % (name, ", ".join(names()) or "无"))
    return AGENTS[name]


def names() -> List[str]:
    return sorted(AGENTS)


def catalog() -> List[dict]:
    return [AGENTS[n].describe() for n in names()]


def run_agent(name: str, ctx: Any = None, options: Optional[dict] = None) -> AgentResult:
    """创建并执行一个智能体（带 needs 预检）。"""
    cls = agent(name)
    missing = [k for k in cls.needs if not (ctx and ctx.has(k))]
    if missing:
        res = AgentResult(agent=name, ok=False)
        res.findings.append(Finding(SKIP, "缺少依赖仓库，已跳过",
                                    "未找到：%s" % ", ".join(missing)))
        return res
    return cls(ctx, options).execute()


#: 便于第三方扩展：把自定义 Agent 类挂进来即可
HOOKS: Dict[str, Callable[..., Any]] = {}
