"""认知能力门面 —— **一份实现，多个表面**。

为什么要有这个模块
------------------
「观察 / 回忆 / 语义检索 / 焦点 / 巩固 / 感受 / 动作 / 反馈 / 人格 / 上下文 / 状态 / 落盘」
这套语义，此前在 MCP 服务里写过一遍。当 HTTP 表面也要这套能力时，如果照抄一份，
就会出现**同源两份代码**：改了一边忘了另一边，行为悄悄分叉。
本项目已经因为同源两份代码吃过一次亏（相关性闸门只回植了一边），所以这里把实现收敛。

- 本模块：**唯一的实现**，返回纯 ``dict``，不依赖任何协议。
- 各表面（MCP stdio / HTTP / CLI）只负责协议编解码与鉴权，逻辑一律调这里。

降级约定
--------
没装认知层（``pasm_skills.cognition.hub`` 不可用）时**不报错**：
退回 ``BaseAgent`` 的原生 ``recall``，并在返回值里用 ``mode="lexical"`` 如实申报。
—— 降级可以，装不知道不行。
"""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..sdk import BaseAgent

try:                                                    # pragma: no cover
    from .hub import CognitionHub, enhance, episodes_of
    _HAS_COG = True
except Exception:                                       # pragma: no cover
    CognitionHub = None                                 # type: ignore
    enhance = None                                      # type: ignore
    episodes_of = None                                  # type: ignore
    _HAS_COG = False


#: 未显式配置动作池时的默认动作。
#: 名字里刻意带 BaseAgent._fallback_weights 认得的关键词
#: （talk/share/teach/give → temper；hop/dance/run → energy；peek/play/joke → play），
#: 这样即使装在 light 档、没有真学习层，性格参数也仍然起作用。
DEFAULT_ACTIONS: List[str] = ["greet", "ask", "share", "teach", "listen"]

#: 默认人格。可被构造参数或环境变量整体覆盖。
DEFAULT_PERSONA: Dict[str, Any] = {
    "name": "小墨",
    "role": "认知陪伴",
    "tone": "温和、简洁",
    "temper": 0.5,      # 主动性
    "energy": 0.5,      # 活跃度
    "play": 0.5,        # 俏皮度
}

#: ``feedback`` 的合法取值。
FEEDBACK_KINDS = ("praise", "scold", "poke", "hug", "ignore")


