"""相关性闸门 —— 「凭什么说这条资料能支撑这个回答」的**可判定**实现。

为什么需要它
------------
语义检索对**任何**问题都会返回若干条结果（只是分数高低不同）。如果直接把这些
结果当作"依据"，就会出现：

    问「髋关节置换术后康复方案」
    → 命中「过敏史·磺胺」（score 0.47）与「初次相遇」→ 系统据此作答

于是在业务上表现为 **「无依据必须拒答」这条保障形同虚设** ——
医疗场景里这就是事故的前身。

★ 为什么不能用分数阈值
--------------------
PASM 的记忆打分带**时间衰减**（`0.6 + 0.4×recency`）。用绝对阈值当"查不到"的判据，
结果就是：**资料库越老，系统越"失忆"**；而且真命中与假命中的分数区间会重叠
（实测真命中最低 6.00 / 假命中最高 2.29，太近，调不出一个稳的阈值）。

所以闸门用的是**与分数无关的结构判据**：命中的词必须落在资料的
**标题或标签**上。标题和标签是人写的、有语义意图的字段；
正文里的偶然词重合不算依据。

本模块是**共享实现** —— `pasm-customer-service` 与 `pasm-medical` 都用它，
不再各自维护一份（同源多份代码的行为漂移，这个生态已经吃过一次亏）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

__all__ = ["tokens", "surface_of", "touches", "select_evidence", "overlap"]

#: 中日韩统一表意文字
_CJK = re.compile(r"[\u4e00-\u9fff]+")
#: 拉丁字母 / 数字串
_WORD = re.compile(r"[A-Za-z0-9]+")

_ASCII_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "is", "are", "was", "in", "on",
    "for", "with", "how", "what", "why", "when", "who", "do", "does", "i", "you",
}

#: 中文里几乎无处不在、因而不携带区分度的字 / 二元词。
#: 不去掉它们，"的""了""是"会让任何两条文本都"命中"。
_CJK_STOP_CHARS = set("的了是我你他她它们在有和与就都也很不之其这那么呢吗啊呀哦嗯")


def _cjk_units(run: str) -> Set[str]:
    """中文片段切成**二元词**（+ 单字，仅当片段很短时）。

    为什么以二元词为主：单字重合太容易（"血压"与"血管"共享"血"），
    三元以上又太严（"高血压"与"血压高"命不中）。二元是中文检索的经验折中。
    """
    out: Set[str] = set()
    n = len(run)
    if n == 1:
        if run not in _CJK_STOP_CHARS:
            out.add(run)
        return out
    for i in range(n - 1):
        bg = run[i:i + 2]
        if bg[0] in _CJK_STOP_CHARS and bg[1] in _CJK_STOP_CHARS:
            continue
        out.add(bg)
    # 短片段补单字（"血压" → 血压、血、压），提高短查询的召回
    if n <= 4:
        out.update(c for c in run if c not in _CJK_STOP_CHARS)
    return out


def tokens(text: str) -> Set[str]:
    """把一段文本切成可比对的词元集合（中文二元词 + 英文小写词 + 数字）。"""
    s = text or ""
    out: Set[str] = set()
    for run in _CJK.findall(s):
        out |= _cjk_units(run)
    for w in _WORD.findall(s):
        w = w.lower()
        if w not in _ASCII_STOP and len(w) > 1:
            out.add(w)
    return out


def surface_of(fact: Dict[str, Any]) -> str:
    """资料的**命中面** = 标题 + 标签。

    ★ 刻意**不含正文**：正文里的偶然词重合（"邮箱"出现在发票说明里）正是
    造成"答非所问"的原因。要让它算依据，就把它写进标题或标签 ——
    那意味着有人**有意**给它打了这个语义标签。
    """
    if not isinstance(fact, dict):
        return ""
    title = str(fact.get("title") or "")
    tags = fact.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    try:
        tag_s = " ".join(str(t) for t in tags)
    except TypeError:
        tag_s = ""
    return (title + " " + tag_s).strip()


def overlap(question_tokens: Iterable[str], fact: Dict[str, Any]) -> Set[str]:
    """问题词元与资料命中面的交集。"""
    return set(question_tokens) & tokens(surface_of(fact))


def touches(question_tokens: Iterable[str], fact: Dict[str, Any],
            *, min_overlap: int = 1) -> bool:
    """这条资料是否**够格**作为该问题的依据。"""
    return len(overlap(question_tokens, fact)) >= max(1, min_overlap)


def select_evidence(question: str, hits: Sequence[Dict[str, Any]], *,
                    min_overlap: int = 1,
                    limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """从检索结果里筛出**真正能当依据**的那些。

    返回空列表是**有意义的结论**：本资料库里没有能支撑这个回答的内容 →
    调用方应当拒答，而不是把弱命中包装成依据。
    """
    qt = tokens(question)
    if not qt:
        return []
    out = [h for h in (hits or []) if touches(qt, h, min_overlap=min_overlap)]
    return out[:limit] if limit else out


# ============================================================ 自检

def selftest() -> bool:
    ok = fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  v %s" % name)
        else:
            fail += 1
            print("  x %s%s" % (name, ("  <- " + detail) if detail else ""))

    print("pasm_skills.cognition.relevance 自检")
    print("-" * 60)

    check("中文切出二元词", "血压" in tokens("高血压 3 级"))
    check("英文转小写且过滤停用词",
          "aspirin" in tokens("Take Aspirin now") and "the" not in tokens("the a of"))
    check("数字保留", "152" in tokens("血压 152/94 mmHg"))
    check("纯停用词中文不产生噪声词元",
          tokens("的了是") == set(), str(tokens("的了是")))

    hit = {"title": "过敏史·青霉素", "brief": "皮疹", "tags": ["青霉素", "过敏", "禁忌"]}
    check("命中面 = 标题 + 标签", "青霉素" in surface_of(hit))
    check("★ 命中面不含正文（正文偶合不算依据）",
          "皮疹" not in surface_of(hit))

    # ★ 真命中
    check("★ 真命中：问过敏能支撑「过敏史·青霉素」",
          touches(tokens("患者对什么过敏"), hit))
    check("★ 真命中：问青霉素能支撑",
          touches(tokens("青霉素"), hit))

    # ★ 假命中必须被挡住 —— 这就是当初失效的那条
    check("★ 假命中：问髋关节置换**不**支撑过敏史",
          not touches(tokens("髋关节置换术后康复方案"), hit))
    check("★ 假命中：问手术排期**不**支撑过敏史",
          not touches(tokens("手术排期怎么安排"), hit))

    # 选择器
    hits = [hit, {"title": "初次相遇", "brief": "第一次接入", "tags": ["初次", "相遇"]},
            {"title": "观测·血压", "brief": "152/94", "tags": ["血压"]}]
    got = select_evidence("髋关节置换术后康复方案", hits)
    check("★ select_evidence 对无关问题返回空（→ 触发拒答）", got == [], str(got))
    got2 = select_evidence("血压多少", hits)
    check("select_evidence 对相关问题返回命中",
          len(got2) == 1 and "血压" in got2[0]["title"], str(got2))
    check("select_evidence 尊重 limit", len(select_evidence("过敏 血压", hits, limit=1)) == 1)

    # 反例：空问题不能"命中一切"
    check("★ 空/纯停用词问题不返回任何依据",
          select_evidence("的了吗", hits) == [], str(select_evidence("的了吗", hits)))

    print("-" * 60)
    print("结果：%d 项通过，%d 项失败" % (ok, fail))
    return fail == 0


if __name__ == "__main__":                                  # pragma: no cover
    import sys
    sys.exit(0 if selftest() else 1)
