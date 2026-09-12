"""regression —— 事实指纹与基线对比。

长期验证真正要回答的问题是：**"上周还好好的，今天有没有退化？"**
所以本智能体不判断"对错"，只做两件事：

  1. `--update`：把当前事实（认知层文件指纹 + 引擎清单 + 契约版本）存成基线；
  2. 无参数：重新采集事实，与基线逐项比对，列出新增 / 删除 / 变更。

这样任何一次静默退化（文件被删、模块消失、契约版本回退）都会在下次运行被抓到，
而不是等到用户真机上出问题才发现。

**档位可比性（重要）**
------------------------
"可用引擎"这类清单**依赖解释器**：PASM-Lite 的具体引擎要 `import pasm_lite`
（它需要 torch）才会注册。同一个仓，用带 torch 的解释器跑出 `['pasm','pasm-light']`，
用不带 torch 的解释器跑出 `[]` —— 这不是退化，是**换了把尺子**。

早期版本没记录这一点，结果把"换了解释器"误报成 `[FAIL] 能力消失`。
现在基线与采集结果都会记下 `python` 路径与 `torch` 可用性；
两者不一致时，清单类比对自动降级为 `[WARN] 档位不同·不可比`，
而不是撒谎说"能力没了"。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..agent import Agent, register

BASELINE_DIR = Path(__file__).resolve().parents[2] / "baselines"

#: 记录解释器档位的小片段，拼进两段指纹代码里
TIER_CODE = r"""
import sys as _sys
try:
    import torch as _t                      # noqa: F401
    _torch = True
except Exception:
    _torch = False
out["python"] = _sys.executable
out["torch"] = _torch
"""

CORE_FP_CODE = r"""
import json, hashlib, os
def h(p):
    # 行尾归一化后再哈希：本机 core.autocrlf 不稳定，同一份文件在镜像仓 `reset --hard`
    # 之后会变成 CRLF。直接哈希原始字节，就会把"换个行尾"报成"文件有变更"——
    # 又是一个假红。口径与 parity-guard 对齐：忽略 CRLF/LF 差异。
    try:
        return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()[:16]
    except Exception:
        return None
out = {"cognitive": {}, "envs": {}, "engine_api": None, "api": None,
       "engines": [], "engines_error": None, "errors": []}
for sub in ("cognitive", "envs"):
    base = os.path.join("pasm", sub)
    if os.path.isdir(base):
        for fn in sorted(os.listdir(base)):
            if fn.endswith(".py"):
                out[sub][fn] = h(os.path.join(base, fn))
    else:
        out["errors"].append("pasm/%s 目录不存在" % sub)
out["engine_api"] = h(os.path.join("pasm", "engine_api.py"))
try:
    from pasm import engine_api as ea
    out["api"] = getattr(ea, "API_VERSION", None)
    out["engines"] = ea.available()
except Exception as ex:
    out["engines_error"] = repr(ex)
""" + TIER_CODE + r"""
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""