class CapabilityAgent(BaseAgent):
    """通用认知智能体：动作池、人格、回复模板都可配置，其余交给基座。

    子类只需要覆盖 ``_render_reply``（或直接传 persona）就能变成不同的角色。
    """

    def action_pool(self) -> List[str]:
        acts = self.persona.get("actions")
        if isinstance(acts, list) and acts:
            return [str(a) for a in acts]
        return list(DEFAULT_ACTIONS)

    def bootstrap_event(self) -> List[Dict[str, Any]]:
        """首次启动写一条初始记忆 —— 让第一次 ``context`` 调用就不空手。"""
        name = self.persona.get("name", DEFAULT_PERSONA["name"])
        return [{
            "title": "初次相遇",
            "brief": f"{name}第一次接入，还没有任何共同经历。",
            "tags": ["初次", "相遇"],
            "salience": 3,
            "category": "关系",
        }]

    def _render_reply(self, text: str, facts: List[Dict[str, Any]], mood: float) -> str:
        """模板渲染。不带 LLM —— 保证无网、无 key、无 GPU 也能回话。"""
        name = self.persona.get("name", DEFAULT_PERSONA["name"])
        tone = self.persona.get("tone", "温和")
        parts: List[str] = []
        if facts:
            head = "；".join(str(f.get("title", "")) for f in facts[:2] if f.get("title"))
            if head:
                parts.append(f"我记得「{head}」")
        if mood > 0.25:
            parts.append("现在心情不错")
        elif mood < -0.25:
            parts.append("这会儿有点低落")
        if text:
            parts.append(f"你刚才说的是：{text[:40]}")
        body = "，".join(parts) if parts else "我还在熟悉你"
        return f"{name}（{tone}）：{body}。"

    def set_persona(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """**合并式**更新人格（不是整体替换 —— 漏传的键不该被抹掉）。"""
        if not isinstance(patch, dict):
            raise ValueError("persona 必须是对象")
        self.persona.update(patch)
        if hasattr(self, "state") and isinstance(self.state.persona, dict):
            self.state.persona.update(patch)
        return dict(self.persona)


class AgentRegistry:
    """按 ``agent_id`` 管理智能体实例，进程内缓存。

    同 id 多次调用**共享同一份记忆 / 情绪 / 动作权重** —— 这正是 PASM 的价值
    （跨调用连续的认知状态），而不是每次调用新建。
    """

    def __init__(self,
                 persist_root: Optional[str | Path] = None,
                 default_persona: Optional[Dict[str, Any]] = None,
                 agent_cls: type = CapabilityAgent,
                 *,
                 persist_env: str = "PASM_COG_PERSIST_DIR",
                 persona_env: str = "PASM_COG_PERSONA",
                 default_persist_dir: Optional[str | Path] = None) -> None:
        root = persist_root or os.environ.get(persist_env)
        if not root:
            root = default_persist_dir or (Path.home() / ".pasm-cog")
        self.persist_root = Path(root)
        self.persist_root.mkdir(parents=True, exist_ok=True)
        self.agent_cls = agent_cls

        self._default_persona = dict(DEFAULT_PERSONA)
        if default_persona:
            self._default_persona.update(default_persona)
        env_persona = os.environ.get(persona_env)
        if env_persona:
            import json
            try:
                self._default_persona.update(json.loads(env_persona))
            except Exception:
                pass
        self._agents: Dict[str, Any] = {}

    def get(self, agent_id: str = "default",
            persona: Optional[Dict[str, Any]] = None) -> Any:
        """取（或创建）一个智能体。

        人格的优先级：**构造入参 > 上次落盘的人格 > 默认人格**。

        ★ 为什么要主动读一次盘
        ----------------------
        ``BaseAgent._load_state`` 里有一行刻意设计：

            # persona 用当前传入的覆盖（外部可能更新），其余从盘里读
            st["persona"] = dict(self.persona)

        也就是说基座把 persona 当作**外部配置**，每次构造都用入参覆盖 ——
        于是"运行时改过的人格，重启就丢"。对产品智能体这是合理的（人格写在代码里），
        但对**提供 `persona` 写入接口**的表面来说就是名不副实：
        用户调了设置、也看到了成功，重启后却变回默认值。

        这里在本层补上持久化读取，**不动 BaseAgent**，因此不影响已发布的产品智能体。
        """
        if agent_id not in self._agents:
            p = dict(self._default_persona)
            saved = None if persona else self._saved_persona(agent_id)
            if saved:
                p.update(saved)
            if persona:
                p.update(persona)
            self._agents[agent_id] = self.agent_cls(
                agent_id=agent_id,
                persona=p,
                persist_dir=self.persist_root / agent_id,
            )
        return self._agents[agent_id]

    def _saved_persona(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """从落盘状态里读回上次保存的人格；读不到就返回 None（不抛错）。"""
        import json
        fname = getattr(self.agent_cls, "_STATE_FILE", "agent_state.json")
        p = self.persist_root / agent_id / fname
        if not p.exists():
            return None
        try:
            st = (json.loads(p.read_text(encoding="utf-8")) or {}).get("state") or {}
            saved = st.get("persona")
            return dict(saved) if isinstance(saved, dict) and saved else None
        except Exception:
            return None

    def agent_ids(self) -> List[str]:
        return sorted(self._agents.keys())

    def save_all(self) -> List[str]:
        """落盘所有已加载的智能体（进程退出前调用）。"""
        saved = []
        for aid, ag in self._agents.items():
            try:
                ag.save()
                saved.append(aid)
            except Exception:
                pass
        return saved

    def __repr__(self) -> str:                          # pragma: no cover
        return f"<AgentRegistry root={self.persist_root} agents={list(self._agents)}>"


class Capabilities:
    """认知能力门面。所有方法返回**纯 dict**，可直接 JSON 序列化。"""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    # ---------------------------------------------------------- 内部

    def _pair(self, agent_id: str) -> Tuple[Any, Optional[Any]]:
        """取 (智能体, 认知中枢)。中枢拿不到就返回 None —— 降级但不报错。"""
        ag = self.registry.get(agent_id)
        if not _HAS_COG or enhance is None:
            return ag, None
        hub = getattr(ag, "cognition", None)
        if hub is None:
            try:
                hub = enhance(ag)                        # type: ignore[misc]
            except Exception:
                return ag, None
        return ag, hub

    @staticmethod
    def _clamp_int(v: Any, lo: int, hi: int, dflt: int) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            n = dflt
        return max(lo, min(hi, n))

    # ---------------------------------------------------------- 只读

    def context(self, agent_id: str = "default", *,
                query: str = "", k: int = 5) -> Dict[str, Any]:
        """取认知上下文（**只读，不写记忆**）。注入提示词用的一号操作。"""
        ag, cog = self._pair(agent_id)
        k = self._clamp_int(k, 1, 50, 5)
        if cog is not None and query:
            facts = cog.recall(query, k=k)
        else:
            facts = ag.recall(query, k=k) if query else []
        return {
            "agent_id": ag.agent_id,
            "tier": ag.tier,
            "query": query,
            "cognition": ("semantic" if cog is not None else
                          "lexical（未装认知层，检索为字面匹配）"),
            "focus": (cog.focus.to_prompt() if cog is not None else ""),
            "recalled": [
                {
                    "title": f.get("title", ""),
                    "brief": f.get("brief", ""),
                    "tags": list(f.get("tags", [])),
                    "category": f.get("cat", f.get("category", "")),
                    "salience": f.get("sal", f.get("salience", 1)),
                }
                for f in facts
            ],
            "mood": round(float(ag.mood), 3),
            "persona": dict(ag.persona),
            "growth_stage": ag.state.growth_stage,
            "total_interactions": ag.state.total_interactions,
            "action_pool": ag.action_pool(),
            "hint": ("把 recalled 里的内容当作'你确实记得的事'写进回复；"
                     "mood 决定语气；action_pool 是当前可选行为。"),
        }

    def recall(self, agent_id: str = "default", *,
               query: str, k: int = 5) -> Dict[str, Any]:
        """记忆检索。装了认知层走**语义检索**（同义扩展 + 遗忘加权）。"""
        if not query:
            raise ValueError("query 不能为空")
        ag, cog = self._pair(agent_id)
        k = self._clamp_int(k, 1, 50, 5)
        hits = cog.recall(query, k=k) if cog is not None else ag.recall(query, k=k)
        return {
            "agent_id": ag.agent_id,
            "query": query,
            "mode": "semantic" if cog is not None else "lexical",
            "count": len(hits),
            "hits": [
                {
                    "title": f.get("title", ""),
                    "brief": f.get("brief", ""),
                    "tags": list(f.get("tags", [])),
                    "salience": f.get("sal", f.get("salience", 1)),
                    # 仅语义模式有：融合分 / 语义分 / 记忆保留度 / 被唤起次数
                    **({"score": f.get("score"), "semantic": f.get("semantic"),
                        "retention": f.get("retention"), "hits": f.get("hits")}
                       if cog is not None else {}),
                }
                for f in hits
            ],
        }

    def semantic(self, agent_id: str = "default", *, query: str, k: int = 5,
                 use_focus: bool = True,
                 use_forgetting: bool = True) -> Dict[str, Any]:
        """显式语义检索，并解释每一条**为什么**被召回（可解释性）。

        可解释性在医疗 / 风控场景是刚需：要能回答"你凭哪一条这么说的"。
        """
        if not query:
            raise ValueError("query 不能为空")
        ag, cog = self._pair(agent_id)
        k = self._clamp_int(k, 1, 50, 5)
        if cog is None:
            return {
                "agent_id": agent_id, "query": query, "mode": "lexical",
                "note": "未装认知层，退回字面匹配。",
                "hits": [{"title": f.get("title", ""), "brief": f.get("brief", "")}
                         for f in ag.recall(query, k=k)],
            }
        hits = cog.recall(query, k=k, use_focus=use_focus,
                          use_forgetting=use_forgetting)
        return {
            "agent_id": agent_id,
            "query": query,
            "mode": "semantic",
            "backend": getattr(cog.index.backend, "name", "?"),
            "expanded": cog.index.bridge.expand(query)[:8],
            "count": len(hits),
            "hits": [
                {
                    "title": h.get("title", ""),
                    "brief": h.get("brief", ""),
                    "tags": list(h.get("tags", [])),
                    "salience": h.get("sal", 1),
                    "score": h.get("score"),
                    "semantic": h.get("semantic"),
                    "retention": h.get("retention"),
                    "rehearsals": h.get("hits"),
                }
                for h in hits
            ],
            "hint": ("score = 语义×w + 记忆保留度×w + 重要度×w + 焦点加成。"
                     "retention 低说明这条很久没被唤起（正在遗忘）。"),
        }

    def focus(self, agent_id: str = "default", *, topic: str = "",
              entities: Optional[Iterable[str]] = None,
              weight: float = 1.0, n: int = 3) -> Dict[str, Any]:
        """焦点栈：查看或压入「现在在聊什么」。"""
        _, cog = self._pair(agent_id)
        if cog is None:
            return {"agent_id": agent_id, "ok": False,
                    "error": "需要已安装的认知层（pasm_skills.cognition）"}
        topic = (topic or "").strip()
        if topic:
            cog.focus.push(topic,
                           entities=[str(e) for e in (entities or [])],
                           weight=float(weight or 1.0))
        return {
            "agent_id": agent_id,
            "updated": bool(topic),
            "depth": len(cog.focus),
            "prompt": cog.focus.to_prompt(int(n or 3)),
            "stack": cog.focus.snapshot()[:8],
        }

    def status(self, agent_id: str = "default") -> Dict[str, Any]:
        """状态快照：档位、记忆量、情绪、反馈数、认知层状态。"""
        ag, cog = self._pair(agent_id)
        snap = ag.summary()
        snap["persist_dir"] = str(ag.persist_dir)
        snap["registry_root"] = str(self.registry.persist_root)
        snap["loaded_agents"] = self.registry.agent_ids()
        if cog is not None:
            try:
                eps = episodes_of(cog.agent) if episodes_of else []
                snap["cognition"] = {
                    "enabled": True,
                    "embedding_backend": cog.index.backend.name,
                    "indexed": len(cog.index),
                    "focus": cog.focus.to_prompt(),
                    "focus_depth": len(cog.focus),
                    "archive": cog.archive.stats(),
                    "memory": cog.curve.decay_report(eps),
                }
            except Exception as ex:
                snap["cognition"] = {"enabled": True, "error": str(ex)}
        else:
            snap["cognition"] = {"enabled": False,
                                 "hint": "安装认知层后自动启用（pasm-skills）"}
        return snap

    # ---------------------------------------------------------- 写入

    def observe(self, agent_id: str = "default", *, title: str, brief: str = "",
                tags: Optional[Iterable[str]] = None, salience: int = 2,
                category: str = "日常") -> Dict[str, Any]:
        """写入一条经历（记忆）。"""
        title = (title or "").strip()
        if not title:
            raise ValueError("title 不能为空")
        sal = self._clamp_int(salience, 1, 5, 2)
        ag, cog = self._pair(agent_id)
        kw = dict(title=title, brief=brief,
                  tags=[str(t) for t in (tags or [])],
                  salience=sal, category=category or "日常")
        if cog is not None:
            # 走中枢：写记忆 + 同步语义索引 + 更新焦点，一次做完
            cog.observe(**kw)
        else:
            ag.observe(**kw)
        ag.save()
        return {
            "agent_id": ag.agent_id,
            "ok": True,
            "title": title,
            "salience": sal,
            "total_interactions": ag.state.total_interactions,
        }

    def feel(self, agent_id: str = "default", *, event: str,
             valence: float = 0.0) -> Dict[str, Any]:
        """报告一个带情绪效价的事件。"""
        event = (event or "").strip()
        if not event:
            raise ValueError("event 不能为空")
        v = max(-1.0, min(1.0, float(valence or 0.0)))
        ag = self.registry.get(agent_id)
        ag.feel(event, v)
        ag.save()
        return {
            "agent_id": ag.agent_id,
            "event": event,
            "valence": v,
            "mood": round(float(ag.mood), 3),
            "emotion_backend": ("pasm.modules.emotion" if ag._emo_ok else "fallback"),
        }

    def act(self, agent_id: str = "default",
            candidates: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """从动作池里按「性格 + 学到的偏好」选一个动作。"""
        ag = self.registry.get(agent_id)
        if candidates:
            pool = [str(c) for c in candidates if str(c)]
            if not pool:
                raise ValueError("candidates 不能是空数组")
            chosen = self._act_with_pool(ag, pool)
        else:
            chosen = ag.act()
            pool = ag.action_pool()
        return {"agent_id": ag.agent_id, "chosen": chosen, "pool": list(pool)}

    @staticmethod
    def _act_with_pool(ag: Any, pool: List[str]) -> str:
        """用指定候选池走一次动作选择（**复用基座的学习层，不绕过反馈**）。"""
        picker = getattr(ag._core, "learn_pick", None)
        if picker is not None:
            try:
                got = picker(pool, base=ag._fallback_weights(pool),
                             persona=ag.persona, stage=ag.state.growth_stage)
                if got in pool:
                    return got
            except Exception:
                pass
        return random.choices(pool, weights=ag._fallback_weights(pool), k=1)[0]

    def feedback(self, agent_id: str = "default", *, kind: str,
                 action: Optional[str] = None) -> Dict[str, Any]:
        """外部反馈塑形。**强烈建议带 action**，否则长期会让动作分布极端化。"""
        kind = (kind or "").strip()
        if kind not in FEEDBACK_KINDS:
            raise ValueError("kind 必须是 %s 之一" % ", ".join(sorted(FEEDBACK_KINDS)))
        ag = self.registry.get(agent_id)
        weights = ag.feedback(kind, action=str(action) if action else None)
        ag.save()
        return {
            "agent_id": ag.agent_id,
            "kind": kind,
            "action": action,
            "weights": {k: round(float(v), 3) for k, v in (weights or {}).items()},
            "warning": (None if action else
                        "未指定 action：反馈作用在了当前最偏好的动作上，"
                        "长期会让行为分布极端化（基座已知特性，建议明确传 action）。"),
        }

    def consolidate(self, agent_id: str = "default", *,
                    apply: bool = False) -> Dict[str, Any]:
        """记忆巩固（睡眠回放）：把高度相似的重复经历蒸馏成要点。

        ``apply=False``（默认）**只给建议，不落盘**。
        """
        _, cog = self._pair(agent_id)
        if cog is None:
            return {"agent_id": agent_id, "ok": False,
                    "error": "需要已安装的认知层（pasm_skills.cognition）"}
        rep = cog.consolidate(apply=apply)
        return {
            "agent_id": agent_id,
            "applied": apply,
            **rep.as_dict(),
            "hint": ("这是建议，未落盘。想执行请再调一次并传 apply=true。"
                     if not apply else "已写入要点记忆，源条目标记为已合并。"),
        }

    def chat(self, agent_id: str = "default", *, text: str) -> Dict[str, Any]:
        """走完整认知回路对话一次：检索 → 渲染 → 写入记忆。

        注意：回复是**模板渲染**的，不是 LLM 生成。
        要自然语言请用 ``context`` + 你自己的模型 —— PASM 出记忆与倾向，
        语言生成交给客户端模型，这样语料与合规边界都在你手里。
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("text 不能为空")
        ag = self.registry.get(agent_id)
        facts = ag.recall(text, k=3)
        reply = ag.chat(text)
        ag.save()
        return {
            "agent_id": ag.agent_id,
            "reply": reply,
            "cognitive": {
                "recalled": [f.get("title", "") for f in facts],
                "mood": round(float(ag.mood), 3),
                "tier": ag.tier,
                "total_interactions": ag.state.total_interactions,
            },
            "note": "模板渲染，非 LLM 生成；接 LLM 请用 context。",
        }

    def persona(self, agent_id: str = "default",
                patch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """查看或（合并式）更新人格。"""
        ag = self.registry.get(agent_id)
        if patch:
            if not isinstance(patch, dict):
                raise ValueError("persona 必须是对象")
            ag.set_persona(patch)
            ag.save()
        return {"agent_id": ag.agent_id, "persona": dict(ag.persona),
                "updated": bool(patch)}

    def save(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """把当前智能体状态落盘。不传 agent_id 则落盘全部。"""
        if agent_id:
            ag = self.registry.get(agent_id)
            return {"saved": [str(ag.save())]}
        return {"saved": self.registry.save_all()}

    # ---------------------------------------------------------- 元信息

    def operations(self) -> List[str]:
        """本门面暴露的操作名（表面层据此生成路由 / 工具清单，避免手工维护漂移）。"""
        return ["context", "recall", "semantic", "focus", "status", "observe",
                "feel", "act", "feedback", "consolidate", "chat", "persona", "save"]


# ============================================================ 自检

def selftest() -> bool:
    """自检：真起智能体、真落盘、真检索，并带反例。"""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="pasm-caps-")
    ok = fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  v %s" % name)
        else:
            fail += 1
            print("  x %s%s" % (name, ("  <- " + detail) if detail else ""))

    print("pasm_skills.cognition.capabilities 自检")
    print("-" * 60)
    try:
        reg = AgentRegistry(persist_root=os.path.join(tmp, "hub"),
                            persist_env="_NOPE_", persona_env="_NOPE_")
        caps = Capabilities(reg)

        check("操作清单覆盖 13 项", len(caps.operations()) == 13,
              str(caps.operations()))

        # ---- 写入 + 隔离
        caps.observe("p1", title="青霉素过敏", brief="皮疹", tags=["过敏"], salience=5)
        caps.observe("p2", title="磺胺过敏", brief="发热", tags=["过敏"], salience=5)
        r1 = caps.recall("p1", query="过敏")
        r2 = caps.recall("p2", query="过敏")
        t1 = [h["title"] for h in r1["hits"]]
        t2 = [h["title"] for h in r2["hits"]]
        check("按 agent_id 隔离：各自只看到自己的记忆",
              "青霉素过敏" in t1 and "磺胺过敏" not in t1 and
              "磺胺过敏" in t2 and "青霉素过敏" not in t2,
              "p1=%s p2=%s" % (t1, t2))

        # ---- 反例：空 query 必须报错（不能被静默吞掉返回空）
        try:
            caps.recall("p1", query="")
            check("空 query 抛 ValueError", False, "没抛")
        except ValueError:
            check("空 query 抛 ValueError", True)
        try:
            caps.feel("p1", event="", valence=0)
            check("空 event 抛 ValueError", False, "没抛")
        except ValueError:
            check("空 event 抛 ValueError", True)
        try:
            caps.feedback("p1", kind="nonsense")
            check("非法 feedback kind 抛 ValueError", False, "没抛")
        except ValueError:
            check("非法 feedback kind 抛 ValueError", True)

        # ---- 情绪
        f = caps.feel("p1", event="被夸奖", valence=0.8)
        check("feel 改变心情", -1.0 <= f["mood"] <= 1.0 and "emotion_backend" in f,
              str(f))
        check("valence 被夹到 [-1,1]",
              caps.feel("p1", event="越界", valence=99)["valence"] == 1.0)

        # ---- 动作 + 反馈
        a = caps.act("p1", candidates=["talk", "hop", "peek"])
        check("act 只从给定候选池里选", a["chosen"] in ["talk", "hop", "peek"], str(a))
        fb = caps.feedback("p1", kind="praise", action=a["chosen"])
        check("feedback 返回权重且无警告（带了 action）",
              isinstance(fb["weights"], dict) and fb["warning"] is None, str(fb))
        fb2 = caps.feedback("p1", kind="scold")
        check("不带 action 的反馈会给出警告", bool(fb2["warning"]))

        # ---- 人格
        p = caps.persona("p1", {"name": "医疗助手"})
        check("persona 合并式更新（未传的键保留）",
              p["persona"]["name"] == "医疗助手" and "tone" in p["persona"], str(p))

        # ---- 焦点 / 巩固 / 状态
        caps.focus("p1", topic="用药安全", entities=["青霉素"])
        check("焦点栈可压入", caps.focus("p1")["depth"] >= 1)
        caps.consolidate("p1", apply=False)
        check("consolidate 默认不落盘时给出 hint",
              "hint" in caps.consolidate("p1", apply=False))
        st = caps.status("p1")
        check("status 含档位与认知层段", "tier" in st and "cognition" in st, str(list(st)))
        check("status 列出已加载 agent", "p1" in st["loaded_agents"] and "p2" in st["loaded_agents"])

        # ---- chat 模板渲染（不依赖 LLM）
        ch = caps.chat("p1", text="你好")
        check("chat 在无 LLM 下也能回话", bool(ch["reply"]), str(ch))

        # ---- 落盘 + 重启恢复
        caps.save()
        check("save 落盘成功", len(caps.save()["saved"]) >= 2)
        reg2 = AgentRegistry(persist_root=os.path.join(tmp, "hub"),
                             persist_env="_NOPE_", persona_env="_NOPE_")
        caps2 = Capabilities(reg2)
        check("重启后记忆可恢复", caps2.recall("p1", query="过敏")["count"] >= 1,
              str(caps2.recall("p1", query="过敏")))
        check("重启后人格可恢复",
              caps2.status("p1").get("persona", {}).get("name") == "医疗助手",
              str(caps2.status("p1").get("persona")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 60)
    print("结果：%d 项通过，%d 项失败" % (ok, fail))
    return fail == 0


if __name__ == "__main__":                              # pragma: no cover
    import sys
    sys.exit(0 if selftest() else 1)
