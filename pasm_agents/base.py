"""BaseAgent：以 PASM 核心为基座的产品智能体基类。

设计目标：

1. **离线优先**：不强制要求 torch/LLM/网络 —— 用户能 ``pip install`` 完就用。
2. **核心真接入**：能用 PASM 真核心（``pasm.cognitive.memory_layers`` /
   ``pasm.cognitive.learning`` / ``pasm.modules.emotion``）时优先用；不能时降级到
   :mod:`pasm.light` 或纯内置实现，并在 ``self.tier`` 字段写明档位，**永不隐藏降级**。
3. **可持久化**：每个 agent 一个目录 ``~/.pasm-agents/<agent_id>/``，JSON 存盘；
   跨进程加载能恢复上次记忆/情绪/动作权重。
4. **可反馈**：``feedback(kind, action=)`` 显式接受 action，调用学习层调整指定动作的权重。
   这一接口是 ``pasm-skills/agents/npc_lifelong`` 验证器压出来的"必备能力"。

子类需要实现的契约：

- :meth:`BaseAgent._render_reply`  — 给定用户输入 + 检索到的事实 + 当前情绪，渲染回复。
- :meth:`BaseAgent.action_pool`    — 返回当前阶段解锁的动作池。
- :meth:`BaseAgent.bootstrap_event` — 可选；首次启动时写入一条初始记忆。
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


# ============================================================ 档位探测

def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def _core_available() -> bool:
    """PASM 核心是否可导入（无需 torch）。"""
    try:
        from pasm.cognitive import memory_layers, learning  # noqa: F401
        return True
    except Exception:
        return False


def _now() -> float:
    return time.time()


# ============================================================ 状态结构


@dataclass
class AgentState:
    """Agent 的轻量运行时状态（不包含 PASM 核心本身的 episode 列表）。"""
    persona: Dict[str, Any] = field(default_factory=dict)
    growth_stage: int = 0
    total_interactions: int = 0
    last_active: float = 0.0
    mood: float = 0.0            # [-1, 1]；无 emotion 时由 fall-back 累计
    feedback_history: List[Dict[str, Any]] = field(default_factory=list)
    notes: Dict[str, Any] = field(default_factory=dict)


# ============================================================ 基类


class BaseAgent:
    """产品智能体的通用底座。

    参数
    ----
    agent_id : str
        全局唯一标识。同一 id 多次实例化会恢复到上次的状态。
    persona : dict
        性格/角色画像。常用键：``name``, ``role``, ``temper``, ``energy``, ``play``,
        ``tone``（语气描述，用于聊天渲染）。
    persist_dir : str | Path | None
        落盘目录；缺省 ``~/.pasm-agents/<agent_id>``。
    use_core : bool
        是否尝试接入 PASM 真核心。默认 True，找不到核心时静默降级。
    """

    #: 类级档位标签，写入 self.tier；子类可覆盖。
    TIER_LIGHT = "light"
    TIER_CORE = "core"
    TIER_BIONIC = "bionic"

    # ------- 构造 --------------------------------------------------

    def __init__(
        self,
        agent_id: str,
        persona: Dict[str, Any],
        persist_dir: Optional[str | Path] = None,
        *,
        use_core: bool = True,
        seed: Optional[int] = None,
    ):
        self.agent_id = agent_id
        self.persona = dict(persona or {})
        self.persist_dir = Path(
            persist_dir or (Path.home() / ".pasm-agents" / agent_id)
        )
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        if seed is not None:
            random.seed(seed)

        # 1. PASM 核心（memory + learning，torch-not-required）
        self._core = None  # type: ignore[var-annotated]
        self._core_ok = False
        if use_core:
            try:
                from pasm.cognitive import memory_layers, learning  # type: ignore
                memory_layers.set_data_dir(str(self.persist_dir))
                self._core = _CoreAdapter(memory_layers, learning,
                                          persona=self.persona)
                self._core_ok = True
            except Exception:
                self._core_ok = False

        if not self._core_ok:
            self._core = _LightAdapter(self.persist_dir)

        # 2. Emotion：优先 EmotionSystem（需 torch）；降级到 light 风格。
        self._emo = None
        self._emo_ok = False
        try:
            from pasm.modules.emotion import EmotionSystem, Personality  # type: ignore
            self._emo = EmotionSystem(Personality(
                temper=float(self.persona.get("temper", 0.5)),
                energy=float(self.persona.get("energy", 0.5)),
                play=float(self.persona.get("play", 0.5)),
            ))
            self._emo_ok = True
        except Exception:
            self._emo_ok = False

        # 3. 加载已有 state.json
        self.state = self._load_state()

        # 4. tier 标签（每次都重算；不存盘）
        if self._emo_ok and self._core_ok:
            self.tier = self.TIER_BIONIC
        elif self._core_ok:
            self.tier = self.TIER_CORE
        else:
            self.tier = self.TIER_LIGHT

        # 5. 引导事件（仅首次）
        if self.state.total_interactions == 0:
            for ev in self.bootstrap_event():
                self.observe(**ev) if isinstance(ev, dict) else self.observe(ev)

    # ------- 抽象契约（子类必须实现） -------------------

    def _render_reply(
        self,
        text: str,
        facts: List[Dict[str, Any]],
        mood: float,
    ) -> str:
        """基于用户输入 + 检索事实 + 当前情绪，渲染回复。"""
        raise NotImplementedError

    def action_pool(self) -> List[str]:
        """当前成长阶段解锁的动作池。"""
        raise NotImplementedError

    def bootstrap_event(self) -> List[Dict[str, Any]]:
        """首次启动时的初始记忆。可返回空列表。"""
        return []

    # ------- 记忆 ----------------------------------------------------

    def observe(
        self,
        title: str,
        brief: str = "",
        tags: Optional[Iterable[str]] = None,
        *,
        salience: int = 1,
        category: str = "日常",
    ) -> None:
        """写入一条经历。``salience`` 越高越不容易被覆盖。"""
        self.state.total_interactions += 1
        self.state.last_active = _now()
        self._core.episode_push(
            title=title, brief=brief,
            tags=list(tags or []),
            category=category, salience=salience,
        )

    def recall(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """跨层检索。返回结构：``[{title, brief, tags, sal, score, ...}, ...]``。"""
        return self._core.recall(query, k=k)

    # ------- 情绪 ---------------------------------------------------

    @property
    def mood(self) -> float:
        if self._emo_ok:
            snap = self._emo.snapshot() if hasattr(self._emo, "snapshot") else {}
            for k in ("valence", "mood", "v"):
                if k in snap:
                    try:
                        return float(snap[k])
                    except Exception:
                        pass
        return self.state.mood

    def feel(self, event: str, valence: float) -> None:
        """事件引发情绪变化。``valence`` ∈ [-1, 1]。"""
        if self._emo_ok:
            try:
                self._emo.update(event, valence)  # type: ignore[attr-defined]
            except Exception:
                pass
        else:
            cur = self.state.mood
            self.state.mood = max(-1.0, min(1.0, cur + valence * 0.1))

    # ------- 行为 / 学习 --------------------------------------------

    def act(self) -> str:
        """从当前动作池里挑一个。

        两个档位都走同一套语义：**性格基线（天生偏好）+ 学习权重（反馈塑形）**。
        早期版本把 `learn_pick` 挡在 `_core_ok` 后面，于是轻量档下反馈只进历史、
        不影响行为；核心档又因为参数名写错而从未真正启用。
        现在统一：候选池 + 性格基线一起交给适配层。
        """
        pool = list(self.action_pool())
        if not pool:
            return ""
        picker = getattr(self._core, "learn_pick", None)
        if picker is not None:
            try:
                return picker(pool, base=self._fallback_weights(pool),
                              persona=self.persona,
                              stage=self.state.growth_stage)
            except TypeError:
                # 适配层签名较老：退回位置参数
                try:
                    return picker(pool)
                except Exception:
                    pass
            except Exception:
                pass
        # 最终兜底：persona 加权随机
        return random.choices(pool, weights=self._fallback_weights(pool), k=1)[0]

    def feedback(self, kind: str, action: Optional[str] = None) -> Dict[str, float]:
        """用户反馈。

        ``kind`` ∈ ``{"praise", "scold", "poke", "hug", "ignore"}``。
        ``action`` 指明被反馈的是哪个动作（强烈建议传入，
        否则反馈会作用在"当前最偏好"的动作上，长期会让分布极端化——
        这正是 npc_lifelong 验证器压出的产品级要求）。
        """
        self.state.feedback_history.append({
            "kind": kind, "action": action, "ts": _now(),
        })
        # 只保留最近 200 条
        if len(self.state.feedback_history) > 200:
            self.state.feedback_history = self.state.feedback_history[-200:]
        # ⚠ 不要加 `self._core_ok and` 这个前置条件 ——
        # 轻量档同样有 feedback 实现（_LightAdapter），挡掉就等于
        # "记录了一次反馈，但行为永远不变"。
        if hasattr(self._core, "feedback"):
            try:
                return self._core.feedback(kind, action=action)
            except Exception:
                return {}
        return {}

    def _fallback_weights(self, pool: List[str]) -> List[float]:
        """无学习层时的性格驱动权重。

        temper 高 → 偏"主动"动作；energy 高 → 偏"动"作；play 高 → 偏"俏皮"动作。
        缺省 0.5 → 均匀分布。
        """
        temper = float(self.persona.get("temper", 0.5))
        energy = float(self.persona.get("energy", 0.5))
        play = float(self.persona.get("play", 0.5))
        # 用 action 名的关键词做软匹配（子类可扩展 ACT_BIAS）
        weights = []
        for a in pool:
            w = 1.0
            if any(k in a for k in ("wave", "talk", "share", "teach", "give")):
                w *= 0.5 + temper
            if any(k in a for k in ("hop", "dance", "spin", "ball", "run")):
                w *= 0.5 + energy
            if any(k in a for k in ("peek", "play", "joke", "boast")):
                w *= 0.5 + play
            weights.append(max(0.05, w))
        return weights

    # ------- 对话（不依赖外部 LLM） ------------------------------

    def chat(self, text: str) -> str:
        """基于 persona + 检索 + 情绪的回复。

        不调用外部 LLM；纯模板渲染 —— 这保证了产品在无网环境也能跑。
        子类若接入 LLM，应在自身的 :meth:`_render_reply` 里覆盖。
        """
        facts = self.recall(text, k=3)
        mood = self.mood
        # 同步：chat 也是一次交互
        self.state.total_interactions += 1
        self.state.last_active = _now()
        # 写入一条"听到对话"的记忆
        self.observe(
            title=f"对话：{text[:24]}",
            brief=text, tags=[text[:4]] if text else [],
            salience=2,
            category="对话",
        )
        return self._render_reply(text=text, facts=facts, mood=mood)

    # ------- 持久化 -------------------------------------------------

    _STATE_FILE = "agent_state.json"

    def save(self) -> Path:
        """落盘到 ``<persist_dir>/agent_state.json``。"""
        data = {
            "agent_id": self.agent_id,
            "agent_class": type(self).__name__,
            "version": 1,
            "state": asdict(self.state),
            "saved_at": _now(),
            "tier": self.tier,
        }
        out = self.persist_dir / self._STATE_FILE
        tmp = self.persist_dir / (self._STATE_FILE + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 用 rename 替代直接覆盖，避免半写文件
        os.replace(tmp, out)
        return out

    def _load_state(self) -> AgentState:
        p = self.persist_dir / self._STATE_FILE
        if not p.exists():
            return AgentState(persona=dict(self.persona))
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            st = data.get("state") or {}
            # persona 用当前传入的覆盖（外部可能更新），其余从盘里读
            st["persona"] = dict(self.persona)
            return AgentState(**st)
        except Exception:
            return AgentState(persona=dict(self.persona))

    # ------- 工具 ---------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """导出可读快照（给 inspect / API 用）。"""
        counts = self._core.counts() if hasattr(self._core, "counts") else {}
        return {
            "agent_id": self.agent_id,
            "agent_class": type(self).__name__,
            "tier": self.tier,
            "persist_dir": str(self.persist_dir),
            "persona": self.persona,
            "growth_stage": self.state.growth_stage,
            "total_interactions": self.state.total_interactions,
            "last_active": self.state.last_active,
            "mood": round(self.mood, 3),
            "feedback_count": len(self.state.feedback_history),
            "memory_counts": counts,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<{type(self).__name__} id={self.agent_id!r} "
            f"tier={self.tier} interactions={self.state.total_interactions}>"
        )


# ============================================================ 核心适配层


class _CoreAdapter:
    """把 PASM 真核心包成一个 ``BaseAgent`` 能直接用的薄接口。"""

    def __init__(self, memory_layers, learning, persona: Optional[dict] = None,
                 stage: int = 0):
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

    def _ensure_design(self, pool: List[str], persona=None, stage=None) -> None:
        """保证学习层认得当前动作池。

        ``LearningEngine`` 只对 ``design()`` 过的动作池有权重，没 design 过时
        ``pick()`` 直接返回 ``None``。而候选池会随成长阶段 / 子类自定义而变化，
        所以这里比对一次，变了就重新 design（``design`` 内部会保留已累积的反馈 adj）。
        """
        persona = dict(persona or self._persona or {})
        stage = int(stage if stage is not None else self._stage)
        if set(pool) == set(self._designed):
            return
        self._learning.design(persona, stage, list(pool))
        self._designed = list(pool)

    def episode_push(
        self, *, title, brief, tags, category, salience,
    ) -> None:
        self._mem.episode_push(
            title=title, brief=brief, tags=tags,
            cat=category, salience=salience,
        )

    def recall(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        try:
            hits = self._mem.recall_layers(query, k=k) or []
        except Exception:
            hits = []
        out = []
        for h in hits:
            if isinstance(h, dict):
                out.append(dict(h))
            elif isinstance(h, (list, tuple)) and len(h) >= 2:
                out.append({"score": h[0], **(h[1] if isinstance(h[1], dict) else {"content": h[1]})})
            else:
                out.append({"content": str(h)})
        return out

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


class _LightAdapter:
    """无核心时的内存版 fallback。

    实现与核心**一致的语义**（重要度淘汰 + 字面检索 + 朴素权重），
    这样无论档位高低，``BaseAgent`` 调用方感受不到差异。
    """

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
                self._weights = json.loads(self._weights_path.read_text(encoding="utf-8"))
            except Exception:
                self._weights = {}

    def _save_weights(self) -> None:
        self._weights_path.write_text(
            json.dumps(self._weights, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
        早期版本这里只用了学习权重，也没有把候选池送进学习层，
        导致轻量档下"反馈"记录了却从不影响行为。
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