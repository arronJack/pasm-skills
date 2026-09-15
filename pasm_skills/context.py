"""仓库上下文 —— 定位 PASM 三仓，并提供"隔离探测"能力。

为什么要隔离探测
----------------
长期验证最怕"验证脚本自己把环境搞脏"：
本项目要同时检查核心仓（`pasm/`）、Studio 仓（`desktop/`）、教学仓（PASM-Lite），
三者存在**同名模块**（symbolic/memrouter/learning...）。若在同一解释器里逐个
import，`sys.modules` 会互相顶掉，结论就不可信了。

所以每次检查都在**独立子进程**里跑：干净的解释器 + 明确的 cwd + 结构化 JSON 回传。
代价是慢几十毫秒，换来的是结论可复现。

定位顺序（每个仓各自决定）：
    1. 环境变量：PASM_CORE / PASM_STUDIO / PASM_LITE（直接给绝对路径）
    2. 生态根目录 × 该仓的目录名（见 `REPO_SPEC` 与 `_ecosystem_roots()`）
    3. 从 `PASM_SKILLS_ROOTS`（分号分隔）逐层向下搜同名目录

生态根目录怎么来的（**不写死盘符**）
----------------------------------
2026-09-15 的教训：生态在**公司机（`E:\\AI\\pasm`）**与**家机（`H:\\pasm`）**
之间来回拷贝，而这里原先写死了 `E:/AI/PASM`、`E:/AI/pasm_qclaw`、
`E:/AI/PASM_LITE` 三个"约定路径" —— 换到任何别的布局，三仓全部定位失败，
所有依赖仓的智能体集体静默跳过。

现在改为按优先级自动发现：
    1. `PASM_SKILLS_ROOTS` / `PASM_HOME` / `PASM_ROOT` / `PASM_CODE`
    2. 本包自身位置：`<生态根>/pasm-skills/pasm_skills/context.py`
       → 上溯两级即得生态根（源码布局下永远正确）
    3. 当前工作目录逐级上溯（从某个仓内部运行脚本时同样有效）
    4. `~/AI`、`E:/AI`（历史布局，仅兜底）
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

#: 仓键 -> (环境变量名, 仓目录名候选, 判定"这是个仓"的标志文件)
#:
#: 注意 `core` 与 `studio` 的目录名候选相同：桌面端自 0.29.x 起已并入核心仓
#: （`desktop/` 就在 `PASM/` 里），但为兼容历史上分仓的
#: `pasm_qclaw/desktop/pasm_companion.py` 布局，这里两个名字都留着。
REPO_SPEC: Dict[str, tuple] = {
    "core":   ("PASM_CORE",   ("PASM", "pasm"),
               "pasm/__init__.py"),
    "studio": ("PASM_STUDIO", ("PASM", "pasm_qclaw", "pasm-qclaw", "pasm_qclaw_release"),
               "desktop/pasm_companion.py"),
    "lite":   ("PASM_LITE",   ("PASM-Lite", "PASM_LITE", "pasm-lite"),
               "pasm_lite.py"),
}

SENTINEL = "@@PASM_SKILLS_JSON@@"


def _ecosystem_roots() -> List[str]:
    """按优先级收集"生态根目录"候选（去重、只保留存在的目录）。"""
    roots: List[str] = []

    def add(path) -> None:
        if not path:
            return
        try:
            rp = os.path.abspath(os.path.expanduser(str(path)))
        except Exception:                                  # noqa: BLE001
            return
        if rp not in roots and os.path.isdir(rp):
            roots.append(rp)

    raw = os.environ.get("PASM_SKILLS_ROOTS", "")
    for p in raw.split(os.pathsep):
        if p.strip():
            add(p.strip())
    for key in ("PASM_HOME", "PASM_ROOT", "PASM_CODE"):
        add(os.environ.get(key))

    # 本包自身位置：<生态根>/pasm-skills/pasm_skills/context.py
    here = Path(__file__).resolve()
    add(here.parent.parent.parent)          # 生态根
    add(here.parent.parent.parent.parent)   # 生态根的父级
    add(here.parent.parent)                 # 仓根

    # 从 CWD 逐级上溯（脚本常在某个仓内部运行）
    try:
        cur = Path.cwd().resolve()
    except OSError:
        cur = None
    if cur:
        for _ in range(5):
            add(cur)
            if cur.parent == cur:
                break
            cur = cur.parent

    add(Path.home() / "AI")                 # 普通家目录布局
    add("E:/AI")                            # 历史遗留，仅兜底
    return roots


class RepoContext:
    """三仓的定位与只读访问。"""

    def __init__(self, roots: Optional[List[str]] = None):
        self._paths: Dict[str, Optional[Path]] = {}
        self._roots = list(roots) if roots else _ecosystem_roots()
        for key in REPO_SPEC:
            self._paths[key] = self._locate(key)

    # ------------------------------------------------------------ 定位
    def _locate(self, key: str) -> Optional[Path]:
        env_name, dirnames, marker = REPO_SPEC[key]
        explicit = os.environ.get(env_name)
        if explicit and (Path(explicit) / marker).exists():
            return Path(explicit).resolve()
        for root in self._roots:
            for name in dirnames:
                c = Path(root) / name
                if (c / marker).exists():
                    return c.resolve()
        return None

    # ------------------------------------------------------------ 访问
    def path(self, key: str) -> Optional[Path]:
        return self._paths.get(key)

    def has(self, *keys: str) -> bool:
        return all(self._paths.get(k) is not None for k in keys)

    def require(self, key: str) -> Path:
        p = self._paths.get(key)
        if p is None:
            raise FileNotFoundError("找不到仓库 %r（可用环境变量 %s 指定）"
                                    % (key, REPO_SPEC[key][0]))
        return p

    def rel(self, key: str, *parts: str) -> Optional[Path]:
        """仓内相对路径 → 绝对路径（不以存在为前提）。"""
        p = self._paths.get(key)
        return (p.joinpath(*parts)) if p else None

    def exists(self, key: str, *parts: str) -> bool:
        p = self.rel(key, *parts)
        return bool(p and p.exists())

    def resolve_existing(self, *candidates: str) -> Optional[Path]:
        """在任一仓里找第一个存在的相对路径（用于"文件可能在这仓也可能在那仓"）。"""
        for key in REPO_SPEC:
            p = self.rel(key, *candidates)
            if p and p.exists():
                return p
        return None

    def describe(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {k: (str(v) if v else None) for k, v in self._paths.items()}
        # 顺带把"搜索了哪些根目录"一并给出：定位失败时这是唯一能自证的线索
        d["roots"] = list(self._roots)
        return d

    @property
    def roots(self) -> List[str]:
        """本次定位使用的生态根目录候选（调试/报错用）。"""
        return list(self._roots)

    # ------------------------------------------------------------ 文件工具
    @staticmethod
    def sha256(path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def normalize_text(path) -> str:
        """读文本并统一换行，跨平台比对用（忽略 CRLF/LF 差异）。"""
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().replace("\r\n", "\n").replace("\r", "\n")

    # ------------------------------------------------------------ 探测
    def python(self) -> str:
        """用于探测的解释器。

        `PASM_PYTHON` 优先；否则沿用与领域场景**完全同一套**择优逻辑
        （`scenarios.choose_python`，优先带 torch 的解释器）。

        为什么要统一：同一份基线，用带 torch 的解释器采集（PASM-Lite 的
        具体引擎会注册）和用不带 torch 的采集（拿不到），结果天然不同。
        两边不统一，就会把"换了解释器"误报成"能力消失"。
        """
        explicit = os.environ.get("PASM_PYTHON")
        if explicit:
            return explicit
        cached = getattr(self, "_py_cache", None)
        if cached:
            return cached
        py = sys.executable
        try:
            from .scenarios import choose_python
            py = choose_python(self, prefer_torch=True)[0]
        except Exception:                              # noqa: BLE001
            py = sys.executable
        self._py_cache = py
        return py

    def probe(self, repo_key: str, code: str, timeout: int = 90,
              extra_path: Optional[List[str]] = None,
              python: Optional[str] = None) -> Dict[str, Any]:
        """在指定仓目录下、用**独立解释器**跑一段代码。

        代码里 `print(SENTINEL + json.dumps(obj))` 的结构化结果会被解析到
        `result["json"]`；其余 stdout/stderr 原样保留便于排查。

        返回 {"rc": int|None, "json": obj|None, "stdout": str, "stderr": str}
        """
        base = self._paths.get(repo_key)
        if base is None:
            return {"rc": None, "json": None, "stdout": "",
                    "stderr": "仓库 %s 未找到" % repo_key}

        paths = [str(base)] + [str(Path(p)) for p in (extra_path or [])]
        boot = ("import sys, json\n"
                "for _p in %r:\n"
                "    sys.path.insert(0, _p)\n"
                "SENTINEL = %r\n" % (paths, SENTINEL))
        script = boot + code

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env.pop("PYTHONPATH", None)
        try:
            proc = subprocess.run(
                [python or self.python(), "-c", script],
                cwd=str(base), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            return {"rc": None, "json": None, "stdout": "",
                    "stderr": "探测超时（%ss）" % timeout}
        except Exception as ex:                       # noqa: BLE001
            return {"rc": None, "json": None, "stdout": "",
                    "stderr": "%s: %s" % (type(ex).__name__, ex)}

        payload = None
        keep: List[str] = []
        for line in (proc.stdout or "").splitlines():
            if line.startswith(SENTINEL):
                try:
                    payload = json.loads(line[len(SENTINEL):])
                except Exception:                     # noqa: BLE001
                    payload = None
            else:
                keep.append(line)
        return {"rc": proc.returncode, "json": payload,
                "stdout": "\n".join(keep).strip(),
                "stderr": (proc.stderr or "").strip()}
