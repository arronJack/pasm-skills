"""可复用的校验集 —— 智能体从这里挑检查项拼装。

每个 `check_*` 接收一个智能体实例（`agent.ctx` 提供三仓上下文），
把结论通过 `agent.ok/warn/fail/skip` 收集起来；自己绝不抛异常。

约定：`check_*` 只做**只读**操作（import、哈希比对、跑子进程），不写任何仓库文件。
基线写入由 regression 智能体自己负责。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# 认知皮层"必须落盘核心"的模块（v0.28.5 起）
CORE_COGNITIVE_MODULES = ("cog", "memory_layers", "symbolic", "memrouter",
                          "memvec", "learning", "agent_team", "workctx",
                          "coder", "selfheal", "mathlab", "percept", "quantum",
                          "facts", "worldmodel")

#: 记忆质量基线：本套件一旦全绿，记忆层从"零覆盖"变成"可回归"
MEMORY_QUALITY_BASELINE = 1.0

#: 引擎契约的规范快照区块
SNAPSHOT_SECTIONS = ("step", "personality", "emotion", "development",
                     "memory", "global_workspace", "last_retrieval")


def _j(result: Dict[str, Any]) -> Optional[dict]:
    return result.get("json")


# ---------------------------------------------------------------- 1. 引擎契约
CONTRACT_CODE = r"""
import json
out = {"api": None, "engines": [], "conforms": [], "snapshot": {}}
try:
    from pasm import engine_api as ea
    out["api"] = getattr(ea, "API_VERSION", "?")
    out["engines"] = ea.available()
    for nm in out["engines"]:
        try:
            eng = ea.create(nm)
            okk, probs = ea.conforms(eng, strict=True)
            out["conforms"].append({"engine": nm, "ok": bool(okk),
                                    "problems": list(probs)})
            try:
                snap = eng.snapshot()
                out["snapshot"][nm] = sorted(snap.keys())
            except Exception as ex:
                out["snapshot"][nm] = "snapshot() 异常: %s" % ex
        except Exception as ex:
            out["conforms"].append({"engine": nm, "ok": False,
                                    "problems": ["create 失败: %s" % ex]})
