"""TICK 心跳主循环 —— 让智能体在"没人说话的时候"也能做事。

真实问题
--------
PASM 此前是**纯被动**的：不调用就没有行为。于是

- 智能体永远不会主动开口（用户离开了它也不挽留、不总结）
- 记忆巩固、遗忘衰减这类后台任务没有触发时机

设计
----
一个后台守护线程 + 可注册的 tick 处理器：

- **空闲判定**：距上次交互超过 ``idle_after`` 秒才算空闲，避免打断对话
- **异常隔离**：任一处理器抛异常只记下来，循环继续 —— 心跳不能因为一个插件挂掉
- **卡死看门狗**：记录每次 tick 耗时，超过阈值记入 ``slow_ticks``，
  便于发现"某个后台任务把进程拖死了"
- **可强制**：``run_once(force=True)`` 供测试与手动触发

典型用法::

    loop = TickLoop(interval=60.0, idle_after=180.0)
    loop.register(consolidate_every_10min, name="consolidate", every=10)
    loop.register(idle_greeting, name="greet")
    loop.start()
    ...
    loop.notify()          # 用户说话了 → 重置空闲计时
    loop.stop()
"""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

__all__ = ["TickContext", "TickHandler", "TickLoop", "TickResult"]


def _now() -> float:
    return time.time()


@dataclass
class TickContext:
    """传给处理器的上下文。"""

    tick: int
    now: float
    idle_seconds: float
    loop_name: str = "pasm"

    def as_dict(self) -> Dict[str, Any]:
        return {"tick": self.tick, "now": self.now,
                "idle_seconds": round(self.idle_seconds, 1),
                "loop": self.loop_name}


@dataclass
class TickResult:
    """一次处理器执行的记要。"""

    name: str
    ok: bool
    ms: float
    value: Any = None
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "ms": round(self.ms, 1),
                "error": self.error}


@dataclass
class TickHandler:
    fn: Callable[[TickContext], Any]
    name: str
    every: int = 1
    enabled: bool = True
    runs: int = 0
    errors: int = 0
    last_ms: float = 0.0
    tags: List[str] = field(default_factory=list)


class TickLoop:
    """心跳循环。

    参数
    ----
    interval   : 两次 tick 的间隔（秒）
    idle_after : 距上次交互多久算空闲（秒）
    slow_ms    : 单次 tick 超过这个毫秒数记入慢 tick
    """

    def __init__(self, interval: float = 60.0, idle_after: float = 180.0,
                 slow_ms: float = 2000.0, name: str = "pasm"):
        self.interval = max(1.0, float(interval))
        self.idle_after = max(0.0, float(idle_after))
        self.slow_ms = float(slow_ms)
        self.name = name

        self._handlers: List[TickHandler] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._tick = 0
        self._last_active = _now()
        self._last_results: List[TickResult] = []
        self._slow_ticks = 0

    # ------- 注册 -------------------------------------------------

    def register(self, fn: Callable[[TickContext], Any], name: Optional[str] = None,
                 every: int = 1, tags: Optional[List[str]] = None) -> TickHandler:
        h = TickHandler(fn=fn, name=name or getattr(fn, "__name__", "anon"),
                        every=max(1, int(every)), tags=list(tags or []))
        with self._lock:
            self._handlers.append(h)
        return h

    def on_tick(self, *, name: Optional[str] = None, every: int = 1,
                tags: Optional[List[str]] = None):
        """装饰器形式::

            @loop.on_tick(every=10)
            def consolidate(ctx): ...
        """

        def deco(fn):
            self.register(fn, name=name, every=every, tags=tags)
            return fn

        return deco

    def unregister(self, name: str) -> bool:
        with self._lock:
            before = len(self._handlers)
            self._handlers = [h for h in self._handlers if h.name != name]
            return len(self._handlers) < before

    def handler_names(self) -> List[str]:
        return [h.name for h in self._handlers]

    # ------- 状态 -------------------------------------------------

    def notify(self) -> None:
        """标记一次用户活动（重置空闲计时）。"""
        self._last_active = _now()

    @property
    def idle_seconds(self) -> float:
        return max(0.0, _now() - self._last_active)

    @property
    def is_idle(self) -> bool:
        return self.idle_seconds >= self.idle_after

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------- 执行 -------------------------------------------------

    def run_once(self, force: bool = False) -> List[TickResult]:
        """跑一轮。**不启动线程** —— 测试与手动触发都用它。"""
        self._tick += 1
        ctx = TickContext(tick=self._tick, now=_now(),
                          idle_seconds=self.idle_seconds, loop_name=self.name)
        if not force and not self.is_idle:
            return []
        results: List[TickResult] = []
        t0 = _now()
        with self._lock:
            handlers = list(self._handlers)
        for h in handlers:
            if not h.enabled:
                continue
            if h.every > 1 and (self._tick % h.every) != 0:
                continue
            st = _now()
            try:
                val = h.fn(ctx)
                h.runs += 1
                results.append(TickResult(h.name, True, (_now() - st) * 1000, val))
            except Exception as ex:
                h.errors += 1
                results.append(TickResult(
                    h.name, False, (_now() - st) * 1000, None,
                    f"{type(ex).__name__}: {ex}",
                ))
            h.last_ms = (_now() - st) * 1000
        elapsed = (_now() - t0) * 1000
        if elapsed > self.slow_ms:
            self._slow_ticks += 1
        self._last_results = results
        return results

    # ------- 线程 -------------------------------------------------

    def _loop(self) -> None:  # pragma: no cover - 线程体
        while not self._stop.wait(self.interval):
            try:
                self.run_once()
            except Exception:
                # 兜底：心跳绝不能因为意外退出
                traceback.print_exc()

    def start(self, daemon: bool = True) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name=f"pasm-tick-{self.name}", daemon=daemon,
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 2.0) -> bool:
        if not self.running:
            return False
        self._stop.set()
        self._thread.join(timeout=timeout)  # type: ignore[union-attr]
        self._thread = None
        return True

    def __enter__(self) -> "TickLoop":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ------- 观测 -------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "running": self.running,
            "ticks": self._tick,
            "interval": self.interval,
            "idle_after": self.idle_after,
            "idle_seconds": round(self.idle_seconds, 1),
            "handlers": [
                {"name": h.name, "every": h.every, "runs": h.runs,
                 "errors": h.errors, "last_ms": round(h.last_ms, 1),
                 "enabled": h.enabled}
                for h in self._handlers
            ],
            "slow_ticks": self._slow_ticks,
            "last_results": [r.as_dict() for r in self._last_results[-10:]],
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<TickLoop {self.name} running={self.running} "
                f"ticks={self._tick} handlers={len(self._handlers)}>")
