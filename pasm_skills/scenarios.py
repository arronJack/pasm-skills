"""scenarios.py —— 领域场景仿真底座。

为什么需要它
------------
`core-verifier` 查的是**结构**（文件在不在、契约满不满足）；
而"游戏 NPC / 老人陪伴 / 学习陪伴"这类智能体要查的是**行为**——
记忆会不会忘、情绪会不会漂、行为会不会僵化、跑久了会不会垮。
行为只能在"跑一段场景"之后才看得出来。

本模块提供三样公共能力，让每个领域智能体只写"它自己的场景"：

1. **子进程 prelude**：把 `entropy / topk_by / bounded / max_jump` 等度量工具
   注入到隔离探测进程里（与 `checks.py` 里的内嵌代码同一套机制）；
2. **解释器择优**：优先挑一个能 `import torch` 的解释器（能驱动仿生层），
   挑不到就如实降级到轻量核心，并把"降级"写进结论，绝不假装覆盖了；
3. **指标判定**：把场景产出的指标字典 + 阈值表，翻译成 `OK/WARN/FAIL/SKIP` 结论。

一条设计红线
------------
**场景必须跑在真实核心组件上**。这里不提供任何"自研替身"的兜底实现——
否则就成了"看起来验证了，其实验的是自己写的假货"。
核心组件拿不到时，正确做法是 `SKIP` 并说明原因，而不是换个假的接着跑。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: 本机私有配置（已进 .gitignore）。**公开仓里不留任何个人解释器路径**，
#: 需要固定某个带 torch 的解释器时，在仓库根写 `pasm-skills.local.json`：
#:     {"python": ["/path/to/python", "C:/another/python.exe"]}
#: 它只影响本机，不会随仓库分发出去。
LOCAL_CONF = "pasm-skills.local.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------- prelude
#: 注入到子进程的公共工具。随每个场景一起下发，保持"自包含"。
PRELUDE = r'''
import json, math, os, shutil, tempfile, time
from collections import Counter

try:                       # 能不能驱动仿生层，由这个开关决定（结论里要如实标注）
    import torch           # noqa: F401
    TORCH_OK = True
except Exception:
    TORCH_OK = False

def emit(obj):
    """把场景结果回传父进程（SENTINEL 由 probe 的引导代码定义）。"""
    print(SENTINEL + json.dumps(obj, ensure_ascii=False, default=str))

def entropy(counts):
    """香农熵（bit）。counts 为 {项: 次数}。"""
    tot = float(sum(counts.values())) or 1.0
    e = 0.0
    for v in counts.values():
        if v <= 0:
            continue
        p = v / tot
        e -= p * math.log(p, 2)
    return e

def norm_entropy(counts):
    """归一化熵：0 = 恒定不变，1 = 完全均匀。用于判断"行为是否僵化"。"""
    n = len([k for k, v in counts.items() if v > 0])
    if n <= 1:
        return 0.0
    return entropy(counts) / math.log(n, 2)

def tv_distance(a, b):
    """两个离散分布的总变差距离（0 = 相同，1 = 完全不相交）。"""
    keys = set(a) | set(b)
    ta = float(sum(a.values())) or 1.0
    tb = float(sum(b.values())) or 1.0
    return 0.5 * sum(abs(a.get(k, 0) / ta - b.get(k, 0) / tb) for k in keys)

def topk_by(query, texts, k=5):
    """用核心 memvec 做语义 top-k 召回，返回 [(序号, 相似度)]。"""
    from pasm.cognitive import memvec
    qv = memvec.embed(query)
    scored = [(memvec.cosine(qv, memvec.embed(t)), i) for i, t in enumerate(texts)]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:k]

def hits_in(query, texts, k=5, want=None):
    """top-k 里是否命中 want（下标集合）；want 为空则返回 top-k 本身。"""
    r = topk_by(query, texts, k)
    idx = [i for _, i in r]
    if want is None:
        return idx
    return len([i for i in idx if i in want])

def ghost_max(query, texts):
    """检索一个"根本不相关"的话题时能拿到的最高相似度。

    这个值必须很低 —— 高了说明检索会把无关记忆硬塞进上下文，
    那是"AI 一本正经胡说八道"的温床。"""
    r = topk_by(query, texts, k=1)
    return r[0][0] if r else 0.0

def bounded(series, lo=-3.0, hi=3.0):
    """序列是否全部落在 [lo, hi] 内。"""
    return all(lo <= float(x) <= hi for x in series)

def max_jump(series):
    """相邻两步的最大绝对跳变（检测"情绪瞬移"）。"""
    if len(series) < 2:
        return 0.0
    return max(abs(float(series[i + 1]) - float(series[i])) for i in range(len(series) - 1))

def span(series):
    return (max(series) - min(series)) if series else 0.0

def mean(xs):
    xs = list(xs)
    return sum(xs) / float(len(xs)) if xs else 0.0

def rate(hit, total):
    return float(hit) / float(total) if total else 0.0

def slope(series):
    """最小二乘斜率（判断情绪是在回升还是在滑落）。"""
    n = len(series)
    if n < 2:
        return 0.0
    mx = (n - 1) / 2.0
    my = mean(series)
    num = sum((i - mx) * (series[i] - my) for i in range(n))
    den = sum((i - mx) ** 2 for i in range(n))
    return num / den if den else 0.0

def temp_layers(prefix="pasm_sk_"):
    """把分层记忆指向临时目录，绝不碰用户真实数据。"""
    from pasm.cognitive import memory_layers as ML
    d = tempfile.mkdtemp(prefix=prefix)
    ML.set_data_dir(d)
    return d, ML

def cleanup(d):
    try:
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass

def toc():
    return time.perf_counter()
'''

#: 场景代码默认回传的载荷哨兵（复用 probe 的解析）
SCENARIO_KIND = "pasm-skills/scenario@1"


# ---------------------------------------------------------------- 解释器择优
_PY_EXISTS: Dict[str, bool] = {}
_TORCH_OK: Dict[str, bool] = {}


def _resolve(python: str) -> Optional[str]:
    """把解释器名字/路径解析成可执行文件；不存在返回 None。"""
    if python in _PY_EXISTS:
        return python if _PY_EXISTS[python] else None
    p = python
    if os.path.sep not in p and "/" not in p:
        p = shutil.which(p) or ""
    ok = bool(p) and os.path.isfile(p)
    _PY_EXISTS[python] = ok
    return p if ok else None


def has_torch(python: str, timeout: int = 90) -> bool:
    """该解释器能否 import torch（带缓存，探测一次 ~2s）。"""
    if python in _TORCH_OK:
        return _TORCH_OK[python]
    ok = False
    try:
        proc = subprocess.run([python, "-c", "import torch"],
                              capture_output=True, timeout=timeout)
        ok = proc.returncode == 0
    except Exception:                                  # noqa: BLE001
        ok = False
    _TORCH_OK[python] = ok
    return ok


def local_pythons() -> List[str]:
    """读仓库根的 `pasm-skills.local.json` 里的本机解释器。

    存在的理由：能驱动仿生档的那个解释器往往在仓库外（某个 venv / 托管运行时）。
    把它写进代码会泄露个人路径、对别人也无效；写进环境变量又跨不了终端。
    放一个**已被 gitignore 的**本机配置文件，两边都顾上。
    """
    out: List[str] = []
    try:
        conf = _repo_root() / LOCAL_CONF
        if conf.is_file():
            data = json.loads(conf.read_text(encoding="utf-8"))
            v = data.get("python")
            if isinstance(v, str):
                v = [v]
            for item in (v or []):
                if item:
                    # 支持 %%HOME%% 占位，配置文件里就不用写死用户名
                    out.append(str(item).replace("%%HOME%%", str(Path.home())))
    except Exception:                                  # noqa: BLE001
        pass                                           # 配置坏了不该让验证跑不起来
    return out


def candidate_pythons() -> List[str]:
    """候选解释器，按优先级：

    显式环境变量 → 本机私有配置 → 当前解释器 → 仓库内 venv → PATH。
    """
    out: List[str] = []
    for key in ("PASM_TORCH_PYTHON", "PASM_PYTHON"):
        v = os.environ.get(key)
        if v:
            out.append(v)
    out.extend(local_pythons())
    out.append(sys.executable)
    # 仓库内自带的虚拟环境：可移植，而且通常就是装了 torch 的那个
    root = _repo_root()
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python",
                "venv/Scripts/python.exe", "venv/bin/python"):
        out.append(str(root / rel))
    if os.name == "nt":
        out.append("py")                               # Windows 启动器
    out.append("python3")
    out.append("python")
    seen, res = set(), []
    for c in out:
        if c and c not in seen:
            seen.add(c)
            res.append(c)
    return res


def choose_python(ctx: Any = None, prefer_torch: bool = True,
                  timeout: int = 90) -> Tuple[str, bool]:
    """挑一个最合适的解释器。

    返回 `(python, torch_ok)`。`prefer_torch=True` 时优先挑能 import torch 的；
    找不到就退回当前解释器并如实返回 `torch_ok=False`（由调用方写进结论）。
    """
    explicit = os.environ.get("PASM_PYTHON")
    if explicit and _resolve(explicit):
        return explicit, has_torch(explicit, timeout)
    if prefer_torch:
        for c in candidate_pythons():
            p = _resolve(c)
            if p and has_torch(p, timeout):
                return p, True
    fallback = (explicit or sys.executable)
    return fallback, has_torch(fallback, timeout)


# ---------------------------------------------------------------- 场景执行
def run_scenario(ctx: Any, body: str, *, repo: str = "core",
                 python: Optional[str] = None, timeout: int = 300,
                 extra_path: Optional[List[str]] = None) -> Dict[str, Any]:
    """在隔离子进程里跑一段场景代码（自动带上 PRELUDE）。

    场景代码用 `emit({...})` 回传指标字典；返回 `probe()` 的原始结果，
    其 `json` 字段即指标字典（解析失败为 None）。
    """
    return ctx.probe(repo, PRELUDE + "\n" + body, timeout=timeout,
                     extra_path=extra_path, python=python)


def metrics_of(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从 probe 结果里取指标字典；顺便把 stderr 尾部带出来便于排查。"""
    if result is None:
        return None
    return result.get("json")


