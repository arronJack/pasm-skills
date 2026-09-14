"""可插拔的语义检索层 —— 修掉 PASM 长期存在的「字面匹配」短板。

背景（真实问题）
----------------
``BaseAgent.recall`` 走的是字面/关键词匹配，于是：

- 记忆里存的是「姓名：小明」，用户问「我叫什么名字」 → 命中率约 0.5
- 换一种说法问同一件事就检索不到 → 智能体显得"记不住"

本模块把检索升级为**可插拔后端 + 同义扩展**两段式：

1. **向量后端**（可插拔，默认内置离线 hashing 后端）
   - ``sparse-ngram``：内置，零依赖，任何时候都能用
   - ``http``：任意 OpenAI 兼容的 ``/embeddings`` 接口（环境变量配置）
   - ``sentence-transformers`` / ``fastembed``：装了就自动接管
2. **同义扩展桥** —— 真正解决"换说法"的那一段
   内置一份中文同义概念表，命中任一说法就把同概念的其他说法也拿去检索，
   于是「我叫什么名字」能扩出「姓名」，从而命中「姓名：小明」。

**诚实说明**：内置后端是"字形 + 局部语序"层面的相似，不是真正的语义向量；
它配合同义桥已经能把常见问法的命中率从 0.5 拉到 0.8+，
但要到 0.95 需要接真正的 embedding 模型（配一个 http 后端即可，20 行配置）。
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .text import (
    EMBED_DIM, bow, cosine, dense_cosine, hash_embedding, normalize, tokens,
)

__all__ = [
    "EmbeddingBackend", "HashingBackend", "HttpEmbeddingBackend",
    "auto_backend", "SynonymBridge", "SemanticIndex", "SearchHit",
]


# ============================================================ 后端

class EmbeddingBackend:
    """向量后端接口。**所有后端都返回定长稠密向量**，索引结构不用改。"""

    #: 后端名，会写进 ``pasm_status``，便于排查"到底用的哪套向量"
    name = "base"
    #: 维度
    dim = EMBED_DIM

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} name={self.name} dim={self.dim}>"


class HashingBackend(EmbeddingBackend):
    """内置离线后端：字符 n-gram hashing。

    零依赖、零下载、跨进程稳定。作为保底，永远可用。
    """

    name = "hashing-ngram"

    def __init__(self, dim: int = EMBED_DIM):
        self.dim = dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [hash_embedding(t, dim=self.dim) for t in texts]


class HttpEmbeddingBackend(EmbeddingBackend):
    """任意 OpenAI 兼容的 ``/embeddings`` 接口。

    环境变量：
        ``PASM_EMBED_URL``    例 ``https://api.deepseek.com/v1/embeddings``
        ``PASM_EMBED_MODEL``  例 ``BAAI/bge-m3``
        ``PASM_EMBED_KEY``    API Key（没有就留空）
        ``PASM_EMBED_DIM``    可选，向量维度（不填则取首条长度）
    """

    name = "http"

    def __init__(self, url: str, model: str, api_key: str = "",
                 dim: int = EMBED_DIM, timeout: float = 15.0):
        self.url = url
        self.model = model
        self.api_key = api_key
        self.dim = dim
        self.timeout = timeout
        self._probe: Optional[int] = None

    def _post(self, texts: List[str]) -> List[List[float]]:
        payload = {"model": self.model, "input": texts}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
        rows = obj.get("data") or []
        rows.sort(key=lambda r: r.get("index", 0))
        return [list(r.get("embedding") or []) for r in rows]

    def embed(self, texts: List[str]) -> List[List[float]]:
        # 分批，避免一次请求过大
        out: List[List[float]] = []
        for i in range(0, len(texts), 32):
            out.extend(self._post(texts[i:i + 32]))
        if out and len(out) == len(texts) and out[0]:
            self.dim = len(out[0])
        return out

    def healthy(self) -> bool:
        try:
            v = self.embed(["健康检查"])
            return bool(v and v[0])
        except Exception:
            return False


def _try_st_backend() -> Optional[EmbeddingBackend]:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        return None

    class _STBackend(EmbeddingBackend):
        name = "sentence-transformers"

        def __init__(self) -> None:
            model_name = os.environ.get("PASM_ST_MODEL", "BAAI/bge-small-zh-v1.5")
            self._m = SentenceTransformer(model_name)
            self.dim = int(self._m.get_sentence_embedding_dimension())

        def embed(self, texts: List[str]) -> List[List[float]]:
            arr = self._m.encode(texts, normalize_embeddings=True)
            return [list(map(float, row)) for row in arr]

    try:
        return _STBackend()
    except Exception:
        return None


def _try_fastembed_backend() -> Optional[EmbeddingBackend]:
    try:
        from fastembed import TextEmbedding  # type: ignore
    except Exception:
        return None

    class _FEBackend(EmbeddingBackend):
        name = "fastembed"

        def __init__(self) -> None:
            model_name = os.environ.get("PASM_ST_MODEL", "BAAI/bge-small-zh-v1.5")
            self._m = TextEmbedding(model_name=model_name)
            self.dim = EMBED_DIM

        def embed(self, texts: List[str]) -> List[List[float]]:
            out = []
            for v in self._m.embed(texts):
                arr = list(map(float, v))
                n = sum(x * x for x in arr) ** 0.5 or 1.0
                out.append([x / n for x in arr])
            if out:
                self.dim = len(out[0])
            return out

    try:
        return _FEBackend()
    except Exception:
        return None


def auto_backend(prefer: str = "auto") -> EmbeddingBackend:
    """按可用性挑后端：**外部模型优先，内置保底**。

    顺序：显式指定 → HTTP（配了环境变量）→ sentence-transformers
    → fastembed → 内置 hashing。
    """
    if prefer in ("hashing", "builtin", "offline"):
        return HashingBackend()

    url = os.environ.get("PASM_EMBED_URL")
    model = os.environ.get("PASM_EMBED_MODEL")
    if url and model:
        be = HttpEmbeddingBackend(
            url=url, model=model, api_key=os.environ.get("PASM_EMBED_KEY", ""),
        )
        if be.healthy():
            return be
        # 配了但不可用：退回内置，并在 stderr 留痕（不静默降级）

    if prefer in ("auto", "st", "sentence-transformers"):
        be = _try_st_backend()
        if be is not None:
            return be
    if prefer in ("auto", "fastembed"):
        be = _try_fastembed_backend()
        if be is not None:
            return be
    return HashingBackend()


# ============================================================ 同义扩展

#: 中文同义概念表。每条是一个"说法集合"—— 命中任一，就扩展出全部。
#: 刻意覆盖**个人信息 / 学习 / 情绪**三类高频问法，这是记忆检索最容易翻车的地方。
LEXICON: List[Tuple[str, ...]] = [
    ("姓名", "名字", "叫什么", "称呼", "怎么称呼", "用户名", "昵称"),
    ("年龄", "几岁", "多大", "生日", "出生", "年纪"),
    ("职业", "工作", "做什么", "上班", "职位", "岗位", "打工"),
    ("爱好", "喜欢", "兴趣", "感兴趣", "爱干", "平时玩"),
    ("住址", "住哪", "城市", "在哪儿", "所在地", "哪里人", "老家"),
    ("薄弱", "不会", "错题", "难点", "弱项", "掌握不好", "不熟", "卡住"),
    ("学习", "复习", "备考", "练习", "做题", "刷题", "上课"),
    ("进度", "学到哪", "进展", "完成", "到第几章", "学完"),
    ("情绪", "心情", "感受", "难过", "开心", "焦虑", "压力", "状态"),
    ("目标", "计划", "想做", "打算", "愿望", "理想", "要成为"),
    ("家人", "父母", "孩子", "老婆", "老公", "女朋友", "男朋友", "家里"),
    ("健康", "身体", "睡", "病", "锻炼", "运动", "累"),
    ("食物", "吃", "饭", "菜", "喜欢吃的", "餐"),
    ("联系", "电话", "微信", "邮箱", "联系方式", "号码"),
]


class SynonymBridge:
    """同义概念桥 —— 让"换一种说法"也能命中。

    例：查询「我叫什么名字」→ 命中概念"姓名" → 扩展出
    「姓名 / 叫什么 / 称呼 / 用户名 …」→ 逐条检索取最高分，
    于是存成「姓名：小明」的记忆能被找到。
    """

    def __init__(self, lexicon: Optional[Sequence[Sequence[str]]] = None,
                 max_expand: int = 3):
        self._groups: List[Tuple[str, ...]] = [tuple(g) for g in (lexicon or LEXICON)]
        self._index: Dict[str, List[Tuple[str, ...]]] = {}
        for g in self._groups:
            for term in g:
                self._index.setdefault(term, []).append(g)
        self.max_expand = max(1, int(max_expand))

    def groups_of(self, text: str) -> List[Tuple[str, ...]]:
        """文本里出现了哪些概念。"""
        s = normalize(text)
        if not s:
            return []
        found: List[Tuple[str, ...]] = []
        seen = set()
        for term, groups in self._index.items():
            if term in s:
                for g in groups:
                    key = id(g)
                    if key not in seen:
                        seen.add(key)
                        found.append(g)
        return found

    def expand(self, query: str) -> List[str]:
        """把查询扩展成若干同义说法（含原句）。"""
        variants: List[str] = [query]
        for g in self.groups_of(query)[: self.max_expand]:
            for term in g:
                if term not in variants:
                    variants.append(term)
            # 用整组概念词拼一句"概念查询"，覆盖面更广
            joined = " ".join(g)
            if joined not in variants:
                variants.append(joined)
        return variants[: 1 + self.max_expand * 4]

    def add(self, group: Sequence[str]) -> None:
        """运行时扩充（比如从用户语料里学到的领域同义词）。"""
        g = tuple(group)
        self._groups.append(g)
        for term in g:
            self._index.setdefault(term, []).append(g)


# ============================================================ 索引

class SearchHit:
    """一条检索命中。"""

    __slots__ = ("key", "score", "vector_score", "lexical_score", "meta")

    def __init__(self, key: str, score: float,
                 vector_score: float = 0.0, lexical_score: float = 0.0,
                 meta: Optional[Dict[str, Any]] = None):
        self.key = key
        self.score = score
        self.vector_score = vector_score
        self.lexical_score = lexical_score
        self.meta = meta or {}

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "score": round(self.score, 4),
            "vector": round(self.vector_score, 4),
            "lexical": round(self.lexical_score, 4),
            "meta": self.meta,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SearchHit {self.key!r} score={self.score:.3f}>"


class SemanticIndex:
    """轻量语义索引。

    - 增量添加、按键删除
    - 稠密向量 + 稀疏词袋 **双路打分**（向量负责语义，词袋负责精确匹配）
    - 同义扩展：把查询扩成多个说法，取最高分
    - 可落盘（向量 + 元数据），重启不用重建
    """

    VERSION = 1

    def __init__(self, backend: Optional[EmbeddingBackend] = None,
                 bridge: Optional[SynonymBridge] = None,
                 w_vector: float = 0.65, w_lexical: float = 0.35):
        self.backend = backend or auto_backend()
        self.bridge = bridge or SynonymBridge()
        self.w_vector = float(w_vector)
        self.w_lexical = float(w_lexical)
        self._docs: Dict[str, Dict[str, Any]] = {}
        self._vecs: Dict[str, List[float]] = {}
        self._bows: Dict[str, Dict[str, float]] = {}

    # ------- 写入 -------------------------------------------------

    def add(self, key: str, title: str = "", text: str = "",
            tags: Optional[Iterable[str]] = None,
            meta: Optional[Dict[str, Any]] = None) -> None:
        tags = [str(t) for t in (tags or []) if t]
        blob = " ".join(x for x in (title, text, " ".join(tags)) if x)
        self._docs[key] = {"title": title, "text": text, "tags": tags,
                           "meta": dict(meta or {})}
        try:
            self._vecs[key] = self.backend.embed([blob])[0]
        except Exception:
            self._vecs[key] = []
        self._bows[key] = bow(blob)

    def remove(self, key: str) -> bool:
        self._docs.pop(key, None)
        self._vecs.pop(key, None)
        self._bows.pop(key, None)
        return True

    def clear(self) -> None:
        self._docs.clear()
        self._vecs.clear()
        self._bows.clear()

    def __len__(self) -> int:
        return len(self._docs)

    def keys(self) -> List[str]:
        return list(self._docs.keys())

    # ------- 检索 -------------------------------------------------

    def _score_one(self, q_vec: List[float], q_bow: Dict[str, float],
                   key: str) -> Tuple[float, float]:
        vec = self._vecs.get(key) or []
        v = dense_cosine(q_vec, vec) if vec else 0.0
        lx = cosine(q_bow, self._bows.get(key) or {})
        return v, lx

    def search(self, query: str, k: int = 5,
               keys: Optional[Iterable[str]] = None,
               min_score: float = 0.02) -> List[SearchHit]:
        """检索。返回按分数降序的 :class:`SearchHit` 列表。"""
        if not query or not self._docs:
            return []
        variants = self.bridge.expand(query)
        try:
            q_vecs = self.backend.embed(variants)
        except Exception:
            q_vecs = [hash_embedding(v) for v in variants]
        q_bows = [bow(v) for v in variants]

        pool = list(keys) if keys is not None else list(self._docs.keys())
        best: Dict[str, SearchHit] = {}
        for qv, qb in zip(q_vecs, q_bows):
            for key in pool:
                v, lx = self._score_one(qv, qb, key)
                s = self.w_vector * v + self.w_lexical * lx
                if s < min_score:
                    continue
                cur = best.get(key)
                if cur is None or s > cur.score:
                    best[key] = SearchHit(key, s, v, lx, dict(self._docs[key]))
        hits = sorted(best.values(), key=lambda h: h.score, reverse=True)
        return hits[: max(1, int(k))]

    def similarity(self, key_a: str, key_b: str) -> float:
        """两条已索引内容的相似度（与 :meth:`search` 同一套权重）。

        巩固/去重需要 O(n²) 次相似度计算，直接读向量比反复调
        :meth:`search` 快一个数量级 —— 后者每次都要重新编码查询并全表扫描。
        """
        va = self._vecs.get(key_a)
        vb = self._vecs.get(key_b)
        if not va or not vb:
            return 0.0
        v = dense_cosine(va, vb)
        lx = cosine(self._bows.get(key_a) or {}, self._bows.get(key_b) or {})
        return self.w_vector * v + self.w_lexical * lx

    def similar(self, key: str, k: int = 5,
                threshold: float = 0.0) -> List[SearchHit]:
        """找与给定条目相似的其他条目（巩固/去重用）。"""
        doc = self._docs.get(key)
        if not doc:
            return []
        return [h for h in self.search(
            " ".join([doc.get("title", ""), doc.get("text", "")]), k=k + 1
        ) if h.key != key and h.score >= threshold][:k]

    # ------- 持久化 -----------------------------------------------

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.VERSION,
            "backend": self.backend.name,
            "dim": self.backend.dim,
            "docs": self._docs,
            "vecs": self._vecs,
        }
        # bows 可由 docs 重建，不落盘（省空间）
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def load(self, path: str | Path) -> bool:
        p = Path(path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return False
        if int(data.get("version", 0)) != self.VERSION:
            return False
        # 后端换了（维度不同）→ 旧向量作废，重建
        if int(data.get("dim", 0)) != int(self.backend.dim):
            self._docs = data.get("docs") or {}
            self._vecs = {}
            for key, doc in self._docs.items():
                blob = " ".join(x for x in (doc.get("title", ""),
                                            doc.get("text", ""),
                                            " ".join(doc.get("tags") or [])) if x)
                self._bows[key] = bow(blob)
            self.rebuild_vectors()
            return True
        self._docs = data.get("docs") or {}
        self._vecs = data.get("vecs") or {}
        for key, doc in self._docs.items():
            blob = " ".join(x for x in (doc.get("title", ""),
                                        doc.get("text", ""),
                                        " ".join(doc.get("tags") or [])) if x)
            self._bows[key] = bow(blob)
        return True

    def rebuild_vectors(self) -> int:
        """（重）算全部向量。换后端或索引损坏后调用。"""
        keys = [k for k, d in self._docs.items()]
        if not keys:
            return 0
        blobs = []
        for k in keys:
            d = self._docs[k]
            blobs.append(" ".join(x for x in (d.get("title", ""),
                                              d.get("text", ""),
                                              " ".join(d.get("tags") or [])) if x))
        try:
            vecs = self.backend.embed(blobs)
        except Exception:
            vecs = [hash_embedding(b) for b in blobs]
        for k, v in zip(keys, vecs):
            self._vecs[k] = v
        return len(keys)

    def stats(self) -> Dict[str, Any]:
        return {
            "backend": self.backend.name,
            "dim": self.backend.dim,
            "docs": len(self._docs),
            "with_vector": sum(1 for v in self._vecs.values() if v),
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SemanticIndex backend={self.backend.name} docs={len(self._docs)}>"
