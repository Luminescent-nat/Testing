"""知识库语义搜索服务。"""
import logging
from typing import List, Optional, Dict, Any

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeEntry
from app.services.knowledge_embedder import get_embedder, cosine_similarity

logger = logging.getLogger(__name__)


class KnowledgeSearchService:
    """结合关键词过滤与向量相似度的混合搜索。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedder = get_embedder()

    async def search(
        self,
        query: str,
        entry_type: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        top_k: int = 10,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        混合搜索知识库条目。

        策略：
        1. 先用关键词/分类/状态/标签过滤候选集；
        2. 对候选集计算与查询向量的余弦相似度；
        3. 综合关键词匹配分与语义相似度排序。
        """
        if not query or not query.strip():
            return []

        # 1. 构建候选查询（先按元数据过滤，避免全表扫描）
        stmt = select(KnowledgeEntry)
        if entry_type:
            stmt = stmt.where(KnowledgeEntry.entry_type == entry_type)
        if category:
            stmt = stmt.where(KnowledgeEntry.category == category)
        if status:
            stmt = stmt.where(KnowledgeEntry.status == status)
        if tag:
            stmt = stmt.where(KnowledgeEntry.tags.contains([tag]))

        result = await self.db.execute(stmt)
        candidates = result.scalars().all()

        if not candidates:
            return []

        # 2. 生成查询向量
        query_vec = await self.embedder.embed(query)

        # 3. 计算相似度并排序
        scored = []
        for entry in candidates:
            keyword_score = self._keyword_score(entry, query)
            semantic_score = 0.0
            if query_vec and entry.embedding:
                semantic_score = max(0.0, cosine_similarity(query_vec, entry.embedding))

            final_score = keyword_weight * keyword_score + semantic_weight * semantic_score
            scored.append({
                "entry": entry,
                "keyword_score": keyword_score,
                "semantic_score": semantic_score,
                "score": final_score
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        return [
            {
                "id": item["entry"].id,
                "title": item["entry"].title,
                "entry_type": item["entry"].entry_type,
                "category": item["entry"].category,
                "tags": item["entry"].tags or [],
                "status": item["entry"].status,
                "content": item["entry"].content,
                "score": round(item["score"], 4),
                "keyword_score": round(item["keyword_score"], 4),
                "semantic_score": round(item["semantic_score"], 4),
            }
            for item in scored[:top_k]
        ]

    async def semantic_search(
        self,
        query: str,
        entry_type: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """纯语义搜索（不强制关键词匹配），用于推荐/兜底。"""
        if not query or not query.strip():
            return []

        query_vec = await self.embedder.embed(query)
        if not query_vec:
            return []

        stmt = select(KnowledgeEntry).where(KnowledgeEntry.embedding.isnot(None))
        if entry_type:
            stmt = stmt.where(KnowledgeEntry.entry_type == entry_type)
        if category:
            stmt = stmt.where(KnowledgeEntry.category == category)
        if status:
            stmt = stmt.where(KnowledgeEntry.status == status)
        if tag:
            stmt = stmt.where(KnowledgeEntry.tags.contains([tag]))

        result = await self.db.execute(stmt)
        candidates = result.scalars().all()

        scored = []
        for entry in candidates:
            score = cosine_similarity(query_vec, entry.embedding)
            if score <= 0:
                continue
            scored.append({
                "id": entry.id,
                "title": entry.title,
                "entry_type": entry.entry_type,
                "category": entry.category,
                "tags": entry.tags or [],
                "status": entry.status,
                "content": entry.content,
                "score": round(score, 4),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _keyword_score(entry: KnowledgeEntry, keyword: str) -> float:
        """简单关键词匹配得分：标题 > 标签 > 分类 > 内容。支持中英文短串匹配。"""
        keyword_lower = keyword.lower().strip()
        score = 0.0

        # 完整关键词匹配
        if keyword_lower in (entry.title or "").lower():
            score += 1.0
        if entry.tags and keyword in entry.tags:
            score += 0.8
        if keyword_lower in (entry.category or "").lower():
            score += 0.6
        if keyword_lower in (entry.content or "").lower():
            score += 0.3

        if score > 0:
            return min(score, 1.0)

        # 中文/无空格场景：按 2-gram 子串匹配
        tokens = [keyword_lower[i:i+2] for i in range(len(keyword_lower) - 1)]
        if not tokens:
            return 0.0

        title_lower = (entry.title or "").lower()
        content_lower = (entry.content or "").lower()
        category_lower = (entry.category or "").lower()
        entry_tags = set(t.lower() for t in (entry.tags or []))

        matched = 0
        for token in tokens:
            if token in title_lower:
                matched += 1
            elif token in entry_tags:
                matched += 1
            elif token in category_lower:
                matched += 0.6
            elif token in content_lower:
                matched += 0.3

        if matched:
            score = min(matched / max(len(tokens) * 0.5, 1.0), 1.0) * 0.8
        return min(score, 1.0)
