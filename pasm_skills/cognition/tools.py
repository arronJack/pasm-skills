"""工具注册表 —— 给智能体接上"手脚"。

真实问题
--------
``BaseAgent`` 只有**动作名**（``act()`` 返回 "teach" 这样的字符串），
没有可执行的工具：选了动作之后做什么，全靠各智能体自己 if/else。
于是"动作 → 真实副作用"这一层在每个产品里重复实现，且无法被发现、无法被授权。

本模块提供统一的工具注册表：

- 声明式注册（名称 / 描述 / JSON-Schema 参数 / 风险等级）
- **白名单**：只允许已注册的工具被调用（防 LLM 幻觉出工具名）
- **异常隔离**：单个工具炸了不影响智能体
- **可导出 MCP / OpenAI function-calling 的 schema** —— 这是接外部生态的关键

安全边界（诚实说明）
--------------------
这是**注册与授权层，不是沙箱**。真正执行外部副作用（写文件、发请求、跑命令）
的风险由调用方承担。``risk`` 字段只是给调用方一个可判定的信号，
配合 ``allow`` 白名单使用；本模块不做进程隔离。
"""
from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

__all__ = ["ToolSpec", "ToolResult", "ToolRegistry", "tool"]


SAFE = "safe"        # 只读、无副作用
RISKY = "risky"      # 有外部副作用（写文件、发网络请求、改状态）
DANGER = "danger"    # 不可逆（删除、支付、执行命令）


@dataclass
class ToolSpec:
    """一个工具的声明。"""

    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable[..., Any]] = None
    risk: str = SAFE
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    calls: int = 0
    errors: int = 0

    def schema(self) -> Dict[str, Any]:
        """导出 OpenAI / MCP 风格的 JSON Schema。"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": dict(self.parameters or {}),
                "required": [k for k, v in (self.parameters or {}).items()
                             if isinstance(v, dict) and v.get("required")],
            },
        }

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "tags": list(self.tags),
            "enabled": self.enabled,
            "calls": self.calls,
            "errors": self.errors,
        }


@dataclass
class ToolResult:
    name: str
    ok: bool
    result: Any = None
    error: str = ""
    ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "ok": self.ok,
                "result": self.result if self.ok else None,
                "error": self.error, "ms": round(self.ms, 1)}


def _schema_from_callable(fn: Callable[..., Any]) -> Dict[str, Any]:
    """从类型注解推一个简易 schema（够用，且不引入 pydantic）。"""
    props: Dict[str, Any] = {}
    try:
        sig = inspect.signature(fn)
    except Exception:
        return props
    py2json = {str: "string", int: "integer", float: "number", bool: "boolean",
               list: "array", dict: "object"}
    for pname, p in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        ann = p.annotation
        t = "string"
        if ann is not inspect._empty:
            t = py2json.get(ann, "string")
        props[pname] = {"type": t, "description": ""}
        if p.default is not inspect._empty:
            props[pname]["default"] = p.default
        else:
            props[pname]["required"] = True
    return props


class ToolRegistry:
    """工具注册表。"""

    def __init__(self, allow: Optional[Iterable[str]] = None,
                 allow_risk: Optional[Iterable[str]] = None):
        self._tools: Dict[str, ToolSpec] = {}
        #: 白名单；None 表示"注册即可用"
        self._allow = set(allow) if allow is not None else None
        #: 允许的风险等级
        self._allow_risk = set(allow_risk) if allow_risk is not None else {SAFE, RISKY}

    # ------- 注册 -------------------------------------------------

    def register(self, name: str, handler: Callable[..., Any],
                 description: str = "", parameters: Optional[Dict[str, Any]] = None,
                 risk: str = SAFE, tags: Optional[Iterable[str]] = None) -> ToolSpec:
        if not name or not callable(handler):
            raise ValueError("name 不能为空且 handler 必须可调用")
        spec = ToolSpec(
            name=name, description=description or (handler.__doc__ or "").strip(),
            parameters=parameters if parameters is not None
            else _schema_from_callable(handler),
            handler=handler, risk=risk, tags=list(tags or []),
        )
        self._tools[name] = spec
        return spec

    def tool(self, name: Optional[str] = None, description: str = "",
             risk: str = SAFE, tags: Optional[Iterable[str]] = None,
             parameters: Optional[Dict[str, Any]] = None):
        """装饰器注册::

            @tools.tool(risk="risky", description="发一条消息")
            def send(to: str, text: str) -> dict: ...
        """

        def deco(fn):
            self.register(name or fn.__name__, fn, description=description,
                          parameters=parameters, risk=risk, tags=tags)
            return fn

        return deco

    def unregister(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    # ------- 授权 -------------------------------------------------

    def allow(self, names: Iterable[str]) -> None:
        self._allow = set(names)

    def allow_all(self) -> None:
        self._allow = None

    def allowed(self, name: str) -> bool:
        spec = self._tools.get(name)
        if spec is None or not spec.enabled:
            return False
        if spec.risk not in self._allow_risk:
            return False
        if self._allow is not None and name not in self._allow:
            return False
        return True

    # ------- 调用 -------------------------------------------------

    def call(self, name: str, args: Optional[Dict[str, Any]] = None) -> ToolResult:
        args = dict(args or {})
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(name, False, error=f"未知工具：{name}")
        if not self.allowed(name):
            return ToolResult(name, False,
                              error=f"工具未被授权：{name}（risk={spec.risk}）")
        st = time.time()
        try:
            out = spec.handler(**args)  # type: ignore[misc]
            spec.calls += 1
            return ToolResult(name, True, out, ms=(time.time() - st) * 1000)
        except TypeError as ex:
            spec.errors += 1
            return ToolResult(name, False, error=f"参数不匹配：{ex}",
                              ms=(time.time() - st) * 1000)
        except Exception as ex:
            spec.errors += 1
            return ToolResult(name, False,
                              error=f"{type(ex).__name__}: {ex}",
                              ms=(time.time() - st) * 1000)

    # ------- 导出 -------------------------------------------------

    def list_specs(self, only_allowed: bool = True) -> List[ToolSpec]:
        return [s for s in self._tools.values()
                if (not only_allowed or self.allowed(s.name))]

    def schemas(self, only_allowed: bool = True) -> List[Dict[str, Any]]:
        return [s.schema() for s in self.list_specs(only_allowed)]

    def names(self) -> List[str]:
        return sorted(self._tools)

    def stats(self) -> Dict[str, Any]:
        return {
            "total": len(self._tools),
            "allowed": len(self.list_specs(True)),
            "allow_risk": sorted(self._allow_risk),
            "tools": [s.as_dict() for s in self._tools.values()],
        }

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ToolRegistry n={len(self._tools)}>"


def tool(name: Optional[str] = None, description: str = "", risk: str = SAFE):
    """模块级便捷装饰器（需要配合 ``bind_to`` 使用）。

    更常见的用法是 :meth:`ToolRegistry.tool`。
    """
    def deco(fn):
        fn.__pasm_tool__ = {  # type: ignore[attr-defined]
            "name": name or fn.__name__,
            "description": description or (fn.__doc__ or "").strip(),
            "risk": risk,
        }
        return fn
    return deco
