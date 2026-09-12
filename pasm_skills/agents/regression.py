"""regression —— 事实指纹与基线对比。

长期验证真正要回答的问题是：**"上周还好好的，今天有没有退化？"**
所以本智能体不判断"对错"，只做两件事：

  1. `--update`：把当前事实（认知层文件指纹 + 引擎清单 + 契约版本）存成基线；
  2. 无参数：重新采集事实，与基线逐项比对，列出新增 / 删除 / 变更。

这样任何一次静默退化（文件被删、模块消失、契约版本回退）都会在下次运行被抓到，
而不是等到用户真机上出问题才发现。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..agent import Agent, register

BASELINE_DIR = Path(__file__).resolve().parents[2] / "baselines"

CORE_FP_CODE = r"""
import json, hashlib, os
def h(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    except Exception:
        return None
out = {"cognitive": {}, "api": None, "engines": [], "errors": []}
base = os.path.join("pasm", "cognitive")
if os.path.isdir(base):
    for fn in sorted(os.listdir(base)):
        if fn.endswith(".py"):
            out["cognitive"][fn] = h(os.path.join(base, fn))
else:
    out["errors"].append("pasm/cognitive 目录不存在")
try:
    from pasm import engine_api as ea
    out["api"] = getattr(ea, "API_VERSION", None)
    out["engines"] = ea.available()
except Exception as ex:
    out["errors"].append("engine_api: %s" % ex)
print(SENTINEL + json.dumps(out, ensure_ascii=False))
"""

LITE_FP_CODE = r"""
import json, hashlib, os
def h(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    except Exception:
        return None
out = {"files": {}, "errors": []}
for fn in ("pasm_lite.py", "learning.py", "engine.py", "engine_api.py"):
    if os.path.exists(fn):
        out["files"][fn] = h(fn)
try:
    from engine_api import available
    out["engines"] = available()
except Exception as ex:
    out["errors"].append("engine_api: %s" % ex)
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
            self.extra = {"baseline": str(path), "created": True}
            return None

        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except Exception as ex:                        # noqa: BLE001
            self.fail("基线文件损坏", "%s (%s)" % (path, ex))
            return None

        self._diff_hashes("核心认知层", old.get("core", {}).get("cognitive", {}),
                          snapshot["core"].get("cognitive", {}))
        self._diff_hashes("Lite 源码", old.get("lite", {}).get("files", {}),
                          snapshot["lite"].get("files", {}))
        self._diff_list("核心可用引擎", old.get("core", {}).get("engines", []),
                        snapshot["core"].get("engines", []))
        self._diff_list("Lite 可用引擎", old.get("lite", {}).get("engines", []),
                        snapshot["lite"].get("engines", []))
        self._diff_scalar("契约 API 版本", old.get("core", {}).get("api"),
                          snapshot["core"].get("api"))

        self.extra = {"baseline": str(path),
                      "baseline_at": old.get("collected_at"),
                      "now": snapshot["collected_at"]}
        self.ok("基线比对完成", "%s（%s）" % (path.name, old.get("collected_at", "?")))
        return None

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

    def _diff_list(self, label: str, old: list, new: list) -> None:
        removed = sorted(set(old) - set(new))
        added = sorted(set(new) - set(old))
        if removed:
            self.fail("%s 能力消失" % label, ", ".join(removed))
        if added:
            self.ok("%s 新增" % label, ", ".join(added))
        if not removed and not added:
            self.ok("%s 与基线一致" % label, "%s" % (", ".join(new) or "（空）"))

    def _diff_scalar(self, label: str, old, new) -> None:
        if old == new:
            self.ok("%s 一致" % label, str(new))
        else:
            self.warn("%s 发生变化" % label, "%s -> %s" % (old, new))
