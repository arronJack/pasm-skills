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
    1. 环境变量：PASM_CORE / PASM_STUDIO / PASM_LITE
    2. 约定路径：E:/AI/PASM、E:/AI/pasm_qclaw、E:/AI/PASM_LITE
    3. 从 `PASM_SKILLS_ROOTS`（分号分隔）逐层向下搜同名目录
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

#: 仓键 -> (环境变量名, 默认绝对路径, 判定"这是个仓"的标志文件)
REPO_SPEC: Dict[str, tuple] = {
    "core":   ("PASM_CORE",   "E:/AI/PASM",       "pasm/__init__.py"),
    "studio": ("PASM_STUDIO", "E:/AI/pasm_qclaw", "desktop/pasm_companion.py"),
    "lite":   ("PASM_LITE",   "E:/AI/PASM_LITE",  "pasm_lite.py"),
}

SENTINEL = "@@PASM_SKILLS_JSON@@"


class RepoContext:
    """三仓的定位与只读访问。"""

    def __init__(self, roots: Optional[List[str]] = None):
        self._paths: Dict[str, Optional[Path]] = {}
        self._roots = roots or self._env_roots()
        for key in REPO_SPEC:
            self._paths[key] = self._locate(key)

    # ------------------------------------------------------------ 定位
    @staticmethod
    def _env_roots() -> List[str]:
        raw = os.environ.get("PASM_SKILLS_ROOTS", "")
        roots = [p for p in raw.split(os.pathsep) if p.strip()]
        roots += ["E:/AI", str(Path.home() / "AI")]
        seen, out = set(), []
        for r in roots:
            rp = os.path.abspath(r)
            if rp not in seen and os.path.isdir(rp):
                seen.add(rp)
                out.append(rp)
        return out

    def _locate(self, key: str) -> Optional[Path]:
        env_name, default, marker = REPO_SPEC[key]
        explicit = os.environ.get(env_name)
        cands: List[Path] = []
        if explicit:
            cands.append(Path(explicit))
        cands.append(Path(default))
        for c in cands:
            if (c / marker).exists():
                return c.resolve()
        # 兜底：在 roots 下按目录名找
        wanted = Path(default).name
        for root in self._roots:
            for c in (Path(root) / wanted, Path(root) / wanted.lower()):
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
        return {k: (str(v) if v else None) for k, v in self._paths.items()}

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
        """用于探测的解释器：PASM_PYTHON 优先，否则当前解释器。"""
        return os.environ.get("PASM_PYTHON") or sys.executable

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
