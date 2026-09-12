"""智能体发现（discovery）—— 基座不认识任何具体智能体。

设计取舍
--------
基座仓**不内置任何智能体**，所以必须有一套"把外部智能体接进来"的机制。
按优先级：

1. **`PASM_SKILLS_PATH`** —— 本地开发最常用。指向一个 `.py` 文件或目录，
   直接把里面的模块加载进来（适合"我刚写了一个智能体，还没打包"）。
2. **`PASM_SKILLS_AGENT_MODULES`** —— 逗号分隔的模块名，逐个 import。
   （适合测试环境里显式钉死加载哪些模块。）
3. **entry points**（`importlib.metadata`，组名 `pasm_skills.agents`）——
   智能体包装成 pip 包并安装后，自动被发现。独立仓 `pasm-agents` 用的就是这条。

三条都失败也不会报错 —— 基座照样能用 `selftest` / `repos`，
只是 `list` 里智能体为 0 个。**基座不依赖任何智能体，这是刻意的。**
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import List, Tuple

#: entry points 组名：智能体包在自己的 pyproject 里声明这个组即可被基座发现
ENTRY_POINT_GROUP = "pasm_skills.agents"


def _from_path() -> List[str]:
    """从 `PASM_SKILLS_PATH` 加载（文件或目录）。返回加载成功的描述串。"""
    raw = os.environ.get("PASM_SKILLS_PATH", "")
    loaded: List[str] = []
    for entry in [p for p in raw.split(os.pathsep) if p.strip()]:
        p = Path(entry)
        if p.is_file() and p.suffix == ".py":
            files = [p]
        elif p.is_dir():
            files = sorted(p.glob("*.py"))
        else:
            print("[WARN] PASM_SKILLS_PATH 里的路径不存在：%s" % p, file=sys.stderr)
            continue
        for f in files:
            mod_name = "pasm_skills_local_%s" % f.stem
            try:
                spec = importlib.util.spec_from_file_location(mod_name, f)
                if spec is None or spec.loader is None:
                    raise ImportError("无法为 %s 建立 spec" % f)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                loaded.append("path:%s" % f.name)
            except Exception as ex:                   # noqa: BLE001
                print("[WARN] 本地智能体加载失败 %s: %s" % (f, ex), file=sys.stderr)
    return loaded


def _from_modules() -> List[str]:
    """从 `PASM_SKILLS_AGENT_MODULES` 逐个 import。"""
    raw = os.environ.get("PASM_SKILLS_AGENT_MODULES", "")
    loaded: List[str] = []
    for name in [m.strip() for m in raw.split(",") if m.strip()]:
        try:
            importlib.import_module(name)
            loaded.append("module:%s" % name)
        except Exception as ex:                      # noqa: BLE001
            print("[WARN] 智能体模块导入失败 %s: %s" % (name, ex), file=sys.stderr)
    return loaded


def _from_entry_points() -> List[str]:
    """从已安装包的 entry points 发现智能体模块。"""
    loaded: List[str] = []
    try:
        from importlib.metadata import entry_points
    except Exception:                                # noqa: BLE001
        return loaded
    try:
        eps = entry_points()
        # Python 3.10+ 支持按组筛选；3.9 只有 dict 风格
        group = (eps.select(group=ENTRY_POINT_GROUP)
                 if hasattr(eps, "select")
                 else eps.get(ENTRY_POINT_GROUP, []))
    except Exception:                                # noqa: BLE001
        return loaded
    for ep in group:
        target = getattr(ep, "value", None) or getattr(ep, "module", "")
        try:
            importlib.import_module(target)
            loaded.append("entrypoint:%s" % target)
        except Exception as ex:                      # noqa: BLE001
            print("[WARN] entry point 智能体加载失败 %s: %s" % (target, ex),
                  file=sys.stderr)
    return loaded


def load_agents() -> Tuple[List[str], List[str]]:
    """把外部智能体加载进注册表。

    返回 `(loaded, warnings)`。**不抛异常** —— 基座不该因为某个智能体装坏了就跑不起来。
    """
    loaded: List[str] = []
    for fn in (_from_path, _from_modules, _from_entry_points):
        try:
            loaded.extend(fn())
        except Exception as ex:                      # noqa: BLE001
            print("[WARN] 智能体发现阶段出错（已跳过）: %s" % ex, file=sys.stderr)
    # 去重保序
    seen, out = set(), []
    for x in loaded:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out, []