except Exception as ex:
    out["fatal"] = "%s: %s" % (type(ex).__name__, ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""


def check_contract(agent, engines: Optional[List[str]] = None) -> None:
    """核心包 `pasm.engine_api` 可用、内置引擎能创建、且通过 `conforms(strict)`。"""
    res = agent.ctx.probe("core", CONTRACT_CODE)
    data = _j(res)
    if data is None:
        agent.fail("引擎契约探测失败", (res.get("stderr") or "")[:300])
        return
    if data.get("fatal"):
        agent.fail("pasm.engine_api 不可用", data["fatal"])
        return
    agent.ok("pasm.engine_api 可导入", "api=%s" % data.get("api"))

    available = data.get("engines") or []
    if not available:
        agent.skip("本机无内置引擎可创建", "（无 torch 环境属正常：仅剩零依赖契约层）")
        return
    wanted = engines or available
    for row in data.get("conforms", []):
        if row["engine"] not in wanted:
            continue
        if row["ok"]:
            agent.ok("引擎 %s 通过契约校验" % row["engine"])
        else:
            agent.fail("引擎 %s 不符合契约" % row["engine"],
                       "; ".join(row.get("problems", []))[:300])
    for nm, keys in (data.get("snapshot") or {}).items():
        if nm not in wanted:
            continue
        if isinstance(keys, str):
            agent.fail("引擎 %s 快照异常" % nm, keys)
            continue
        missing = [s for s in SNAPSHOT_SECTIONS if s not in keys]
        if missing:
            agent.warn("引擎 %s 快照缺区块" % nm, "缺：%s" % ", ".join(missing))
        else:
            agent.ok("引擎 %s 快照七区块齐全" % nm)


# ---------------------------------------------------------------- 2. 认知层落盘
LAYERS_CODE = r"""
import json, importlib, io, contextlib, os
names = __NAMES__
out = {"module": {}, "selftest": {}, "missing_files": []}
for n in names:
    p = os.path.join("pasm", "cognitive", n + ".py")
    if not os.path.exists(p):
        out["missing_files"].append(n)
for n in names:
    if n in out["missing_files"]:
        continue
    try:
        mod = importlib.import_module("pasm.cognitive." + n)
        out["module"][n] = "ok"
    except Exception as ex:
        out["module"][n] = "FAIL " + type(ex).__name__ + ": " + str(ex)
        continue
    fn = getattr(mod, "selftest", None)
    if callable(fn):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                r = fn()
            out["selftest"][n] = bool(r)
        except Exception as ex:
            out["selftest"][n] = "ERR " + type(ex).__name__ + ": " + str(ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""


def _layers_code(names) -> str:
    return LAYERS_CODE.replace("__NAMES__", repr(list(names)))


def check_cognitive_layers(agent) -> None:
    """核心包 `pasm/cognitive/` 是否**全部**落盘、可导入、自检通过。"""
    res = agent.ctx.probe("core", _layers_code(CORE_COGNITIVE_MODULES), timeout=120)
    data = _j(res)
    if data is None:
        agent.fail("认知层探测失败", (res.get("stderr") or "")[:300])
        return
    missing = data.get("missing_files") or []
    if missing:
        agent.fail("核心包缺认知层文件", "缺：%s" % ", ".join(missing))
    else:
        agent.ok("认知层文件齐全", "%d 个模块全在 pasm/cognitive/" % len(CORE_COGNITIVE_MODULES))

    for n, st in (data.get("module") or {}).items():
        if st != "ok":
            agent.fail("pasm.cognitive.%s 导入失败" % n, st[:250])
    bad = {k: v for k, v in (data.get("selftest") or {}).items() if v is not True}
    if bad:
        for k, v in bad.items():
            agent.fail("pasm.cognitive.%s.selftest 未通过" % k, str(v)[:250])
    have_st = [k for k, v in (data.get("selftest") or {}).items() if v is True]
    if have_st:
        agent.ok("模块自检通过", "%d 个：%s" % (len(have_st), ", ".join(sorted(have_st))))


# ---------------------------------------------------------------- 3. 符号闭环
LOOP_CODE = r"""
import json
out = {}
try:
    from pasm.cognitive import symbolic as SY
    out["writeback"] = callable(getattr(SY, "writeback", None))
    out["set_memory_sink"] = callable(getattr(SY, "set_memory_sink", None))
    out["solve"] = callable(getattr(SY, "solve", None))
    out["verify"] = callable(getattr(SY, "verify", None))
    out["prompt_block"] = callable(getattr(SY, "prompt_block", None))
    try:
        from pasm.cognitive import memrouter as MR
        out["route"] = callable(getattr(MR, "route", None))
        out["classify"] = callable(getattr(MR, "classify", None))
    except Exception as ex:
        out["route_err"] = str(ex)
except Exception as ex:
    out["fatal"] = "%s: %s" % (type(ex).__name__, ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""


def check_symbolic_loop(agent) -> None:
    """符号层↔向量记忆的回写闭环是否具备完整接线面。"""
    data = _j(agent.ctx.probe("core", LOOP_CODE))
    if data is None:
        agent.fail("符号层探测失败")
        return
    if data.get("fatal"):
        agent.fail("符号层导入失败", data["fatal"])
        return
    for key, label in (("solve", "solve()"), ("verify", "verify()"),
                       ("prompt_block", "prompt_block()"),
                       ("writeback", "writeback()"),
                       ("set_memory_sink", "set_memory_sink()")):
        if data.get(key):
            agent.ok("符号层 %s 齐备" % label)
        else:
            agent.fail("符号层缺 %s" % label, "闭环/注入面不完整")
    if data.get("route_err"):
        agent.fail("记忆路由器不可用", data["route_err"][:250])
    elif data.get("route") and data.get("classify"):
        agent.ok("记忆路由器 route()/classify() 齐备")
    else:
        agent.fail("记忆路由器缺 route()/classify()")


# ---------------------------------------------------------------- 4. 学习层契约
LEARN_CODE = r"""
import json
out = {}
try:
    from pasm.cognitive import learning as L
    try:
        _ok, _probs = L.learning_conforms(L.LearningEngine(), strict=True)
        conforms = {"ok": bool(_ok), "problems": list(_probs)}
    except Exception as ex:
        conforms = {"ok": False, "problems": ["%s: %s" % (type(ex).__name__, ex)]}
    out["core"] = {
        "api": getattr(L, "LEARNING_API", None),
        "required": list(getattr(L, "LEARNING_REQUIRED_METHODS", ())),
        "has_api": hasattr(L, "LEARNING_API"),
        "has_engine": hasattr(L, "LearningEngine"),
        "has_protocol": hasattr(L, "LearningLayer"),
        "has_conforms": hasattr(L, "learning_conforms"),
        "conforms": conforms,
        "selftest": None,
    }
    fn = getattr(L, "selftest", None)
    if callable(fn):
        try:
            out["core"]["selftest"] = bool(fn())
        except Exception as ex:
            out["core"]["selftest"] = "ERR %s" % ex
except Exception as ex:
    out["core_err"] = "%s: %s" % (type(ex).__name__, ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""

LITE_LEARN_CODE = r"""
import json, importlib
out = {}
try:
    import learning as L
    try:
        _ok, _probs = L.learning_conforms(L.LearningLayer(), strict=True)
        conforms = {"ok": bool(_ok), "problems": list(_probs)}
    except Exception as ex:
        conforms = {"ok": False, "problems": ["%s: %s" % (type(ex).__name__, ex)]}
    out["classes"] = [c for c in dir(L) if c[0].isupper()]
    out["has_learninglayer"] = hasattr(L, "LearningLayer")
    out["api"] = getattr(L, "LEARNING_API", None)
    out["required"] = list(getattr(L, "LEARNING_REQUIRED_METHODS", ()))
    out["conforms"] = conforms
    out["selftest"] = None
    fn = getattr(L, "selftest", None)
    if callable(fn):
        try:
            out["selftest"] = bool(fn())
        except Exception as ex:
            out["selftest"] = "ERR %s" % ex
except Exception as ex:
    out["fatal"] = "%s: %s" % (type(ex).__name__, ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""

#: 跨档互换验证：同一个解释器里同时加载两档，用同一段调用方代码驱动
LEARN_SWAP_CODE = r"""
import json
out = {}
try:
    from pasm.cognitive import learning as CORE
    import learning as LITE
    core, lite = CORE.LearningEngine(seed=1), LITE.LearningLayer()
    core.design({"energy": 0.6, "play": 0.5, "temper": 0.5}, 3,
                ["wave", "hop", "peek", "ball", "dance", "spin", "think"])
    _oc, _pc = CORE.learning_conforms(core, strict=True)
    _ol, _pl = LITE.learning_conforms(lite, strict=True)
    out["api"] = getattr(CORE, "LEARNING_API", None)
    out["api_same"] = (getattr(CORE, "LEARNING_API", None)
                       == getattr(LITE, "LEARNING_API", None))
    out["req_same"] = (set(getattr(CORE, "LEARNING_REQUIRED_METHODS", ()))
                       == set(getattr(LITE, "LEARNING_REQUIRED_METHODS", ())))
    out["core"] = {"ok": bool(_oc), "problems": list(_pc),
                   "tier": core.info().tier, "kind": core.info().kind}
    out["lite"] = {"ok": bool(_ol), "problems": list(_pl),
                   "tier": lite.info().tier, "kind": lite.info().kind}
    out["caps_same"] = sorted(core.capabilities()) == sorted(lite.capabilities())
    # 同一段驱动代码（只认契约方法）跑两档 → 输出结构应同构
    drive = []
    for lay in (core, lite):
        try:
            info = lay.info()
            info = info.to_dict() if hasattr(info, "to_dict") else dict(info)
            drive.append({"api": info.get("api"),
                          "keys": sorted(info.keys()),
                          "state_keys": sorted(lay.state()),
                          "bias_len": len(list(lay.bias(None)))})
        except Exception as ex:
            drive.append({"err": "%s: %s" % (type(ex).__name__, ex)})
    out["drive"] = drive
except Exception as ex:
    out["fatal"] = "%s: %s" % (type(ex).__name__, ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""


def check_learning_contract(agent) -> None:
    """学习层：核心档（pasm.cognitive.learning）与 Lite 档（learning.py）都存在且可用。"""
    core = _j(agent.ctx.probe("core", LEARN_CODE))
    if core is None:
        agent.fail("核心学习层探测失败")
    elif core.get("core_err"):
        agent.fail("pasm.cognitive.learning 导入失败", core["core_err"])
    else:
        c = core.get("core") or {}
        if c.get("has_api"):
            agent.ok("核心学习层已声明学习接口契约", "api=%s" % c.get("api"))
        else:
            agent.warn("核心学习层尚未声明 LEARNING_API",
                       "建议按「同一接口两档实现」收敛")
        for k, label in (("has_engine", "LearningEngine 完整档"),
                         ("has_protocol", "LearningLayer 接口协议")):
            if c.get(k):
                agent.ok("核心学习层含 %s" % label)
            else:
                agent.warn("核心学习层缺 %s" % label)
        cf = c.get("conforms") or {}
        if cf.get("ok"):
            agent.ok("完整档满足学习层契约（strict）")
        elif c.get("has_conforms"):
            agent.fail("完整档不符合学习层契约", "; ".join(cf.get("problems", []))[:250])
        st = c.get("selftest")
        if st is True:
            agent.ok("核心学习层 selftest 通过")
        elif st:
            agent.fail("核心学习层 selftest 未通过", str(st)[:200])

    lite = _j(agent.ctx.probe("lite", LITE_LEARN_CODE))
    if lite is None:
        agent.warn("Lite 学习层探测失败")
    elif lite.get("fatal"):
        agent.warn("PASM-Lite learning.py 探测失败（多为该解释器无 torch）",
                   lite["fatal"][:250])
    else:
        if lite.get("has_learninglayer"):
            agent.ok("Lite 学习层含 LearningLayer", "api=%s" % lite.get("api"))
        else:
            agent.warn("Lite 学习层缺 LearningLayer", "实际类：%s" % lite.get("classes"))
        cf = lite.get("conforms") or {}
        if cf.get("ok"):
            agent.ok("教学档满足学习层契约（strict）")
        else:
            agent.fail("教学档不符合学习层契约", "; ".join(cf.get("problems", []))[:250])
        st = lite.get("selftest")
        if st is True:
            agent.ok("Lite 学习层 selftest 通过")
        elif st:
            agent.fail("Lite 学习层 selftest 未通过", str(st)[:200])


def check_learning_swap(agent) -> None:
    """同一接口两档实现：两档契约一致、能力表同构、同一驱动代码跑得通。"""
    core_dir = agent.ctx.path("core")
    res = agent.ctx.probe("lite", LEARN_SWAP_CODE, timeout=120,
                          extra_path=[core_dir] if core_dir else None)
    data = _j(res)
    if data is None:
        agent.warn("跨档互换探测失败", (res.get("stderr") or "")[:250])
        return
    if data.get("fatal"):
        agent.skip("跨档互换验证跳过",
                   "当前解释器无法同时加载两档（多为无 torch）：%s" % data["fatal"][:160])
        return

    if data.get("api_same") and data.get("api"):
        agent.ok("两档声明同一学习接口", data["api"])
    else:
        agent.fail("两档学习接口标识不一致",
                   "core=%s" % data.get("api"))
    if data.get("req_same"):
        agent.ok("两档必需方法集一致")
    else:
        agent.fail("两档必需方法集不一致", "见 learning_conforms 定义")

    for key, label in (("core", "核心档"), ("lite", "教学档")):
        row = data.get(key) or {}
        if row.get("ok"):
            agent.ok("%s 通过契约校验" % label, "tier=%s kind=%s"
                     % (row.get("tier"), row.get("kind")))
        else:
            agent.fail("%s 契约校验失败" % label, "; ".join(row.get("problems", []))[:200])

    drive = data.get("drive") or []
    if len(drive) == 2 and all(not d.get("err") for d in drive):
        same_keys = drive[0]["api"] == drive[1]["api"]
        if same_keys:
            agent.ok("同一段调用方代码可驱动两档",
                     "bias 长度 %s / %s" % (drive[0]["bias_len"], drive[1]["bias_len"]))
        else:
            agent.fail("两档驱动结果不同构", str(drive)[:250])
    else:
        agent.fail("驱动两档时报错", str(drive)[:250])

    if data.get("caps_same"):
        agent.ok("两档能力表键同构（可互换）")
    else:
        agent.warn("两档能力表键不同构", "调用方若直接读能力键需自行兜底")


# ---------------------------------------------------------------- 5. 跨仓 parity
def check_parity(agent, pairs: Optional[List[tuple]] = None) -> None:
    """核心仓 vs Studio 仓的认知层文件是否逐字一致（忽略行尾差异）。

    默认比对 `pasm/cognitive/*.py`；这是"只在 Studio 实现了、核心没落盘"
    这类真实事故的守门检查。
    """
    pairs = pairs or [("core", "pasm/cognitive"), ("studio", "pasm/cognitive")]
    (k1, sub1), (k2, sub2) = pairs
    if not agent.ctx.has(k1, k2):
        agent.skip("跨仓一致性检查跳过", "缺少 %s 或 %s 仓" % (k1, k2))
        return
    # 退化判定：桌面端自 0.29.x 起并入核心仓，`studio` 键会解析到**同一个目录**。
    # 此时两侧逐字比对必然一致 —— 会报出一片"逐字一致"的**假绿**，
    # 让人以为守门还在工作。必须显式说明"这次没有对照物"，而不是给个 OK。
    if agent.ctx.path(k1) == agent.ctx.path(k2):
        agent.skip("跨仓一致性检查跳过（无对照物）",
                   "%s 与 %s 解析到同一个仓（%s）：桌面端已并入核心仓，"
                   "同名文件比对失去意义。同仓内部一致性请用核心仓的完整性守卫"
                   "（PASM/tools/verify_core_complete.py）"
                   % (k1, k2, agent.ctx.path(k1)))
        return
    d1, d2 = agent.ctx.rel(k1, *sub1.split("/")), agent.ctx.rel(k2, *sub2.split("/"))
    f1 = {p.name for p in d1.glob("*.py")} if d1.is_dir() else set()
    f2 = {p.name for p in d2.glob("*.py")} if d2.is_dir() else set()
    if not f1 and not f2:
        agent.skip("跨仓一致性检查跳过", "两侧都没有 %s" % sub1)
        return

    only1, only2 = sorted(f1 - f2), sorted(f2 - f1)
    if only1:
        agent.fail("核心仓独有、%s 缺失" % k2, ", ".join(only1))
    if only2:
        agent.warn("%s 独有、核心仓缺失" % k2, ", ".join(only2))
    if not only1 and not only2:
        agent.ok("两侧文件清单一致", "%d 个模块" % len(f1))

    drift = []
    for name in sorted(f1 & f2):
        try:
            a = agent.ctx.normalize_text(d1 / name)
            b = agent.ctx.normalize_text(d2 / name)
        except Exception as ex:                       # noqa: BLE001
            drift.append("%s(读取失败:%s)" % (name, ex))
            continue
        if a != b:
            drift.append(name)
    if drift:
        agent.fail("认知层存在内容漂移", "：%s" % ", ".join(drift))
    elif f1 & f2:
        agent.ok("认知层内容逐字一致", "%d 个模块" % len(f1 & f2))


# ---------------------------------------------------------------- 6. 冒烟闭环
SMOKE_CODE = r"""
import json
out = {}
try:
    import engine as E
    from engine_api import create, conforms, available
    out["available"] = available()
    okk, probs = conforms(create("pasm-lite"), strict=True)
    out["conforms"] = {"ok": bool(okk), "problems": list(probs)}
    eng = create("pasm-lite", seed=11)
    eng.reset_episode()
    a, rep = eng.act()
    out["act"] = {"action": int(a) if isinstance(a, int) else str(a),
                  "report_is_dict": isinstance(rep, dict)}
    lr = eng.learn(reward=0.5, next_obs=eng.obs())
    out["learn"] = {"returns_dict": isinstance(lr, dict)}
    snap = eng.snapshot()
    out["snapshot_sections"] = sorted(snap.keys())
    out["freeze_vae"] = hasattr(eng, "freeze_vae")
    try:
        eng.freeze_vae()
        out["freeze_vae_called"] = True
    except Exception as ex:
        out["freeze_vae_called"] = "ERR %s: %s" % (type(ex).__name__, ex)
except Exception as ex:
    out["fatal"] = "%s: %s" % (type(ex).__name__, ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""


def check_smoke(agent) -> None:
    """PASM-Lite 引擎端到端冒烟：create → act → learn → snapshot。"""
    res = agent.ctx.probe("lite", SMOKE_CODE, timeout=180)
    data = _j(res)
    if data is None:
        agent.fail("Lite 引擎冒烟失败", (res.get("stderr") or "")[:300])
        return
    if data.get("fatal"):
        agent.fail("Lite 引擎不可用", data["fatal"])
        return
    c = data.get("conforms") or {}
    if c.get("ok"):
        agent.ok("pasm-lite 契约一致性通过")
    else:
        agent.fail("pasm-lite 不符合契约", "; ".join(c.get("problems", []))[:250])
    if (data.get("act") or {}).get("report_is_dict"):
        agent.ok("act() 返回 (动作, report) 结构")
    else:
        agent.fail("act() 返回结构不符", str(data.get("act"))[:200])
    if (data.get("learn") or {}).get("returns_dict"):
        agent.ok("learn() 返回结构化结果")
    else:
        agent.fail("learn() 未返回 dict", str(data.get("learn"))[:200])
    secs = data.get("snapshot_sections") or []
    missing = [s for s in SNAPSHOT_SECTIONS if s not in secs]
    if missing:
        agent.warn("Lite 快照缺区块", "缺：%s" % ", ".join(missing))
    else:
        agent.ok("Lite 快照七区块齐全")
    if data.get("freeze_vae"):
        called = data.get("freeze_vae_called")
        if called is True:
            agent.ok("freeze_vae() 可调用")
        else:
            agent.warn("freeze_vae() 存在但调用异常", str(called)[:200])
    else:
        agent.warn("Lite 引擎未实现 freeze_vae()", "契约可选方法，建议补齐")


# ---------------------------------------------------------------- 7. env 插件化
ENV_CODE = r"""
import json
out = {}
try:
    import engine_api as ea
    out["api_env"] = [n for n in dir(ea) if "env" in n.lower() or "ENV" in n]
except Exception as ex:
    out["api_err"] = str(ex)
try:
    import envs
    out["envs_attrs"] = [n for n in dir(envs) if not n.startswith("_")]
except Exception as ex:
    out["envs_err"] = "%s: %s" % (type(ex).__name__, ex)
try:
    from engine_api import env_registry
    out["registry"] = env_registry()
except Exception:
    pass
print(SENTINEL + json.dumps(out, ensure_ascii=False, default=str))
"""


def check_env_plugins(agent) -> None:
    """Lite 侧环境是否已插件化（可换非网格环境）。"""
    data = _j(agent.ctx.probe("lite", ENV_CODE, timeout=90))
    if data is None:
        agent.fail("env 插件探测失败")
        return
    reg = data.get("registry")
    if isinstance(reg, dict) and reg:
        agent.ok("环境注册表可用", "已注册：%s" % ", ".join(sorted(reg)))
    elif isinstance(reg, list) and reg:
        agent.ok("环境注册表可用", "已注册：%s" % ", ".join(map(str, reg)))
    else:
        attrs = ", ".join(data.get("envs_attrs") or []) or "（envs 未导入）"
        agent.warn("未发现环境注册表 env_registry()",
                   "当前 envs 导出：%s" % attrs)


# ---------------------------------------------------------------- 8. 安全底线
SAFETY_CODE = r"""
import json, os
out = {"files": [], "hits": [], "errors": []}
PAT = ("safety", "guard", "crisis", "risk", "moderation", "compliance", "emergency", "harm")
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "build", "dist")]
    for f in files:
        if f.endswith(".py") and any(p in f.lower() for p in PAT):
            out["files"].append(os.path.join(root, f).replace("\\", "/"))
#: 只认真正的安全语义词。别放 `120` / `红线` 这种会撞上切片下标和
#: "质量红线" 之类业务词的短串 —— 那会让这条检查永远假绿。
KEY = ("自伤", "自杀", "危机干预", "未成年人保护", "隐私保护", "紧急联系人",
       "急救", "安全底线", "内容安全", "敏感词")
for root, dirs, files in os.walk("pasm"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(root, f)
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for k in KEY:
            if k in txt:
                out["hits"].append("%s:%s" % (p.replace("\\", "/"), k))
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""

#: 智能体/陪伴类应用必须覆盖的红线场景（认知引擎若不做，应用层必须做）
SAFETY_REDLINES = ("自伤/自杀风险识别", "医疗急救升级", "未成年人保护",
                   "隐私不外泄", "越权操作拦截")


def check_safety_readiness(agent) -> None:
    """安全底线：核心是否已落盘安全语义层。

    认知引擎本身可以不做安全过滤（那是应用层的活），但**必须有人说清谁来做**。
    这里只报事实，不替产品做决定。
    """
    data = _j(agent.ctx.probe("core", SAFETY_CODE, timeout=90))
    if data is None:
        agent.fail("安全底线探测失败")
        return
    files = data.get("files") or []
    hits = data.get("hits") or []
    if files:
        agent.ok("核心已落盘安全相关模块", "命中：%s" % ", ".join(files[:4]))
    elif hits:
        agent.ok("核心已出现安全语义线索", "命中 %d 处，如 %s" % (len(hits), hits[0]))
    else:
        agent.warn("核心侧尚无安全底线层",
                   "陪伴/NPC/教学场景需要覆盖：%s。"
                   "若由应用层（如 PASM Studio）承担，请在那侧确认并写入文档"
                   % "、".join(SAFETY_REDLINES))


# ------------------------------------------------- 2.5 记忆质量评测（LongMemEval 式）
#: 为什么要有这一段：此前套件对记忆层的覆盖是**零**——根因是探测只看模块里有没有
#: `selftest()` 可调用对象，而记忆层当时只有 `if __name__ == "__main__"` 的自检，
#: 于是"验 A 跑 B"：套件全绿，而实际在跑的桌面那份实现零覆盖，长期分叉没人发现。
#: 这段评测**断言行为而不是文件存在**，把记忆质量变成可回归的基线。
MEMORY_QUALITY_CODE = r"""
import json, os, tempfile, time
out = {"scenarios": [], "score": 0.0, "baseline": 1.0}

def case(name, ok, detail=""):
    out["scenarios"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:180]})

try:
    from pasm.cognitive import memory_layers as ML, facts as FA, worldmodel as WM
except Exception as ex:
    print(SENTINEL + json.dumps({"fatal": type(ex).__name__ + ": " + str(ex)}))
    raise SystemExit(0)

d = tempfile.mkdtemp(prefix="memq_")
try:
    ML.set_data_dir(d)

    # 1) 里程碑守恒：容量触顶时高重要度经历不能被日常琐事挤掉
    daily = [{"ts": "2026-01-01 00:00", "cat": "闲聊", "title": "日常%d" % i,
              "brief": "闲聊。", "tags": ["闲聊"], "sal": 1, "str_": 1.0,
              "hits": 0, "last_hit": 0.0, "imp": 0.5, "media": [],
              "vec": None, "vk": ""} for i in range(ML._EPI_CAP + 50)]
    ms = {"ts": "2020-01-01 00:00", "cat": "任务", "title": "里程碑",
          "brief": "用户第一次成功发布。", "tags": ["发布"], "sal": 5, "str_": 1.0,
          "hits": 0, "last_hit": 0.0, "imp": 0.5, "media": [], "vec": None, "vk": ""}
    lst = daily + [dict(ms)]
    ML._trim_episodes(lst)
    case("里程碑守恒（容量触顶不被挤出）",
         len(lst) == ML._EPI_CAP and any(e.get("title") == "里程碑" for e in lst),
         "裁剪后 %d 条" % len(lst))
    # 对照组：同权时按新旧淘汰 —— 证明是「重要度」在起作用，不是巧合
    ctrl = daily + [dict(ms, sal=1)]
    ML._trim_episodes(ctrl)
    case("同权淘汰对照组（重要度确实在起作用）",
         not any(e.get("title") == "里程碑" for e in ctrl))

    # 2) 只巩固被召回的条目（防止"沾边即巩固"把遗忘曲线拉平）
    for i in range(3):
        ML.episode_push("记账本项目·第%d期" % (i + 1), "围绕记账本项目做迭代。",
                        ["记账本", "项目"], "任务", salience=1)
    ML.recall_layers("记账本项目进展", top=1)
    bumped = [e for e in ML.episodes() if int(e.get("hits", 0)) > 0]
    case("只巩固被召回的条目", len(bumped) == 1, "被巩固 %d 条（期望 1）" % len(bumped))

    # 3) 重要度参数真的生效（统一签名 episode_push(salience=)）
    ML.episode_push("里程碑·签名", "写入一条高重要度经历。", ["测试"], "任务", salience=5)
    eps = ML.episodes()
    case("episode_push 接受并保存 salience",
         bool(eps) and int(eps[0].get("sal", 1)) == 5)

    # 4) 双时态：新事实覆盖旧事实，旧的失效但不删除
    FA.fact_put("居住地", "北京", "我住在北京", kind="location")
    r = FA.fact_put("居住地", "上海", "我搬到上海了", kind="location")
    act = [f["value"] for f in FA.active_facts()]
    case("矛盾检测：新事实取代旧事实", r.get("action") == "updated" and act == ["上海"],
         "当前有效=%s" % act)
    case("双时态：旧事实可追溯", 
         sorted(f["status"] for f in FA.fact_history("居住地")) == ["active", "superseded"])

    # 5) 过期事实绝不进检索结果（对标 Zep 双时态图的能力项）
    vals = [f["value"] for f in FA.facts_recall("我现在住哪儿")]
    case("过期事实不被召回", "上海" in vals and "北京" not in vals, "召回=%s" % vals)

    # 6) 意图词别名通道：问句里没有"居住地"三个字也要命中
    case("意图别名召回（住哪 → 居住地）", len(FA.facts_recall("我住哪儿")) > 0)

    # 7) 计划类事实到期 → 时序自更新（要去 → 去过）
    FA.fact_put("计划·明天", "北京", "我明天要去北京", kind="plan", due="明天")
    n = FA.expire_plans(now=time.time() + 3 * 86400)
    later = time.time() + 3 * 86400
    case("计划到期自动改写成已发生",
         n == 1 and any("已发生" in f["subject"] for f in FA.active_facts(later))
         and not any(f["kind"] == "plan" for f in FA.active_facts(later)), "改写 %d 条" % n)

    # 8) 事实层经记忆层召回通道进入提示词
    blk = ML.recall_layers("我现在住哪儿")
    case("事实层进入召回文本", "上海" in blk and "北京" not in blk)

    # 9) 世界模型：从办事历史学出前向预测（W1）
    ctx = "帮我写个脚本统计字数"
    for _ in range(4):
        WM.observe(ctx, "script", True, "跑通了")
    WM.observe(ctx, "script", False, "报错")
    p = WM.predict(ctx, "script")
    case("W1 动作后果表：成功率高于先验", 0.6 < p < 0.95, "p=%.3f" % p)
    case("W1 没数据就说不知道（返回先验）",
         abs(WM.predict(ctx, "根本没见过的动作") - WM.PRIOR) < 1e-6)

    # 10) 领域回退：同类新任务也要有估计（不是只会背原题）
    fresh = "帮我把昨天那份日志跑一遍脚本"
    case("W1 领域回退（新任务也能估）",
         WM.domain_of(fresh) == "脚本" and abs(WM.predict(fresh, "script") - WM.PRIOR) > 1e-6)

    # 11) W2 脑内预演：整体成功率 = 各步之积
    r2 = WM.rollout(["script", "script"], ctx)
    case("W2 预演乘积正确", abs(r2["p"] - round(p * p, 4)) < 1e-3, "p=%s" % r2["p"])

    # 12) 多模态条目（P3）：挂了图仍然能被文本召回，且不崩
    ML.episode_push("给用户做的海报", "生成了一张发布会海报。", ["海报", "图片"],
                    "任务", salience=3, media=["C:/tmp/poster_final.png"])
    case("多模态条目可文本召回", "海报" in ML.recall_layers("那张海报"))

    # 13) 写盘去抖后仍能落盘（P0.5）
    ML.flush(force=True)
    case("去抖写盘可强制落地", os.path.exists(os.path.join(d, "episodic.json")))

    # ---- 以下 5 项来自 2026-09-14 的对抗式重检测（tools/audit_memory_worldmodel.py）----
    # 14) 别名**精度**：单字别名会误命中（"记住…"里含"住"）——必须归零
    case("别名精度：单字别名不误命中",
         FA._alias_score("记住我明天要去医院复查", {"subject": "居住地"}) == 0)

    # 15) 跨关系不串味：某一门亲戚的别名只应是它自己
    FA.fact_put("关系·老伴", "李秀兰", kind="relation")
    FA.fact_put("关系·儿子", "张伟", kind="relation")
    rel = [f["subject"] for f in FA.facts_recall("我儿子叫什么")]
    case("跨关系不串味（问儿子不带出老伴）",
         FA._aliases("关系·老伴") == ["老伴"] and "关系·老伴" not in rel,
         "别名=%s 召回=%s" % (FA._aliases("关系·老伴"), rel))

    # 16) 同句多事实按**文本位置**去重（后说的为准，不是按规则表顺序）
    mv = [c["value"] for c in FA.extract_facts("我搬到上海了，不过我现在住在北京")
          if c["subject"] == "居住地"]
    case("同句多事实按文本位置去重", mv == ["北京"], "抽到=%s" % mv)

    # 17) 置信度门：低置信度新说法不得推翻已确认事实，只挂起待确认
    FA.fact_put("过敏源", "青霉素", conf=0.95, src="manual")
    rp = FA.fact_put("过敏源", "花粉", conf=0.3, src="chat")
    al2 = [f["value"] for f in FA.active_facts() if f["sid"] == FA._norm_key("过敏源")]
    case("低置信度不覆盖已确认事实（挂起待确认）",
         rp.get("action") == "pending" and al2 == ["青霉素"],
         "action=%s 有效=%s" % (rp.get("action"), al2))

    # 18) 别名表升级后，**已落盘的旧条目**不再沿用坏别名
    FA.fact_put("居住地", "广州", "我住在广州", kind="location")
    _p = os.path.join(d, "facts.json")
    _raw = json.load(open(_p, encoding="utf-8"))
    for _f in _raw:
        if _f.get("subject") == "居住地":
            _f["keys"], _f["alias_ver"] = ["住"], 1          # 模拟旧版残留
    json.dump(_raw, open(_p, "w", encoding="utf-8"), ensure_ascii=False)
    case("别名表升级后旧条目就地重算",
         not any(f["subject"] == "居住地" for f in FA.facts_recall("记住我明天去医院")))

    # 19) 跨表述检索的"默认档"：口语问法要能对上记忆里的规范标签
    ML.episode_push("本人信息", "陈秀兰，78 岁，住老街 3 号院",
                    ["姓名", "年龄", "住址"], "陪伴", salience=5)
    blk2 = ML.recall_layers("我叫什么名字")
    case("口语问法能召回规范标签（意图同义通道）",
         bool(blk2) and ("姓名" in blk2 or "陈秀兰" in blk2))

    # 20) 领域词表能区分日常场景（否则领域层退化，分层回退失效）
    case("W1 日常领域可区分（生活 / 健康 / 家人）",
         WM.domain_of("出门买菜") == "生活"
         and WM.domain_of("去医院复查挂号") == "健康"
         and WM.domain_of("给女儿打电话") == "家人")

    # 21) 三层回退：本领域无记录、但该动作在别领域有经验 → 弱先验而非 0.5
    WM.reset()
    for _ in range(12):
        WM.observe("出门买菜带不带伞", "带伞", True)
    p_same, p_cross = (WM.predict("出门买菜带不带伞", "带伞"),
                       WM.predict("去医院复查挂号排队", "带伞"))
    case("三层回退：跨领域弱先验（优于一律 0.5）",
         WM.PRIOR < p_cross < p_same,
         "同领域 %.4f / 跨领域 %.4f" % (p_same, p_cross))
except Exception as ex:
    case("评测过程未抛异常", False, type(ex).__name__ + ": " + str(ex))
# 刻意**不**把数据目录改回去：本探针跑在一次性子进程里，改回去反而可能
# 往用户真实目录写东西。让进程带着临时目录退出最安全。

ok = [c for c in out["scenarios"] if c["ok"]]
out["score"] = round(len(ok) / max(len(out["scenarios"]), 1), 4)
out["failed"] = [c for c in out["scenarios"] if not c["ok"]]
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""


def check_memory_quality(agent) -> None:
    """记忆质量评测：把"记得对不对"变成可回归的分数（P0.4 + P1.4）。

    断言的是**行为**：里程碑守恒、只巩固被召回的、双时态不召回过期事实、
    意图别名、计划到期改写、世界模型前向预测与领域回退、多模态条目。
    这堵住了"验 A 跑 B"——套件测的与产品跑的是**同一份**核心实现。
    """
    data = _j(agent.ctx.probe("core", MEMORY_QUALITY_CODE, timeout=150))
    if data is None:
        agent.fail("记忆质量评测探测失败")
        return
    fatal = data.get("fatal")
    if fatal:
        agent.fail("记忆质量评测无法运行", str(fatal)[:250])
        return
    sc = data.get("scenarios") or []
    failed = data.get("failed") or []
    score = float(data.get("score") or 0.0)
    if not sc:
        agent.fail("记忆质量评测没有产出任何场景")
        return
    if failed:
        agent.fail("记忆质量评测未达标（%.0f%%）" % (score * 100),
                   "失败 %d/%d：%s" % (
                       len(failed), len(sc),
                       "；".join("%s（%s）" % (c["name"], c.get("detail") or "无细节")
                                 for c in failed[:4])))
    else:
        agent.ok("记忆质量评测 %d/%d 全过" % (len(sc), len(sc)),
                 "基线 %.1f：里程碑守恒 / 只巩固被召回的 / 双时态 / 别名 / "
                 "计划自更新 / 世界模型 / 多模态" % float(data.get("baseline") or 1.0))


# ---------------------------------------------------------------- 汇总用
def all_checks(agent) -> None:
    """跑一遍全部基础检查（core-verifier 的默认配方）。"""
    check_contract(agent)
    check_cognitive_layers(agent)
    check_symbolic_loop(agent)
    check_memory_quality(agent)
    check_learning_contract(agent)
    if agent.ctx.has("core") and agent.ctx.has("lite"):
        check_learning_swap(agent)
    else:
        agent.skip("跨档互换验证跳过", "需要 core 与 lite 两仓同时在位")
    check_env_plugins(agent)
    check_safety_readiness(agent)
    if agent.ctx.has("lite"):
        check_smoke(agent)
