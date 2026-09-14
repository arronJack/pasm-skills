"""中文友好的轻量文本处理 —— 认知层的共同地基。

设计约束：**零第三方依赖、离线可用、纯标准库**。
这样 ``pip install pasm-skills`` 之后语义能力立即可用，
不需要先下载几百 MB 的 embedding 模型。

为什么不用 jieba？
    分词器会引入额外依赖与词典体积，而记忆检索场景里
    「字符 n-gram」在中文上的表现足够好，且对新词/专有名词
    （人名、产品名、术语）天然鲁棒 —— 分词器反而会切错。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Dict, Iterable, List, Sequence

__all__ = [
    "normalize", "tokens", "bow", "cosine", "hash_embedding",
    "EMBED_DIM", "is_cjk",
]

#: 中日韩统一表意文字 + 扩展 A
_CJK_RANGE = "\u4e00-\u9fff\u3400-\u4dbf"
_RE_CJK = re.compile("[" + _CJK_RANGE + "]+")
_RE_LATIN = re.compile(r"[A-Za-z]+")
_RE_NUM = re.compile(r"[0-9]+")
_RE_NOISE = re.compile(r"[^\w" + _CJK_RANGE + "]+", re.UNICODE)

#: 单字停用词。只作用于**单字特征** —— 二元特征保留（"的"在"我的"里有区分度）。
_STOP_1GRAM = set(
    "的了是在我有你他她它们这那就和与及或也很都非常还吧呢啊吗嘛哦呀哇嗯个上下中大小多少好坏不没"
)

#: 默认向量维度。足够放下常用特征，又只有 384 * 8B ≈ 3KB/条。
EMBED_DIM = 384


def is_cjk(ch: str) -> bool:
    """单字符是否为中日韩表意文字。"""
    return bool(ch) and ("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf")


def normalize(text: str) -> str:
    """全角转半角、小写、标点归一为空格。"""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).lower()
    return _RE_NOISE.sub(" ", s).strip()


def tokens(text: str) -> List[str]:
    """切出特征：CJK 单字 + 相邻二元 + 英文词 + 数字。

    二元特征是关键 —— 它保留了局部语序信息，
    能把"三角函数"和"函数三角"区分开，而纯词袋做不到。
    """
    if not text:
        return []
    s = normalize(text)
    out: List[str] = []
    for m in _RE_CJK.finditer(s):
        run = m.group()
        out.extend(ch for ch in run if ch not in _STOP_1GRAM)
        if len(run) >= 2:
            out.extend(run[i:i + 2] for i in range(len(run) - 1))
    out.extend(m.group().lower() for m in _RE_LATIN.finditer(s))
    out.extend(m.group() for m in _RE_NUM.finditer(s))
    return [t for t in out if t]


def bow(text: str, bigram_weight: float = 1.6) -> Dict[str, float]:
    """词袋（带次线性 TF 缩放，避免长文本刷分）。"""
    d: Dict[str, float] = {}
    for t in tokens(text):
        w = bigram_weight if len(t) == 2 and is_cjk(t[0]) else 1.0
        d[t] = d.get(t, 0.0) + w
    return {k: 1.0 + (v ** 0.5) for k, v in d.items()}


def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    """稀疏向量余弦相似度。"""
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = 0.0
    for k, v in a.items():
        w = b.get(k)
        if w:
            dot += v * w
    if dot == 0.0:
        return 0.0
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _hfeature(tok: str) -> int:
    """稳定哈希（跨进程、跨机器一致）—— 保证落盘的向量能复用。"""
    return int.from_bytes(hashlib.blake2b(tok.encode("utf-8"), digest_size=4).digest(), "big")


def hash_embedding(text: str, dim: int = EMBED_DIM,
                   bigram_weight: float = 1.6) -> List[float]:
    """把文本压成定长稠密向量（hashing trick）。

    与 :func:`bow` 的信息量等价，但**定长**——
    这样才能和真正的 embedding 后端（HTTP / sentence-transformers）
    共用同一套存储与余弦计算，切换后端不用改索引结构。
    """
    vec = [0.0] * dim
    for tok, w in bow(text, bigram_weight=bigram_weight).items():
        i = _hfeature(tok) % dim
        vec[i] += w
    norm = sum(v * v for v in vec) ** 0.5
    if norm:
        vec = [v / norm for v in vec]
    return vec


def dense_cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """稠密向量余弦。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    return dot / (na ** 0.5 * nb ** 0.5) if na and nb else 0.0


def join_text(parts: Iterable[str]) -> str:
    """把多个字段拼成待检索文本。"""
    return " ".join(str(p) for p in parts if p)
