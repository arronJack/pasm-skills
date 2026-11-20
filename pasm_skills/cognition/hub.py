"""认知中枢 —— 把语义检索 / 遗忘曲线 / 巩固 / 焦点栈 / 心跳 / 工具
一次性接到任何 :class:`~pasm_skills.sdk.BaseAgent` 上。

这是"能力补全"的**装配层**：下面各模块都是独立可用的零件，
本模块负责把它们接成一套，并且**不修改 BaseAgent 一行代码**。

用法（两行接入，零侵入）::

    from pasm_skills.cognition import enhance

    agent = MyAgent("tutor-1", persona={...})
    cog = enhance(agent)              # 挂上全部认知能力
    cog.observe(title="姓名", brief="小明", tags=["身份"], salience=4)
    hits = cog.recall("我叫什么名字")   # ← 字面匹配做不到，这里能命中

设计要点
--------
- **旁挂（sidecar）而非改写**：PASM 核心档与轻量档存储结构不同，
  中枢用 sidecar 文件记录"复习次数 / 已合并 / 已归档"，
  两个档位共用一套逻辑，且不破坏任何一方的数据。
- **档位无关**：不依赖 torch、不依赖核心，装上核心自动受益。
- **可观测**：:meth:`snapshot` 一次给出向量后端、记忆强度分布、焦点、归档、
  心跳状态 —— 便于确认"到底哪套能力在生效"。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .focus import FocusStack
from .forgetting import ArchiveStore, Consolidator, ConsolidationReport, ForgettingCurve
from .semantic import SemanticIndex, auto_backend, EmbeddingBackend, SynonymBridge
from .tick import TickLoop
from .tools import ToolRegistry

__all__ = ["CognitionHub", "enhance", "episodes_of", "episode_key"]


def _now() -> float:
    return time.time()


#: 可读时间的常见格式（按出现概率排序）。``_to_epoch`` 宽容解析用。
_TS_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
)


def _to_epoch(value: Any, default: float = 0.0) -> float:
    """把各种形态的 ``ts`` 归一成 epoch 秒（float）。**绝不抛异常。**

    ★★ 为什么必须容错 —— 0.6.6 的 P0 回归教训（2026-11-20）
    ------------------------------------------------------
    0.6.6 修了"recall 从内层 meta 取 sal/ts/cat"（提交 6240ea0）：取值层级修对了，
    但**没校验值类型**，直接 ``float(rec["ts"])``。
    而 V1 记忆层写入的 episode 里 ``ts`` 是**可读时间字符串**（``'2026-11-20 14:06'``），
    于是 ``float()`` 抛 ``ValueError`` → **召回整条链路崩掉**（不是降级，是抛异常）。
    该版本已发 PyPI/三端，用 V1 backend 且有记忆的用户一召回就崩。

    **根因是类型假设**：轻量档写 epoch float、核心档（V1）写可读时间，
    中枢作为跨档位共享的读取路径，不能假设上游字段类型一致。

    接受：``int`` / ``float``（epoch 秒）/ 数字串 / 可读时间串（多种格式）。
    其余（``None`` / 空串 / 无法解析）→ 返回 ``default``。
    遗忘曲线拿不到准确时间最多是"衰减算得不准"，**不该让召回整体失败** ——
    「算不准」和「功能不可用」是两个量级的后果。

    ⚠️ ``bool`` 要排除：它是 ``int`` 子类，不排除会把 ``True`` 当 1.0 秒。
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value or "").strip()
    if not s:
        return default
    try:
        return float(s)                      # 数字串（"1732082760.0"）
    except ValueError:
        pass
    for fmt in _TS_FORMATS:
        try:
            return time.mktime(time.strptime(s, fmt))
        except ValueError:
            continue
    return default


