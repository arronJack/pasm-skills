"""``pasm_skills.cognition`` —— PASM 认知能力补全层。

补的是长期存在的四个缺口（对照能力矩阵）：

============  ========================================  =====================
缺口          本包给的                                   模块
============  ========================================  =====================
字面检索      语义检索 + 中文同义扩展 + 可插拔向量后端      :mod:`.semantic`
没有遗忘      艾宾浩斯遗忘曲线 + 复习效应                  :mod:`.forgetting`
没有巩固      睡眠回放（相似记忆蒸馏成要点）              :mod:`.forgetting`
没有焦点      带衰减的话题焦点栈                          :mod:`.focus`
纯被动        心跳主循环（空闲自主行为 + 后台任务）        :mod:`.tick`
动作≠工具     工具注册表（白名单 + schema 导出）          :mod:`.tools`
============  ========================================  =====================

两行接入::

    from pasm_skills.cognition import enhance
    cog = enhance(agent)          # agent 是任何 BaseAgent 子类

自检::

    python -m pasm_skills.cognition
"""
from __future__ import annotations

from . import focus, forgetting, hub, semantic, text, tick, tools
from .focus import FocusItem, FocusStack
from .forgetting import (
    ArchiveStore, ConsolidationReport, Consolidator, ForgettingCurve,
)
from .hub import CognitionHub, enhance, episode_key, episodes_of
from .semantic import (
    EmbeddingBackend, HashingBackend, HttpEmbeddingBackend, SearchHit,
    SemanticIndex, SynonymBridge, auto_backend,
)
from .text import bow, cosine, hash_embedding, normalize, tokens
from .tick import TickContext, TickHandler, TickLoop, TickResult
from .tools import ToolRegistry, ToolResult, ToolSpec

__all__ = [
    # 高层入口
    "enhance", "CognitionHub", "episodes_of", "episode_key",
    # 语义
    "SemanticIndex", "SearchHit", "SynonymBridge",
    "EmbeddingBackend", "HashingBackend", "HttpEmbeddingBackend", "auto_backend",
    # 遗忘与巩固
    "ForgettingCurve", "Consolidator", "ConsolidationReport", "ArchiveStore",
    # 焦点
    "FocusStack", "FocusItem",
    # 心跳
    "TickLoop", "TickContext", "TickHandler", "TickResult",
    # 工具
    "ToolRegistry", "ToolSpec", "ToolResult",
    # 文本
    "normalize", "tokens", "bow", "cosine", "hash_embedding",
    # 子模块
    "semantic", "forgetting", "focus", "tick", "tools", "text", "hub",
]


# ============================================================ 自检