LITE_FP_CODE = r"""
import json, hashlib, os
def h(p):
    # 行尾归一化后再哈希：本机 core.autocrlf 不稳定，同一份文件在镜像仓 `reset --hard`
    # 之后会变成 CRLF。直接哈希原始字节，就会把"换个行尾"报成"文件有变更"——
    # 又是一个假红。口径与 parity-guard 对齐：忽略 CRLF/LF 差异。
    try:
        return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()[:16]
    except Exception:
        return None
out = {"files": {}, "engines": [], "engines_error": None, "errors": []}
for fn in ("pasm_lite.py", "learning.py", "engine.py", "engine_api.py",
           "envs.py", "verify_swap.py"):
    if os.path.exists(fn):
        out["files"][fn] = h(fn)
""" + TIER_CODE + r"""
# 具体引擎是在 `import pasm_lite` 时注册的；它依赖 torch，
# 所以无 torch 时这里只能拿到空清单 —— 记录档位，别当成退化。
if out["torch"]:
    try:
        import pasm_lite                     # noqa: F401  触发具体引擎注册
    except Exception as ex:
        out["errors"].append("import pasm_lite: %r" % (ex,))
try:
    from engine_api import available
    out["engines"] = available()
except Exception as ex:
    out["engines_error"] = repr(ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""


@register
class RegressionAgent(Agent):
    """采集/比对 PASM 事实指纹，抓静默退化。

    用法：
        python -m pasm_skills run regression --update          # 建立/刷新基线
        python -m pasm_skills run regression                   # 与基线比对
        python -m pasm_skills run regression --baseline v0285  # 指定基线名
    """

    name = "regression"
    goal = "与基线比对，抓「文件被删 / 模块消失 / 契约回退」这类静默退化"
    needs = ("core",)

    # ------------------------------------------------------------ 采集
    def _collect(self) -> dict:
        core = self.ctx.probe("core", CORE_FP_CODE, timeout=120).get("json") or {}
        lite = (self.ctx.probe("lite", LITE_FP_CODE, timeout=120).get("json") or {})
        if core.get("engines_error"):
            core.setdefault("errors", []).append("engine_api: %s" % core["engines_error"])
        if lite.get("engines_error"):
            lite.setdefault("errors", []).append("engine_api: %s" % lite["engines_error"])
        return {
            "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "core": core,
            "lite": lite,
        }

    def _baseline_path(self, name: str) -> Path:
        return BASELINE_DIR / ("%s.json" % name)

    # ------------------------------------------------------------ 执行
    def run(self):
        name = self.options.get("baseline") or "core"
        path = self._baseline_path(name)
        snapshot = self._collect()

        errs = (snapshot["core"].get("errors") or []) + (snapshot["lite"].get("errors") or [])
        for e in errs:
            self.warn("采集期提示", e)

        if self.options.get("update") or not path.exists():
            BASELINE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            if self.options.get("update"):
                self.ok("基线已刷新", str(path))
            else:
                self.ok("首次运行：已建立基线", str(path))
            self.extra = {"baseline": str(path), "created": True,
                          "python": snapshot["core"].get("python"),
                          "torch": snapshot["core"].get("torch")}
            return None

        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except Exception as ex:                        # noqa: BLE001
            self.fail("基线文件损坏", "%s (%s)" % (path, ex))
            return None

        old_core, old_lite = old.get("core", {}), old.get("lite", {})
        new_core, new_lite = snapshot["core"], snapshot["lite"]

        self._diff_hashes("核心认知层", old_core.get("cognitive", {}),
                          new_core.get("cognitive", {}))
        self._diff_hashes("核心环境层", old_core.get("envs", {}),
                          new_core.get("envs", {}))
        self._diff_scalar("engine_api 指纹", old_core.get("engine_api"),
                          new_core.get("engine_api"))
        self._diff_hashes("Lite 源码", old_lite.get("files", {}),
                          new_lite.get("files", {}))
        self._diff_list("核心可用引擎", old_core.get("engines", []),
                        new_core.get("engines", []),
                        comparable=self._same_tier(old_core, new_core))
        self._diff_list("Lite 可用引擎", old_lite.get("engines", []),
                        new_lite.get("engines", []),
                        comparable=self._same_tier(old_lite, new_lite))
        self._diff_scalar("契约 API 版本", old_core.get("api"), new_core.get("api"))

        self._report_tier(old_core, new_core)

        self.extra = {"baseline": str(path),
                      "baseline_at": old.get("collected_at"),
                      "now": snapshot["collected_at"],
                      "python": new_core.get("python"),
                      "torch": new_core.get("torch")}
        self.ok("基线比对完成", "%s（%s）" % (path.name, old.get("collected_at", "?")))
        return None

    # ------------------------------------------------------------ 档位
    @staticmethod
    def _same_tier(old: dict, new: dict) -> bool:
        """两次采集是否用了"同一把尺子"。

        老基线可能没记 python/torch（早期版本），此时若两边引擎清单相同就当作同档，
        不同则保守地判为"档位可疑"，避免误报 FAIL。
        """
        if "python" not in old or "python" not in new:
            return old.get("engines", []) == new.get("engines", [])
        return (old.get("python") == new.get("python")
                and bool(old.get("torch")) == bool(new.get("torch")))

    def _report_tier(self, old: dict, new: dict) -> None:
        o, n = old.get("python"), new.get("python")
        if o and n and o != n:
            self.warn("采集解释器与基线不同",
                      "%s → %s（清单类结论仅供参考，可用 PASM_PYTHON 固定解释器）" % (o, n))
        elif n:
            self.ok("采集解释器与基线一致", "%s（torch=%s）" % (n, new.get("torch")))

    # ------------------------------------------------------------ 比对器
    def _diff_hashes(self, label: str, old: dict, new: dict) -> None:
        removed = sorted(set(old) - set(new))
        added = sorted(set(new) - set(old))
        changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
        if removed:
            self.fail("%s 文件被移除" % label, ", ".join(removed))
        if changed:
            self.warn("%s 文件有变更" % label, ", ".join(changed))
        if added:
            self.ok("%s 新增文件" % label, ", ".join(added))
        if not (removed or changed or added):
            self.ok("%s 与基线一致" % label, "%d 个文件" % len(new))

    def _diff_list(self, label: str, old: list, new: list,
                   comparable: bool = True) -> None:
        removed = sorted(set(old) - set(new))
        added = sorted(set(new) - set(old))
        if old == new:
            self.ok("%s 与基线一致" % label, "%s" % (", ".join(new) or "（空）"))
            return
        if not comparable:
            # 换了解释器/档位：清单本来就不同，不能算能力消失
            self.warn("%s 档位不同·不可比" % label,
                      "基线 %s → 本次 %s；需用 PASM_PYTHON 固定解释器后再判定"
                      % (", ".join(old) or "（空）", ", ".join(new) or "（空）"))
            return
        if removed:
            self.fail("%s 能力消失" % label, ", ".join(removed))
        if added:
            self.ok("%s 新增" % label, ", ".join(added))

    def _diff_scalar(self, label: str, old, new) -> None:
        if old == new:
            self.ok("%s 一致" % label, str(new))
        else:
            self.warn("%s 发生变化" % label, "%s -> %s" % (old, new))