def episodes_of(agent: Any) -> List[Dict[str, Any]]:
    """从 BaseAgent 里取出记忆条目列表（跨档位）。

    - 轻量档 ``_LightAdapter`` 有 ``_episodes`` 列表
    - 核心档 ``_CoreAdapter`` 持 ``_mem``（真 PASM 记忆层），用 ``episodes()``
    """
    core = getattr(agent, "_core", None)
    if core is None:
        return []
    eps = getattr(core, "_episodes", None)
    if isinstance(eps, list):
        return [e for e in eps if isinstance(e, dict)]
    # ★ 优先走 backend 的**带作用域**入口：core 后端的 ``_mem`` 是模块单例，
    #   直接读会拿到「最后一次 set_data_dir 的那个 agent」的目录 ——
    #   同进程多 agent 时会读到别人的记忆（医疗场景 = 跨患者泄露）。
    fn = getattr(core, "episodes", None)
    if callable(fn):
        try:
            return [e for e in fn() if isinstance(e, dict)]
        except Exception:
            pass
    mem = getattr(core, "_mem", None)
    fn = getattr(mem, "episodes", None)
    if callable(fn):
        try:
            return [e for e in fn() if isinstance(e, dict)]
        except Exception:
            return []
    return []


def episode_key(rec: Dict[str, Any], idx: int = 0) -> str:
    """一条记忆的稳定键（用于索引 / 归档 / 复习计数）。"""
    title = str(rec.get("title") or "")
    ts = rec.get("ts") or rec.get("time") or idx
    return f"{title}|{ts}"