def failure_detail(result: Dict[str, Any], limit: int = 300) -> str:
    """探测失败时给人看的一句话原因。"""
    if not result:
        return "无返回"
    err = (result.get("stderr") or "").strip()
    if err:
        return err[-limit:]
    return "退出码 %s（无 stderr）" % result.get("rc")


# ---------------------------------------------------------------- 指标判定
def _range(lo: Optional[float], hi: Optional[float]) -> str:
    if lo is not None and hi is not None:
        return "%s ~ %s" % (lo, hi)
    if lo is not None:
        return "≥ %s" % lo
    if hi is not None:
        return "≤ %s" % hi
    return "—"


def judge(agent: Any, metrics: Dict[str, Any], spec: List[Dict[str, Any]],
          tier: str = "") -> int:
    """把指标 + 阈值表翻译成结论。

    spec 每项：`{"key","title","lo","hi","bad","fmt","note"}`
      · `lo/hi`：合格区间（单边可省）
      · `bad` ：越界时记 `warn`（默认）还是 `fail`
      · `fmt` ：展示格式，如 `"{:.3f}"`

    返回越界项数（供调用方汇总）。
    """
    bad_count = 0
    for item in spec:
        key = item["key"]
        title = item.get("title", key)
        val = metrics.get(key)
        fmt = item.get("fmt")
        if val is None:
            agent.skip(title, "场景未产出该指标（%s）" % key)
            continue
        try:
            shown = fmt.format(val) if fmt else str(val)
        except Exception:                              # noqa: BLE001
            shown = str(val)
        lo, hi = item.get("lo"), item.get("hi")
        note = item.get("note", "")
        good = True
        if lo is not None and float(val) < float(lo):
            good = False
        if hi is not None and float(val) > float(hi):
            good = False
        tail = ("  " + note) if note else ""
        if tier:
            tail += "  [%s]" % tier
        if good:
            agent.ok(title, "实测 %s（合格 %s）%s" % (shown, _range(lo, hi), tail))
        else:
            bad_count += 1
            msg = "实测 %s（要求 %s）%s" % (shown, _range(lo, hi), tail)
            if item.get("bad") == "fail":
                agent.fail(title, msg)
            else:
                agent.warn(title, msg)
    return bad_count
