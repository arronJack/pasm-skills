"""BaseAgent：以 PASM 核心为基座的产品智能体基类。

设计目标：

1. **离线优先**：不强制要求 torch/LLM/网络 —— 用户能 ``pip install`` 完就用。
2. **核心真接入（经后端）**：引擎连接全部收敛在 ``pasm_skills.sdk.backend``，
   由 ``CognitiveBackend`` 协议 + ``create_v1_backend()`` 工厂提供；能用真核心时优先用、
   不能时降级到纯内置实现，并在 ``self.tier`` 字段写明档位，**永不隐藏降级**。
   本类**不再 import 任何 pasm.* 内部模块** —— 这是 V1→V2 不重写智能体/技能的关键。
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
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .backend import (  # 引擎连接收敛到可替换后端（V1→V2 不重写智能体的关键）
    CognitiveBackend,
    create_v1_backend,
    _core_available,
    _now,
)


# ============================================================ 档位探测

def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


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
        backend: Optional["CognitiveBackend"] = None,
    ):
        self.agent_id = agent_id
        self.persona = dict(persona or {})
        self.persist_dir = Path(
            persist_dir or (Path.home() / ".pasm-agents" / agent_id)
        )
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        if seed is not None:
            random.seed(seed)

        # 引擎连接：优先用注入的后端（依赖注入），否则按 use_core 自动选 V1 后端。
        # 关键：BaseAgent 不再 import 任何 pasm.* 内部模块 —— 所有引擎连接都在
        # `pasm_skills.sdk.backend` 里。V2 只需提供一个实现了 CognitiveBackend 的
        # PasmV2Backend 并在工厂切换，这里与 4 智能体 / 3 技能一行不改。
        self._core = backend if backend is not None else create_v1_backend(
            self.persist_dir, self.persona, use_core=use_core, stage=0
        )
        self._core_ok = bool(getattr(self._core, "is_core", False))

        # 情绪系统由后端提供（None 表示走轻量情绪兜底）
        self._emo = getattr(self._core, "emotion_system", None)
        self._emo_ok = self._emo is not None

        # 加载已有 state.json
        self.state = self._load_state()

        # tier 标签（每次都重算；不存盘）
        if self._emo_ok and self._core_ok:
            self.tier = self.TIER_BIONIC
        elif self._core_ok:
            self.tier = self.TIER_CORE
        else:
            self.tier = self.TIER_LIGHT

        # 引导事件（仅首次）
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
        # 轻量后端（PasmV1LightBackend）同样有 feedback 实现，挡掉就等于
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
        # 用 action 名的关键词做软匹配。想让自己的动作名被识别，
        # 要么在名字里带下列关键词，要么在子类里覆盖本方法（没有 ACT_BIAS 之类的配置项）。
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



# ============================================================
# 引擎连接（PasmV1CoreBackend / PasmV1LightBackend / CognitiveBackend 协议）
# 已迁移到 `pasm_skills/sdk/backend.py`。
#
# 这里不再 import 任何 pasm.* 内部模块 —— 所有引擎连接都收敛在 backend.py，
# 这是 V1→V2 不重写 4 智能体 / 3 技能的关键（详见 backend.py 头部说明）。