class CognitionHub:
    """绑定到一个 BaseAgent 的认知中枢。"""

    #: sidecar 文件名
    FILE_INDEX = "cognition_index.json"
    FILE_REHEARSE = "cognition_rehearsal.json"

    def __init__(
        self,
        agent: Any,
        persist_dir: Optional[str | Path] = None,
        backend: Optional[EmbeddingBackend] = None,
        *,
        half_life_days: float = 2.0,
        w_semantic: float = 0.62,
        w_retention: float = 0.24,
        w_salience: float = 0.14,
        tick_interval: float = 60.0,
        idle_after: float = 180.0,
        auto_tick: bool = False,
    ):
        self.agent = agent
        base_dir = persist_dir or getattr(agent, "persist_dir", None) or (
            Path.home() / ".pasm-agents" / "default")
        self.persist_dir = Path(base_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.backend = backend or auto_backend()
        self.index = SemanticIndex(backend=self.backend)
        self.curve = ForgettingCurve(half_life_days=half_life_days)
        self.consolidator = Consolidator(self.curve)
        self.focus = FocusStack()
        self.archive = ArchiveStore(self.persist_dir / "cognition_archive.json")
        self.tick = TickLoop(interval=tick_interval, idle_after=idle_after,
                             name=str(getattr(agent, "agent_id", "pasm")))
        self.tools = ToolRegistry()

        self.w_semantic = float(w_semantic)
        self.w_retention = float(w_retention)
        self.w_salience = float(w_salience)

        self._rehearsal: Dict[str, int] = {}
        self._load()
        self.reindex()

        if auto_tick:
            self.install_default_ticks()

        # 反向挂载，方便 agent.cognition.recall(...) 直接用
        try:
            setattr(agent, "cognition", self)
        except Exception:
            pass

    # ------- 持久化 -------------------------------------------------

    def _load(self) -> None:
        self.index.load(self.persist_dir / self.FILE_INDEX)
        self.focus.load(self.persist_dir / FocusStack.FILE)
        rp = self.persist_dir / self.FILE_REHEARSE
        if rp.exists():
            try:
                self._rehearsal = json.loads(rp.read_text(encoding="utf-8"))
            except Exception:
                self._rehearsal = {}

    def save(self) -> Dict[str, str]:
        """落盘全部 sidecar（进程退出前 / 定时调用）。"""
        out: Dict[str, str] = {}
        out["index"] = str(self.index.save(self.persist_dir / self.FILE_INDEX))
        out["focus"] = str(self.focus.save(self.persist_dir / FocusStack.FILE))
        out["archive"] = str(self.archive.save())
        rp = self.persist_dir / self.FILE_REHEARSE
        rp.write_text(json.dumps(self._rehearsal, ensure_ascii=False),
                      encoding="utf-8")
        out["rehearsal"] = str(rp)
        return out

    # ------- 索引 ---------------------------------------------------

    def reindex(self, force: bool = False) -> int:
        """把记忆条目同步进语义索引。返回索引条目数。"""
        eps = episodes_of(self.agent)
        known = set(self.index.keys())
        changed = 0
        for i, rec in enumerate(eps):
            key = episode_key(rec, i)
            if key in known and not force:
                continue
            self.index.add(
                key,
                title=str(rec.get("title") or ""),
                text=str(rec.get("brief") or rec.get("text") or ""),
                tags=list(rec.get("tags") or []),
                meta={"sal": rec.get("sal"),
                      # ★ 写入侧也归一化（双保险）：读侧容错保证"旧数据能读"，
                      #   写入侧归一保证"新数据不再产生脏类型"。
                      #   两处都做是因为脏数据可能来自任何版本的旧索引 ——
                      #   只修读侧等于永远在给历史数据擦屁股。
                      "ts": _to_epoch(rec.get("ts"), 0.0),
                      "cat": rec.get("cat") or rec.get("category")},
            )
            changed += 1
        return len(self.index)

    # ------- 记忆 ---------------------------------------------------

    def observe(self, title: str, brief: str = "", tags: Optional[Iterable[str]] = None,
                *, salience: int = 1, category: str = "日常",
                topic: Optional[str] = None) -> None:
        """写记忆 + 同步索引 + 更新焦点（一次调用三件事都做）。"""
        self.agent.observe(title=title, brief=brief, tags=tags,
                           salience=salience, category=category)
        self.reindex()
        if topic or title:
            try:
                self.focus.push(topic or title, entities=list(tags or [])[:4])
            except Exception:
                pass

    def recall(self, query: str, k: int = 5, *,
               use_focus: bool = True, use_forgetting: bool = True,
               min_score: float = 0.03,
               min_relevance: float = 0.0) -> List[Dict[str, Any]]:
        """认知检索：**语义 + 保留度 + 重要度 + 焦点** 四路融合。

        与 ``BaseAgent.recall`` 的差别
        ------------------------------
        - 语义：走 :class:`SemanticIndex`（含同义扩展），不再纯字面
        - 保留度：走 :class:`ForgettingCurve`，久未唤起的记忆自然降权
        - 焦点：当前话题涉及的实体获得加权（解决长对话跑题）
        - 复习：命中的记忆会累加 ``hits``，下次半衰期变长（复习效应）

        ``min_relevance``（可选相关性闸门）
        ----------------------------------
        融合分里的 ``retention/salience`` 是**常驻基线**，语义为 0 时仍非零，
        因此 ``min_score`` 无法拦截"无关查询也返回具体事实"。本闸门改用
        **top1 语义分领先候选均值的幅度**（后端无关的相对量）：

            signal = sem_top1 - mean(所有候选的 semantic)

        设 >0 时，signal 低于该值的命中被滤除；返回空列表是**有效结论**（
        "没有能支撑这个问题的记忆"），调用方应据此如实告知而非编造。
        默认 0.0 = 不启用，避免误杀（离线 hashing 后端语义噪声大，实测
        单一阈值 AUC 最高仅 0.935，不做硬编码默认值）。

        ⚠️ 阈值不可移植：signal 依赖**候选池规模与 k**（候选越多、越同质，
        相关项的 signal 越小）。同一阈值在小语料上能干净分离、在大语料上
        可能大面积误杀。部署方必须用 **与自己后端/语料/k 相同口径** 标定，
        参见 analysis/tools/gate_full_features.py 与 relevance_gate_verify.py。
        实测 hashing 后端：k=5、0.15 阈值可拦住全部无关查询，但误杀约
        45% 相关；这是离线语义退化的表现，嵌入后端预期显著改善（未实测）。
        """
        self.reindex()
        q = (query or "").strip()
        if not q:
            return []
        hits = self.index.search(q, k=max(k * 4, 20), min_score=0.0)
        focus_ents = set(self.focus.current_entities()) if use_focus else set()
        now = _now()
        out: List[Dict[str, Any]] = []
        for h in hits:
            if self.archive.is_hidden(h.key):
                continue
            meta = h.meta or {}
            # reindex() 通过 SemanticIndex.add(meta={...}) 写入的 sal/ts/cat 落在
            # **第二层** meta["meta"]（SemanticIndex.add 把 title/text/tags 放外层、
            # meta 整体塞进 "meta" 键）。此前这里只取外层 → sal/ts/cat 全部丢失：
            # sal 恒 1（显著度排序退化成召回顺序、关键事实护城河失效）、
            # ts 恒 0（遗忘曲线失效）、cat 恒空（分类过滤失效）。
            # 兼容：内层优先，回退外层（手工构造的扁平 meta / 旧索引仍能读）。
            inner = meta.get("meta") or {}
            if not isinstance(inner, dict):
                inner = {}
            rec = {
                "title": meta.get("title") or "",
                "brief": meta.get("text") or "",
                "tags": meta.get("tags") or [],
                "sal": inner.get("sal") or meta.get("sal") or 1,
                # 这里保留原值不归一，归一交给 _to_epoch —— 因为既有 sidecar 索引里
                # 可能存着**字符串 ts**（V1 写的可读时间），在构造 rec 时就地转型
                # 会把"脏数据"静默洗掉、掩盖上游问题；放到使用点转型则一眼能看出
                # "这个字段类型不受控"。
                "ts": inner.get("ts") or meta.get("ts") or 0.0,
                "cat": inner.get("cat") or meta.get("cat") or "",
                "hits": self._rehearsal.get(h.key, 0),
                "_key": h.key,
            }
            # ★★ 原为 ``float(rec["ts"] or now)`` —— 假设 ts 一定是数字，
            #    V1 写的可读时间字符串会让这里抛 ValueError、**整条召回崩掉**（0.6.6 回归）。
            #    改用 _to_epoch：数字/数字串/可读时间都吃得下，实在解析不了就退回 now
            #    （「当作刚写入」比「整条召回失效」合理得多）。
            ret = (self.curve.retention(max(0.0, now - _to_epoch(rec["ts"] or now, now)),
                                        int(rec["sal"] or 1), int(rec["hits"]))
                   if use_forgetting else 1.0)
            sal_w = (0.6 + 0.1 * max(1, min(5, int(rec["sal"] or 1)))) / 1.1
            bonus = 0.0
            if focus_ents:
                if focus_ents & set(rec["tags"]):
                    bonus = 0.12
                elif any(e and e in (rec["title"] + rec["brief"]) for e in focus_ents):
                    bonus = 0.06
            score = (self.w_semantic * h.score
                     + self.w_retention * ret
                     + self.w_salience * sal_w
                     + bonus)
            if score < min_score:
                continue
            rec["score"] = round(score, 4)
            rec["semantic"] = round(h.score, 4)
            rec["retention"] = round(ret, 4)
            out.append(rec)
        out.sort(key=lambda r: r["score"], reverse=True)
        # 去重：同一件事被反复写入会产生多条内容相同的记忆（跨会话累积很常见），
        # 全返回会让上下文被同一件事刷满。按 (title, brief) 保留分最高的那条。
        deduped: List[Dict[str, Any]] = []
        seen: set = set()
        for r in out:
            sig = (r.get("title", ""), r.get("brief", ""))
            if sig in seen:
                continue
            seen.add(sig)
            deduped.append(r)
        top = deduped[: max(1, int(k))]
        # ---- 可选相关性闸门（min_relevance > 0 时启用） ----
        # signal = top1 语义分 - 本批命中语义分均值（后端无关的相对量）。
        # 与 `relevance_gate_calibrate` 的口径一致：都用 recall 最终返回的
        # 这批命中算 mean，阈值由调用方按自己后端标定，引擎不硬编码。
        sem_vals = [float(r.get("semantic") or 0.0) for r in top]
        sem_mean = (sum(sem_vals) / len(sem_vals)) if sem_vals else 0.0
        signal = (max(sem_vals) - sem_mean) if sem_vals else 0.0
        for r in top:
            r["relevance"] = round(float(r.get("semantic") or 0.0) - sem_mean, 4)
        if min_relevance > 0 and signal < min_relevance:
            # 无能支撑此问题的记忆 —— 返回空是有效结论，且**不产生**
            # 复习效应/焦点更新（无关查询不该强化任何记忆或带偏焦点）。
            return []
        # 复习效应：命中一次，半衰期变长
        for r in top:
            key = r["_key"]
            self._rehearsal[key] = self._rehearsal.get(key, 0) + 1
        if use_focus:
            try:
                self.focus.push(q[:32], weight=0.6)
            except Exception:
                pass
        return top

    # ------- 巩固 ---------------------------------------------------

    def _sim(self, eps: Sequence[Dict[str, Any]]):
        """构造 (i, j) -> 相似度。带缓存，且直接读索引向量（不重复编码）。"""
        keys = [episode_key(e, i) for i, e in enumerate(eps)]
        cache: Dict[tuple, float] = {}

        def sim(i: int, j: int) -> float:
            if i == j:
                return 1.0
            a, b = (i, j) if i < j else (j, i)
            k = (a, b)
            if k in cache:
                return cache[k]
            try:
                v = self.index.similarity(keys[a], keys[b])
            except Exception:
                v = 0.0
            cache[k] = v
            return v

        return sim

    def consolidate(self, apply: bool = False) -> ConsolidationReport:
        """记忆巩固。``apply=False`` 时只给建议（不落盘）。"""
        self.reindex()
        eps = episodes_of(self.agent)
        rep = self.consolidator.plan(eps, sim_fn=self._sim(eps))
        if apply:
            for g in rep.gists:
                self.observe(
                    title=g["title"], brief=g["brief"], tags=g["tags"],
                    salience=g["sal"], category=g.get("category", "巩固"),
                )
                self.archive.mark_merged(g.get("sources", []))
            if rep.archived:
                self.archive.archive(rep.archived)
            self.reindex()
            self.save()
        return rep

    # ------- 心跳 ---------------------------------------------------

    def install_default_ticks(self, *, consolidate_every: int = 20,
                              save_every: int = 5) -> List[str]:
        """装上默认后台任务：定时巩固 + 定时落盘 + 焦点衰减。"""
        names: List[str] = []

        def _consolidate(ctx):
            r = self.consolidate(apply=True)
            return {"groups": r.groups, "merged": r.merged}

        def _save(ctx):
            self.save()
            return {"saved": True}

        def _focus(ctx):
            self.focus.decay()
            return {"focus": len(self.focus)}

        self.tick.register(_consolidate, name="consolidate",
                           every=max(1, consolidate_every), tags=["memory"])
        self.tick.register(_save, name="persist", every=max(1, save_every))
        self.tick.register(_focus, name="focus-decay", every=1)
        names.extend(["consolidate", "persist", "focus-decay"])
        return names

    # ------- 观测 ---------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """一次看全：哪套向量后端、记忆强度分布、焦点、归档、心跳、工具。"""
        eps = episodes_of(self.agent)
        decay = self.curve.decay_report(eps)
        merged = set(self.archive.data.get("merged") or [])
        return {
            "agent_id": str(getattr(self.agent, "agent_id", "")),
            "tier": str(getattr(self.agent, "tier", "")),
            "persist_dir": str(self.persist_dir),
            "semantic": self.index.stats(),
            "synonym_groups": len(SynonymBridge()._groups),
            "memory": {
                "episodes": len(eps),
                "indexed": len(self.index),
                **decay,
            },
            "archive": self.archive.stats(),
            "rehearsal_tracked": len(self._rehearsal),
            "focus": self.focus.snapshot()[:3],
            "focus_prompt": self.focus.to_prompt(),
            "tick": self.tick.stats(),
            "tools": self.tools.stats(),
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<CognitionHub agent={getattr(self.agent,'agent_id','?')!r} "
                f"backend={self.index.backend.name} docs={len(self.index)}>")


def enhance(agent: Any, **kw: Any) -> CognitionHub:
    """给一个 BaseAgent 挂上全部认知能力（幂等）。"""
    existing = getattr(agent, "cognition", None)
    if isinstance(existing, CognitionHub):
        return existing
    return CognitionHub(agent, **kw)
