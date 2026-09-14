"""遗忘曲线与记忆巩固 —— 补上 PASM 学习层长期缺失的两块。

真实问题
--------
1. **没有遗忘**：停练 25 天的知识点和昨天刚练的一样强 → 学情失真，
   而且记忆池里塞满了早就该淡化的旧事，检索噪声越来越大。
2. **没有巩固**：只进不出，没有"睡眠回放"把重复经历蒸馏成稳定认知。

设计原则
--------
**不删除数据，只改变权重。** 直接删记忆风险太高（可能是用户唯一一次提过的重要事），
所以遗忘体现在**检索打分**上（越久没被唤起，分数越低），
只有当强度低于阈值且被判定为低价值时才允许**归档**（移到 sidecar，仍可恢复）。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

__all__ = ["ForgettingCurve", "Consolidator", "ConsolidationReport"]


def _now() -> float:
    return time.time()


# ============================================================ 遗忘曲线

@dataclass
class ForgettingCurve:
    """艾宾浩斯式指数遗忘。

    ``retention = 0.5 ** (age_days / half_life)``

    半衰期受三件事影响（这三条是对"重要的事记得更久"的建模）：

    - **salience（重要度 1-5）**：每高一级，半衰期 × ``salience_factor``
    - **rehearsal（被唤起次数）**：每次被检索命中，半衰期 × ``rehearsal_factor``
      —— 这就是"复习"的力学解释，也是为什么高频记忆不会自然消失
    - **floor**：保留度下限。设下限而非归零，是因为"彻底忘记"在对话场景里
      体验很差（用户会觉得智能体突然不认识自己了）
    """

    half_life_days: float = 2.0
    salience_factor: float = 1.8
    rehearsal_factor: float = 1.6
    floor: float = 0.05
    max_half_life_days: float = 365.0

    def half_life(self, sal: int = 1, rehearsals: int = 0) -> float:
        """返回半衰期（天）。"""
        sal = max(1, min(5, int(sal or 1)))
        hl = self.half_life_days * (self.salience_factor ** (sal - 1))
        if rehearsals:
            hl *= self.rehearsal_factor ** min(int(rehearsals), 10)
        return min(hl, self.max_half_life_days)

    def retention(self, age_seconds: float, sal: int = 1,
                  rehearsals: int = 0) -> float:
        """记忆保留度 ∈ [floor, 1]。"""
        age_days = max(0.0, float(age_seconds)) / 86400.0
        hl = self.half_life(sal, rehearsals)
        if hl <= 0:
            return self.floor
        r = 0.5 ** (age_days / hl)
        return max(self.floor, min(1.0, r))

    def strength(self, rec: Dict[str, Any], now: Optional[float] = None) -> float:
        """一条记忆当前的强度（含重要度加权）。

        ``strength = retention * salience_weight``
        重要度本身也参与排序 —— 重要的旧事仍然排在不重要的新事前面。
        """
        now = _now() if now is None else now
        ts = float(rec.get("ts") or rec.get("time") or 0.0) or now
        sal = int(rec.get("sal") or rec.get("salience") or 1)
        reh = int(rec.get("hits") or rec.get("rehearse") or 0)
        base = self.retention(max(0.0, now - ts), sal, reh)
        return round(base * (0.6 + 0.1 * max(1, min(5, sal))), 4)

    def decay_report(self, episodes: Sequence[Dict[str, Any]],
                     now: Optional[float] = None) -> Dict[str, Any]:
        """给一批记忆做体检（给 ``status`` / 调试面板用）。"""
        now = _now() if now is None else now
        if not episodes:
            return {"count": 0, "avg_retention": 0.0, "faded": 0, "strong": 0}
        rets = [self.retention(max(0.0, now - float(e.get("ts") or now)),
                               int(e.get("sal") or 1),
                               int(e.get("hits") or 0)) for e in episodes]
        return {
            "count": len(episodes),
            "avg_retention": round(sum(rets) / len(rets), 4),
            "faded": sum(1 for r in rets if r <= 0.15),
            "strong": sum(1 for r in rets if r >= 0.6),
        }


# ============================================================ 记忆巩固

@dataclass
class ConsolidationReport:
    """一次巩固的结果（可序列化，给 API / CLI 用）。"""

    scanned: int = 0
    groups: int = 0
    merged: int = 0
    gists: List[Dict[str, Any]] = field(default_factory=list)
    archived: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "scanned": self.scanned,
            "groups": self.groups,
            "merged": self.merged,
            "gists": self.gists,
            "archived": self.archived,
        }


class Consolidator:
    """记忆巩固（"睡眠回放"）。

    做什么
    ------
    1. 把**高度相似**的重复经历聚成一簇（比如用户 5 次提到"三角函数不会"）
    2. 每簇蒸馏出一条 **gist（要点）**：标题取最具代表性的一条，
       重要度 = 簇内最高 +1（上限 5），打上 ``巩固`` 标签
    3. 源条目标记为"已合并"，检索时自动跳过 → 记忆池不再被重复项撑爆
    4. 强度低于 ``archive_below`` 且重要度 ≤ 2 的条目移入归档区（可恢复）

    不做什么
    --------
    **不直接改写 PASM 核心的存储。** 本类是纯函数式：
    :meth:`plan` 只返回"建议"，由调用方（:class:`~pasm_skills.cognition.hub.CognitionHub`）
    决定怎么落盘。因为核心档与轻量档的存储结构不同，
    在这里写死会破坏"档位透明"的设计。
    """

    def __init__(self, curve: Optional[ForgettingCurve] = None,
                 similarity: float = 0.72, min_group: int = 3,
                 archive_below: float = 0.12, max_gists: int = 5):
        self.curve = curve or ForgettingCurve()
        self.similarity = float(similarity)
        self.min_group = max(2, int(min_group))
        self.archive_below = float(archive_below)
        self.max_gists = max(1, int(max_gists))

    # ------- 聚类 -------------------------------------------------

    @staticmethod
    def _key_of(rec: Dict[str, Any], idx: int) -> str:
        return str(rec.get("_key") or (str(rec.get("title", "")) + "|"
                                       + str(rec.get("ts", idx))))

    def _group(self, episodes: Sequence[Dict[str, Any]],
               sim_fn) -> List[List[int]]:
        """贪心单遍聚类（O(n²) 但记忆池通常 < 1000 条，够用）。"""
        n = len(episodes)
        used = [False] * n
        groups: List[List[int]] = []
        for i in range(n):
            if used[i]:
                continue
            cluster = [i]
            used[i] = True
            for j in range(i + 1, n):
                if used[j]:
                    continue
                if sim_fn(i, j) >= self.similarity:
                    cluster.append(j)
                    used[j] = True
            if len(cluster) >= 1:
                groups.append(cluster)
        return groups

    # ------- 规划 -------------------------------------------------

    def plan(self, episodes: Sequence[Dict[str, Any]],
             sim_fn=None, now: Optional[float] = None) -> ConsolidationReport:
        """给出巩固建议（不落盘）。

        参数
        ----
        episodes : 记忆条目列表（dict，需含 title/brief/tags/sal/ts）
        sim_fn   : ``(i, j) -> float`` 相似度函数；不传则退化为"标题完全相同"
        """
        now = _now() if now is None else now
        rep = ConsolidationReport(scanned=len(episodes))
        if not episodes:
            return rep

        if sim_fn is None:
            cache: Dict[tuple, float] = {}

            def sim_fn(i: int, j: int) -> float:  # type: ignore[misc]
                k = (i, j)
                if k in cache:
                    return cache[k]
                a = str(episodes[i].get("title", ""))
                b = str(episodes[j].get("title", ""))
                v = 1.0 if (a and a == b) else 0.0
                cache[k] = v
                return v

        groups = self._group(episodes, sim_fn)  # type: ignore[arg-type]
        for cluster in groups:
            if len(cluster) < self.min_group:
                continue
            rep.groups += 1
            # 代表性条目 = 重要度最高，其次最新
            anchor = max(cluster, key=lambda i: (
                int(episodes[i].get("sal") or 1),
                float(episodes[i].get("ts") or 0.0),
            ))
            a = episodes[anchor]
            tags: List[str] = []
            for i in cluster:
                for t in (episodes[i].get("tags") or []):
                    s = str(t)
                    if s and s not in tags:
                        tags.append(s)
            if "巩固" not in tags:
                tags.append("巩固")
            titles: List[str] = []
            for i in cluster:
                t = str(episodes[i].get("title", "")).strip()
                if t and t not in titles:
                    titles.append(t)
            briefs = [str(episodes[i].get("brief", "")).strip()
                      for i in cluster]
            briefs = [b for b in briefs if b]
            gist = {
                "title": f"巩固：{a.get('title', ' recurring')}",
                "brief": (("、".join(titles[:5])) + "。" +
                          (briefs[-1][:120] if briefs else "")),
                "tags": tags[:12],
                "sal": min(5, int(a.get("sal") or 1) + 1),
                "category": str(a.get("cat") or a.get("category") or "巩固"),
                "sources": [self._key_of(episodes[i], i) for i in cluster],
                "count": len(cluster),
            }
            rep.gists.append(gist)
            rep.merged += len(cluster)
            if len(rep.gists) >= self.max_gists:
                break

        # 归档：强度极低且不重要
        for i, e in enumerate(episodes):
            sal = int(e.get("sal") or 1)
            if sal > 2:
                continue
            if self.curve.strength(e, now=now) <= self.archive_below:
                rep.archived.append(self._key_of(e, i))
        return rep


# ============================================================ 归档侧车

class ArchiveStore:
    """归档区（sidecar JSON）—— 巩固合并掉 / 淡出淘汰的条目放这里，**可恢复**。

    为什么是 sidecar 而不是直接改主存储：
    核心档（真 PASM 记忆层）与轻量档（episodes.json）结构不同，
    用 sidecar 记录"哪些 key 已被合并/归档"，检索时过滤，
    两个档位用同一套逻辑，且不破坏任何一方的数据。
    """

    FILE = "cognition_archive.json"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: Dict[str, Any] = {"merged": [], "archived": [], "items": {}}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
                for k in ("merged", "archived", "items"):
                    self.data.setdefault(k, [] if k != "items" else {})
            except Exception:
                self.data = {"merged": [], "archived": [], "items": {}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def mark_merged(self, keys: Iterable[str]) -> None:
        for k in keys:
            if k not in self.data["merged"]:
                self.data["merged"].append(k)

    def archive(self, keys: Iterable[str],
                items: Optional[Dict[str, Any]] = None) -> None:
        for k in keys:
            if k not in self.data["archived"]:
                self.data["archived"].append(k)
        if items:
            self.data["items"].update(items)

    def is_hidden(self, key: str) -> bool:
        return key in self.data["merged"] or key in self.data["archived"]

    def restore(self, key: str) -> bool:
        ok = False
        for bucket in ("merged", "archived"):
            if key in self.data[bucket]:
                self.data[bucket].remove(key)
                ok = True
        return ok

    def stats(self) -> Dict[str, int]:
        return {
            "merged": len(self.data["merged"]),
            "archived": len(self.data["archived"]),
            "items": len(self.data["items"]),
        }
