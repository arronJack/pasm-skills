"""焦点栈 —— 回答"现在在聊什么"。

真实问题
--------
长对话里，智能体容易"跑题"或"记不住当前话题"：用户连续三轮都在问同一个 bug，
但每轮都从头检索，于是上下文里混进了上一轮已经不相关的旧事。

焦点栈维护一个**带权重衰减的话题栈**：

- 每次交互 ``push`` 当前话题（自动去重 + 已存在则加权）
- 权重随时间衰减 → 冷下去的话题自然沉底
- ``to_prompt()`` 只渲染栈顶若干条 → 直接拼进上下文
- 栈过深时 ``compress()`` 把最老的几条压成一条摘要
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["FocusItem", "FocusStack"]


def _now() -> float:
    return time.time()


@dataclass
class FocusItem:
    """栈里的一个话题。"""

    topic: str
    entities: List[str] = field(default_factory=list)
    weight: float = 1.0
    hits: int = 1
    ts: float = field(default_factory=_now)
    last: float = field(default_factory=_now)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FocusItem":
        return cls(
            topic=str(d.get("topic", "")),
            entities=list(d.get("entities") or []),
            weight=float(d.get("weight", 1.0)),
            hits=int(d.get("hits", 1)),
            ts=float(d.get("ts", _now())),
            last=float(d.get("last", _now())),
        )


class FocusStack:
    """带衰减的话题焦点栈。

    参数
    ----
    half_life : 权重半衰期（秒）。默认 10 分钟 ——
        对话里 10 分钟没再提的话题基本可以认为结束了。
    max_items : 超过就压缩最老的
    """

    def __init__(self, half_life: float = 600.0, max_items: int = 8,
                 min_weight: float = 0.05):
        self.half_life = max(1.0, float(half_life))
        self.max_items = max(2, int(max_items))
        self.min_weight = float(min_weight)
        self._items: List[FocusItem] = []

    # ------- 基本操作 ---------------------------------------------

    def push(self, topic: str, entities: Optional[Sequence[str]] = None,
             weight: float = 1.0) -> FocusItem:
        """压入/加权一个话题，并把它移到栈顶。"""
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("topic 不能为空")
        self.decay()
        ents = [str(e) for e in (entities or []) if e]
        for it in self._items:
            if it.topic == topic:
                it.hits += 1
                it.weight = min(5.0, it.weight + weight)
                it.last = _now()
                for e in ents:
                    if e not in it.entities:
                        it.entities.append(e)
                self._items.remove(it)
                self._items.insert(0, it)
                return it
        item = FocusItem(topic=topic, entities=ents, weight=weight)
        self._items.insert(0, item)
        self._trim()
        return item

    def peek(self) -> Optional[FocusItem]:
        """当前焦点（栈顶）。"""
        self.decay()
        return self._items[0] if self._items else None

    def pop(self) -> Optional[FocusItem]:
        self.decay()
        return self._items.pop(0) if self._items else None

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    # ------- 衰减 / 压缩 -------------------------------------------

    def decay(self, now: Optional[float] = None) -> None:
        """按半衰期衰减全部权重，并清掉沉底的。"""
        now = _now() if now is None else now
        kept: List[FocusItem] = []
        for it in self._items:
            age = max(0.0, now - float(it.last))
            it.weight = it.weight * (0.5 ** (age / self.half_life))
            it.last = now
            if it.weight >= self.min_weight:
                kept.append(it)
        self._items = kept

    def _trim(self) -> None:
        if len(self._items) <= self.max_items:
            return
        self.compress(keep=self.max_items)

    def compress(self, keep: int = 4) -> Optional[FocusItem]:
        """把尾部（最老的）若干条压成一条摘要。"""
        keep = max(1, int(keep))
        if len(self._items) <= keep:
            return None
        tail = self._items[keep:]
        self._items = self._items[:keep]
        if not tail:
            return None
        topics: List[str] = []
        ents: List[str] = []
        for it in tail:
            if it.topic not in topics:
                topics.append(it.topic)
            for e in it.entities:
                if e not in ents:
                    ents.append(e)
        merged = FocusItem(
            topic="此前聊过：" + "、".join(topics[:4]),
            entities=ents[:8],
            weight=max(i.weight for i in tail) * 0.8,
            hits=sum(i.hits for i in tail),
        )
        self._items.append(merged)
        return merged

    # ------- 输出 --------------------------------------------------

    def top(self, n: int = 3) -> List[FocusItem]:
        self.decay()
        return sorted(self._items, key=lambda i: i.weight, reverse=True)[: max(1, n)]

    def to_prompt(self, n: int = 3) -> str:
        """渲染成可直接拼进提示词的文本。"""
        items = self.top(n)
        if not items:
            return ""
        parts = []
        for it in items:
            s = it.topic
            if it.entities:
                s += f"（涉及：{'、'.join(it.entities[:4])}）"
            parts.append(s)
        return "当前焦点：" + " ｜ ".join(parts)

    def current_entities(self, n: int = 6) -> List[str]:
        """当前焦点涉及的实体 —— 可用于给检索做加权。"""
        out: List[str] = []
        for it in self.top(3):
            for e in it.entities:
                if e not in out:
                    out.append(e)
        return out[: max(1, n)]

    def snapshot(self) -> List[Dict[str, Any]]:
        self.decay()
        return [it.as_dict() for it in self._items]

    # ------- 持久化 -------------------------------------------------

    FILE = "focus_stack.json"

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p

    def load(self, path: str | Path) -> bool:
        p = Path(path)
        if not p.exists():
            return False
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
            self._items = [FocusItem.from_dict(r) for r in rows if r.get("topic")]
            return True
        except Exception:
            return False

    def __repr__(self) -> str:  # pragma: no cover
        top = self._items[0].topic if self._items else "-"
        return f"<FocusStack n={len(self._items)} top={top!r}>"