def _selftest() -> int:  # noqa: C901 - 自检就是要平铺直叙
    """跑一遍认知层的自检。返回失败数（0 表示全过）。"""
    import os
    import shutil
    import tempfile
    from pathlib import Path

    from pasm_skills.sdk import BaseAgent

    ok = 0
    fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  v {name}")
        else:
            fail += 1
            print(f"  x {name}" + (f"  <- {detail}" if detail else ""))

    print("pasm_skills.cognition 自检")
    print("-" * 60)

    # ---------- 1. 文本层
    toks = text.tokens("我叫小明，喜欢三角函数")
    check("中文切成单字+二元特征", len(toks) > 5 and "小明" in toks)
    check("同义概念可识别", len(SynonymBridge().groups_of("我叫什么名字")) >= 1)

    # ---------- 2. 语义检索（核心：字面匹配做不到的事）
    idx = SemanticIndex()
    idx.add("a", title="姓名", text="小明", tags=["身份"])
    idx.add("b", title="薄弱知识点", text="三角函数 不会 错题", tags=["学习"])
    idx.add("c", title="住址", text="住在 杭州", tags=["身份"])
    hits = idx.search("我叫什么名字", k=3)
    keys = [h.key for h in hits]
    check("换个说法也能命中（名字→姓名）", "a" in keys[:1], f"实际：{keys}")
    hits2 = idx.search("哪块学得不好", k=3)
    check("语义命中薄弱知识点", hits2 and hits2[0].key == "b",
          f"实际：{[h.key for h in hits2]}")

    # ---------- 3. 遗忘曲线
    curve = ForgettingCurve(half_life_days=2.0)
    now = 1e12
    fresh = {"ts": now - 3600, "sal": 1}
    old = {"ts": now - 86400 * 20, "sal": 1}
    r1 = curve.retention(now - fresh["ts"], 1, 0)
    r2 = curve.retention(now - old["ts"], 1, 0)
    check("遗忘曲线：新的比旧的强", r1 > r2, f"{r1:.3f} vs {r2:.3f}")
    check("高重要度记得更久",
          curve.retention(86400 * 20, 5, 0) > curve.retention(86400 * 20, 1, 0))
    check("复习延长记忆",
          curve.retention(86400 * 20, 1, 3) > curve.retention(86400 * 20, 1, 0))
    check("保留度有下限（不会彻底消失）", curve.retention(86400 * 3650, 1, 0) > 0)

    # ---------- 4. 焦点栈
    fs = FocusStack(half_life=600.0, max_items=4)
    fs.push("三角函数", entities=["sin", "cos"])
    fs.push("三角函数", entities=["tan"])
    check("同话题加权而非重复入栈", len(fs) == 1 and fs.peek().hits == 2)
    fs.push("二次函数")
    fs.push("概率")
    fs.push("统计")
    fs.push("微积分")
    check("超容量自动压缩", len(fs) <= 5)
    check("焦点可渲染进提示词", "当前焦点" in fs.to_prompt())

    # ---------- 5. 工具注册表
    reg = ToolRegistry()
    reg.register("add", lambda a, b: a + b, description="相加", risk="safe")
    reg.register("delete_all", lambda: "boom", description="危险操作", risk="danger")
    r = reg.call("add", {"a": 2, "b": 3})
    check("工具可调用", r.ok and r.result == 5, r.error)
    r_bad = reg.call("delete_all")
    check("未授权的危险工具被拒绝", not r_bad.ok, r_bad.error)
    r_unknown = reg.call("nope")
    check("未知工具被拒绝", not r_unknown.ok)
    check("可导出 function-calling schema",
          len(reg.schemas()) == 1 and "inputSchema" in reg.schemas()[0])

    # ---------- 6. 心跳
    seen: list = []
    loop = TickLoop(interval=0.05, idle_after=0.0)
    loop.register(lambda ctx: seen.append(ctx.tick), name="probe")
    res = loop.run_once()
    check("心跳可执行处理器", len(seen) == 1 and res and res[0].ok)
    loop.register(lambda ctx: 1 / 0, name="boom")
    res2 = loop.run_once(force=True)
    check("处理器异常被隔离（循环不停）", len(res2) == 2 and any(not r.ok for r in res2))

    # ---------- 7. 巩固
    eps = [{"title": "三角函数又错了", "brief": "sin cos 搞混", "tags": ["数学"],
            "sal": 2, "ts": now - i * 600} for i in range(4)]
    eps += [{"title": "住址", "brief": "杭州", "tags": ["身份"], "sal": 3, "ts": now}]
    cidx = SemanticIndex()
    for i, e in enumerate(eps):
        cidx.add(str(i), title=e["title"], text=e["brief"], tags=e["tags"])
    cons = Consolidator(similarity=0.55, min_group=3)
    rep = cons.plan(eps, sim_fn=lambda i, j: cidx.similarity(str(i), str(j)))
    check("相似记忆被聚成一簇", rep.groups >= 1 and rep.merged >= 3,
          f"groups={rep.groups} merged={rep.merged}")
    check("巩固产出要点且重要度提升",
          bool(rep.gists) and rep.gists[0]["sal"] > 2)

    # ---------- 8. 端到端：接到真 BaseAgent
    class _Probe(BaseAgent):
        def action_pool(self):
            return ["greet", "teach"]

        def _render_reply(self, text, facts, mood):
            return "ok"

        def bootstrap_event(self):
            return []

    tmp = tempfile.mkdtemp(prefix="pasm-cognition-")
    try:
        agent = _Probe("selftest-agent", persona={"name": "探针"},
                       persist_dir=os.path.join(tmp, "agent"))
        cog = enhance(agent, persist_dir=os.path.join(tmp, "agent"))
        cog.observe("姓名", "小明", tags=["身份"], salience=4)
        cog.observe("薄弱知识点", "三角函数 总是 错", tags=["数学"], salience=3)
        got = cog.recall("我叫什么名字", k=3)
        check("端到端：换说法命中身份记忆",
              bool(got) and "小明" in (got[0].get("brief") or ""),
              f"实际：{[g.get('title') for g in got]}")
        check("端到端：命中后产生复习效应",
              sum(cog._rehearsal.values()) >= 1)

        # 巩固（真落盘）
        for i in range(3):
            cog.observe(f"练习记录{i}", "三角函数 练习 错题", tags=["数学"], salience=2)
        rep2 = cog.consolidate(apply=True)
        check("端到端：巩固产出了要点", rep2.groups >= 1,
              f"groups={rep2.groups}")
        snap = cog.snapshot()
        check("snapshot 给出向量后端名", bool(snap["semantic"]["backend"]))
        check("snapshot 给出记忆强度分布", "avg_retention" in snap["memory"])
        cog.save()
        check("sidecar 落盘", (cog.persist_dir / CognitionHub.FILE_INDEX).exists())

        # 重启恢复
        cog2 = CognitionHub(agent, persist_dir=cog.persist_dir)
        check("重启后索引可恢复", len(cog2.index) >= 1,
              f"docs={len(cog2.index)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------- 9. 零第三方依赖
    import subprocess
    import sys
    src = Path(__file__).parent
    banned = ("torch", "numpy", "jieba", "requests", "sklearn")
    code = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                     for p in src.rglob("*.py"))
    imported = [b for b in banned if f"import {b}" in code]
    check("认知层零第三方依赖（离线可用）", not imported, f"发现：{imported}")

    print("-" * 60)
    print(f"结果：{ok} 项通过，{fail} 项失败")
    return fail


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.exit(1 if _selftest() else 0)
