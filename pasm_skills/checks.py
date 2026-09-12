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
                          "coder", "selfheal", "mathlab", "percept", "quantum")

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


# ---------------------------------------------------------------- 汇总用
def all_checks(agent) -> None:
    """跑一遍全部基础检查（core-verifier 的默认配方）。"""
    check_contract(agent)
    check_cognitive_layers(agent)
    check_symbolic_loop(agent)
    check_learning_contract(agent)
    if agent.ctx.has("core") and agent.ctx.has("lite"):
        check_learning_swap(agent)
    else:
        agent.skip("跨档互换验证跳过", "需要 core 与 lite 两仓同时在位")
    check_env_plugins(agent)
    if agent.ctx.has("lite"):
        check_smoke(agent)
