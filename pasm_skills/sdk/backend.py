"""CognitiveBackend —— BaseAgent 与 PASM 引擎之间唯一的稳定契约面。

为什么存在（V1→V2 不重写智能体/技能的关键）
------------------------------------------------
`BaseAgent` 曾经直接 ``import pasm.cognitive`` / ``pasm.modules``，等于让每个产品智能体
都"摸得到引擎内脏"。一旦 V2 重写引擎、改了模块路径或方法签名，所有智能体 + 技能会同时崩。

本模块把"引擎连接"收敛成一个**可替换的后端**：

  · `CognitiveBackend`     —— 运行时协议（Protocol），定义 BaseAgent 需要的全部方法；
  · `PasmV1CoreBackend`   —— V1 真核心（pasm.cognitive.memory_layers + learning + emotion）；
  · `PasmV1LightBackend`  —— 无核心时的纯本地 fallback（与原 ``_LightAdapter`` 同语义）；
  · `create_v1_backend()` —— 工厂：按 ``use_core`` 自动选 core / light。

V2 落地时只需新增 `PasmV2Backend`（实现同一 `CognitiveBackend` 协议），
并在工厂里切换 —— **BaseAgent、4 个智能体、3 个技能一行不改**。

> 本模块是「防腐层」：所有 ``import pasm.*`` 都只发生在这里（且是 lazily），
> `BaseAgent` 本身不再 import 任何 pasm 内部模块。
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import (
    Any, Dict, Iterable, List, Optional, Protocol, runtime_checkable,
)


# ============================================================ 时钟（与 BaseAgent 共用）

def _now() -> float:
    return time.time()


# ============================================================ 档位探测

def _core_available() -> bool:
    """PASM 核心是否可导入（无需 torch）。"""
    try:
        from pasm.cognitive import memory_layers, learning  # noqa: F401
        return True
    except Exception:
        return False


# ============================================================ 后端协议

@runtime_checkable
class CognitiveBackend(Protocol):
    """BaseAgent 依赖的稳定后端契约。

    必选方法（BaseAgent 必然调用，后端必须实现）：
      - ``episode_push`` / ``recall`` / ``feedback``
    可选方法（BaseAgent 用 ``getattr``/``hasattr`` 探测，缺失则走兜底）：
      - ``learn_pick`` / ``counts``
    引擎元信息（纯属性，用于 tier 标注与情绪路由）：
      - ``is_core``        是否接入了真核心（决定 tier = core/bionic）
      - ``emotion_system`` 真实情绪系统（None 表示走轻量情绪兜底）
    """

    is_core: bool
    emotion_system: Optional[Any]

    def episode_push(self, *, title: str, brief: str, tags: List[str],
                     category: str, salience: int) -> None: ...
    def recall(self, query: str, k: int = 5) -> List[Dict[str, Any]]: ...
    def feedback(self, kind: str, action: Optional[str] = None) -> Dict[str, float]: ...


# ============================================================ V1 核心后端

class PasmV1CoreBackend:
    """V1 真核心（pasm.cognitive.memory_layers + learning + emotion）。

    原 ``BaseAgent`` 里的 ``_CoreAdapter`` —— 仅迁移位置、不改行为。
    把"记忆 + 学习 + 情绪"三个引擎内部件一起隔离进来，外部看不见。
    """

    is_core = True

    def __init__(self, memory_layers, learning,
                 persona: Optional[dict] = None, stage: int = 0):
        self._mem = memory_layers
        # ⚠ 核心 LearningEngine 的参数名是 **data_path**，不是 data_dir。
        # 曾经写成 data_dir：构造时 TypeError，被 `except Exception` 静默吞掉，
        # 结果"永远启用不了核心档"——而且失败得毫无痕迹。别再改回去。
        self._learning = learning.LearningEngine(
            data_path=str(Path(memory_layers.DATA_DIR) / "action_weights.json")
        )
        self._persona = dict(persona or {})
        self._stage = int(stage or 0)
        self._designed: List[str] = []
        # —— 情绪系统（原 BaseAgent.__init__ 的 step2，随核心一起隔离进来）
        self.emotion_system: Optional[Any] = None
        try:
            from pasm.modules.emotion import EmotionSystem, Personality  # type: ignore
            self.emotion_system = EmotionSystem(Personality(
                temper=float(self._persona.get("temper", 0.5)),
                energy=float(self._persona.get("energy", 0.5)),
                play=float(self._persona.get("play", 0.5)),
            ))
        except Exception:
            self.emotion_system = None

    # ---- 学习层设计（动作池随成长阶段变化，变了就重新 design） ----

    def _ensure_design(self, pool: List[str], persona=None, stage=None) -> None:
        persona = dict(persona or self._persona or {})
        stage = int(stage if stage is not None else self._stage)
        if set(pool) == set(self._designed):
            return
        self._learning.design(persona, stage, list(pool))
        self._designed = list(pool)

    # ---- CognitiveBackend 契约 ----

    def episode_push(
        self, *, title, brief, tags, category, salience,
    ) -> None:
        self._mem.episode_push(
            title=title, brief=brief, tags=tags,
            cat=category, salience=salience,
        )

    def recall(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """跨层检索，返回情景记忆命中列表（与 light 档同契约：[{title, brief, tags, sal, ...}]）。

        核心的 ``recall_layers`` 返回的是**已格式化的字符串**（给 companion 直接拼进
        系统提示词用），和 BaseAgent.recall 约定的「列表(dict)」不一致；直接喂进去会被当成
        字符串逐字符遍历。所以这里直接用核心的 ``episodes()`` + ``_score`` 取情景记忆 dict，
        契约与 ``PasmV1LightBackend.recall`` 完全一致。
        """
        q = (query or "").strip()
        if not q:
            return []
        try:
            scored = []
            for e in self._mem.episodes():
                hay = (e.get("title", "") + " " + " ".join(e.get("tags", []))
                       + " " + e.get("brief", ""))
                sc = self._mem._score(q, hay)
                if sc > 0:
                    scored.append((sc, e))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [dict(e) for _, e in scored[:k]]
        except Exception:
            return []

    def learn_pick(self, candidates: List[str], base=None,
                   persona=None, stage=None) -> str:
        """按学习层权重在候选池里选一个动作。

        **不要**把候选池当成 ``pick()`` 的位置参数传进去 ——
        ``LearningEngine.pick(epsilon=0.15)`` 收的是探索率，
        传 list 会 ``TypeError: '<' not supported between 'float' and 'list'``，
        然后被上层吞掉、悄悄退化成"只有性格、没有学习"。
        """
        pool = [c for c in candidates if c]
        if not pool:
            return ""
        try:
            self._ensure_design(pool, persona=persona, stage=stage)
            got = self._learning.pick()
        except Exception:
            got = None
        return got if got in pool else random.choice(pool)

    def feedback(self, kind: str, action: Optional[str] = None) -> Dict[str, float]:
        return self._learning.feedback(kind, lr=0.25, action=action)

    def counts(self) -> Dict[str, int]:
        try:
            return self._mem.counts() or {}
        except Exception:
            return {}


# ============================================================ V1 轻量后端

class PasmV1LightBackend:
    """无核心时的内存版 fallback。

    实现与核心**一致的语义**（重要度淘汰 + 字面检索 + 朴素权重），
    这样无论档位高低，``BaseAgent`` 调用方感受不到差异。
    原 ``BaseAgent`` 里的 ``_LightAdapter`` —— 仅迁移位置、不改行为。
    """

    is_core = False
    emotion_system = None
    _CAP = 200

    def __init__(self, persist_dir: Path):
        self._dir = persist_dir
        self._path = persist_dir / "episodes.json"
        self._episodes: List[Dict[str, Any]] = self._load()
        self._weights: Dict[str, float] = {}
        self._weights_path = persist_dir / "action_weights.json"
        self._load_weights()

    def _load(self) -> List[Dict[str, Any]]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._episodes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_weights(self) -> None:
        if self._weights_path.exists():
            try:
                self._weights = json.loads(
                    self._weights_path.read_text(encoding="utf-8"))
            except Exception:
                self._weights = {}

    def _save_weights(self) -> None:
        self._weights_path.write_text(
            json.dumps(self._weights, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---- CognitiveBackend 契约 ----

    def episode_push(
        self, *, title, brief, tags, category, salience,
    ) -> None:
        rec = {
            "title": title, "brief": brief, "tags": list(tags),
            "cat": category, "sal": max(1, min(5, int(salience))),
            "ts": _now(),
        }
        self._episodes.insert(0, rec)
        # 重要度淘汰
        if len(self._episodes) > self._CAP:
            order = sorted(
                range(len(self._episodes)),
                key=lambda i: (self._episodes[i].get("sal", 1), -i),
            )
            doomed = set(order[: len(self._episodes) - self._CAP])
            self._episodes[:] = [
                e for i, e in enumerate(self._episodes) if i not in doomed
            ]
        self._save()

    def recall(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        if not self._episodes:
            return []
        q_tokens = set(query)
        scored = []
        for e in self._episodes:
            blob = (e.get("title", "") + " " + e.get("brief", "") + " "
                    + " ".join(e.get("tags", [])))
            score = sum(1 for t in q_tokens if t and t in blob)
            score += e.get("sal", 1) * 0.1
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]

    def learn_pick(self, candidates: List[str], base=None, **kw) -> str:
        """在候选池里按「性格基线 + 反馈学到的偏置」采样。

        `base` 是这个角色的性格基线权重（由 :meth:`BaseAgent._fallback_weights` 算好）。
        两者**都要生效**：性格决定"天生偏好什么"，反馈决定"被夸/被凶后怎么偏"。
        """
        pool = [c for c in candidates if c]
        if not pool:
            return ""
        scores = []
        for i, c in enumerate(pool):
            b = float(base[i]) if base and i < len(base) else 1.0
            scores.append(max(0.01, b + float(self._weights.get(c, 0.0))))
        m = max(scores)
        exps = [pow(2.71828, s - m) for s in scores]
        s = sum(exps) or 1.0
        probs = [e / s for e in exps]
        return random.choices(pool, weights=probs, k=1)[0]

    def feedback(self, kind: str, action: Optional[str] = None) -> Dict[str, float]:
        delta = {
            "praise": 0.3, "hug": 0.15, "poke": -0.05, "scold": -0.3,
        }.get(kind, 0.0)
        if delta == 0.0 or not action:
            return dict(self._weights)
        self._weights[action] = round(self._weights.get(action, 0.0) + delta, 3)
        self._save_weights()
        return dict(self._weights)

    def counts(self) -> Dict[str, int]:
        return {"episodes": len(self._episodes)}


# ============================================================ 工厂

def create_v1_backend(
    persist_dir: Path,
    persona: Optional[dict] = None,
    *,
    use_core: bool = True,
    stage: int = 0,
) -> CognitiveBackend:
    """按 ``use_core`` 选 V1 后端。

    - 能用真核心（pasm.cognitive 可导入）就返回 `PasmV1CoreBackend`；
    - 否则退回 `PasmV1LightBackend`。

    返回类型标注为 `CognitiveBackend` 协议，调用方（BaseAgent）只看见稳定契约。

    ``persist_dir`` 接受 ``str | Path``：内部统一转 ``Path``，
    避免上层（如装配器）传字符串时 ``str / "x"`` 抛 TypeError。
    """
    persist_dir = Path(persist_dir)
    if use_core:
        try:
            from pasm.cognitive import memory_layers, learning  # type: ignore
            memory_layers.set_data_dir(str(persist_dir))
            return PasmV1CoreBackend(
                memory_layers, learning, persona=persona, stage=stage)
        except Exception:
            pass
    return PasmV1LightBackend(persist_dir)
