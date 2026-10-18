"""领域知识库与检索（RAG 的 Retrieval 层）。

设计要点
--------
1. **零外部依赖**：BM25 + jieba 分词，全部本地完成。不需要向量模型、
   不需要下载权重、不依赖 HuggingFace（实测本机不可达）。启动毫秒级。
2. **别名硬匹配优先**：BM25 对「稻纵卷叶螟」这类专有名词一旦切词不准就召回失败，
   而检测结果的虫种名是确定的。所以先用虫种名/别名做精确命中置顶，
   再用 BM25 补语义相关的条目。两者结合才不会漏。
3. **每条都带 source**：生成端要求标注引用编号，用户可点开核对原文——
   这是「可溯源」能成立的前提。没有 source 的条目不允许入库。
4. **失败即降级**：知识库缺失或检索报错一律返回空列表，
   调用方（LLM）退回纯参数化回答，绝不能因为 RAG 挂了导致检测失败。
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# backend/data/knowledge/
_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"


def _tokenize(text: str) -> list[str]:
    """中文分词。jieba 首次加载会往 stderr 打一堆日志，这里压掉。"""
    import jieba

    jieba.setLogLevel(60)
    # 去掉标点与空白：BM25 里这些是纯噪声，还会拉长倒排表
    cleaned = re.sub(r"[\s，。、；：（）()【】\[\]“”\"'·/\\|]+", " ", text)
    return [t for t in jieba.cut(cleaned) if len(t.strip()) > 1]


class KnowledgeBase:
    """启动时一次性加载 JSON 知识库并建 BM25 索引，常驻内存。"""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self._bm25: Any = None
        self._alias_index: dict[str, int] = {}  # 别名/正名 -> docs 下标
        self._loaded = False
        self._error: str | None = None

    # ---------- 加载 ----------

    def load(self) -> None:
        if self._loaded:
            return
        try:
            self._load_inner()
        except Exception as exc:  # noqa: BLE001 - 知识库是可选增强
            self._error = str(exc)
            logger.warning("Knowledge base unavailable: %s", exc)
        finally:
            self._loaded = True

    def _load_inner(self) -> None:
        if not _KNOWLEDGE_DIR.is_dir():
            raise FileNotFoundError(f"knowledge dir missing: {_KNOWLEDGE_DIR}")

        docs: list[dict[str, Any]] = []
        for path in sorted(_KNOWLEDGE_DIR.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = raw if isinstance(raw, list) else raw.get("entries", [])
            for entry in entries:
                doc = self._normalize(entry, path.stem)
                if doc:
                    docs.append(doc)

        if not docs:
            raise ValueError("knowledge base is empty")

        from rank_bm25 import BM25Okapi

        self.docs = docs
        self._bm25 = BM25Okapi([d["tokens"] for d in docs])
        for idx, doc in enumerate(docs):
            for key in [doc["title"], *doc.get("aliases", [])]:
                key = str(key).strip().lower()
                if key:
                    self._alias_index.setdefault(key, idx)
        logger.info("Knowledge base loaded: %d entries from %s", len(docs), _KNOWLEDGE_DIR.name)

    @staticmethod
    def _normalize(entry: dict[str, Any], category: str) -> dict[str, Any] | None:
        """校验并把一条原始条目转成可检索文档。缺 source 的条目直接丢弃。"""
        title = str(entry.get("name") or entry.get("title") or "").strip()
        body = str(entry.get("content") or "").strip()
        source = str(entry.get("source") or "").strip()
        if not title or not body:
            return None
        if not source:
            logger.warning("Knowledge entry '%s' has no source, skipped", title)
            return None
        aliases = [str(a).strip() for a in (entry.get("aliases") or []) if str(a).strip()]
        tags = [str(t).strip() for t in (entry.get("tags") or []) if str(t).strip()]
        text = " ".join([title, *aliases, *tags, body])
        return {
            "id": str(entry.get("id") or f"{category}-{len(title)}-{title}"),
            "category": category,
            "title": title,
            "aliases": aliases,
            "tags": tags,
            "body": body,
            "source": source,
            "text": text,
            "tokens": _tokenize(text),
        }

    # ---------- 检索 ----------

    @property
    def available(self) -> bool:
        return self._loaded and self._bm25 is not None and bool(self.docs)

    @property
    def error(self) -> str | None:
        return self._error

    def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        """混合检索：别名精确命中 + BM25 语义召回。

        返回的每条都带 `id / title / body / source`，供生成端编号引用。
        任何异常都吞掉并返回已召回的部分（或空列表）。
        """
        if not query or not query.strip():
            return []
        self.load()
        if not self.available:
            return []

        try:
            return self._search_inner(query, top_k)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Knowledge search failed: %s", exc)
            return []

    def _search_inner(self, query: str, top_k: int) -> list[dict[str, Any]]:
        picked: list[int] = []
        seen: set[int] = set()

        # ① 别名/正名硬匹配：查询里出现虫种名就直取该条目，保证主对象一定召回到
        q_lower = query.lower()
        for key, idx in self._alias_index.items():
            if len(key) >= 2 and key in q_lower and idx not in seen:
                picked.append(idx)
                seen.add(idx)

        # ② BM25 补齐语义相关条目
        scores = self._bm25.get_scores(_tokenize(query))
        best = max(scores) if len(scores) else 0.0
        if best <= 0:
            # 一个词都没命中，只保留别名硬匹配的结果，不做无意义补位
            logger.debug("no BM25 term hit for query: %s", query[:40])
        else:
            # 相关性下限：查询里带了「防治方法」这类通用意图词，会把大量无关条目
            # 拉进前排（实测检索蚜虫时把蝗虫也召回来了）。只保留得分达到最强
            # 命中 25% 的条目，宁可少给几条，也不要给模型塞噪声。
            floor = best * 0.25
            ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
            for idx in ranked:
                if len(picked) >= top_k:
                    break
                if idx in seen or scores[idx] < floor:
                    continue
                picked.append(idx)
                seen.add(idx)

        out: list[dict[str, Any]] = []
        for i, idx in enumerate(picked[:top_k], start=1):
            doc = self.docs[idx]
            out.append(
                {
                    "ref": i,
                    "id": doc["id"],
                    "title": doc["title"],
                    "body": doc["body"],
                    "source": doc["source"],
                }
            )
        return out


@lru_cache
def get_knowledge_base() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.load()
    return kb
