"""为 AI 判定构建知识库上下文：匹配相关规则、基线、黄金案例、失败模式。"""
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeEntry, TestItem, Device

logger = logging.getLogger(__name__)


class JudgeKnowledgeContext:
    """为单个测试项的 AI 判定准备相关知识上下文。"""

    @classmethod
    async def build(
        cls,
        db: AsyncSession,
        device: Device,
        item: TestItem,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        构建判定上下文。

        返回结构:
        {
            "rules": [...],        # 判定规则类知识条目
            "baselines": [...],    # 基线指标类知识条目
            "patterns": [...],     # 失败模式类知识条目
            "cases": [...],        # 测试用例类知识条目
            "device_profiles": [...]  # 设备画像类知识条目
        }
        """
        # 1. 构造查询关键词
        keywords = cls._extract_keywords(device, item)

        # 2. 按类型查询相关知识条目
        rules = await cls._query_by_type(db, ["rule"], keywords, limit)
        baselines = await cls._query_by_type(db, ["baseline"], keywords, limit)
        patterns = await cls._query_by_type(db, ["failure_pattern"], keywords, limit)
        cases = await cls._query_by_type(db, ["test_case"], keywords, limit)
        profiles = await cls._query_by_type(db, ["device_profile"], keywords, limit)

        return {
            "rules": rules,
            "baselines": baselines,
            "patterns": patterns,
            "cases": cases,
            "device_profiles": profiles,
        }

    @classmethod
    def _extract_keywords(cls, device: Device, item: TestItem) -> List[str]:
        """从设备和测试项中提取关键词。"""
        keywords = set()
        for value in [
            item.name,
            item.tags and ",".join(item.tags),
            device.model,
            device.brand,
            device.board,
            device.hardware,
            device.cpu_abi,
            device.wifi_chip,
            device.bt_chip,
        ]:
            if value:
                keywords.add(str(value).strip().lower())

        ddr = device.ddr_info or {}
        emmc = device.emmc_info or {}
        for info in [ddr, emmc]:
            for key in ["type", "vendor", "model"]:
                val = info.get(key)
                if val:
                    keywords.add(str(val).strip().lower())

        return [k for k in keywords if len(k) >= 2 and k not in {"null", "none", "unknown"}]

    @classmethod
    async def _query_by_type(
        cls,
        db: AsyncSession,
        entry_types: List[str],
        keywords: List[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """按类型和关键词查询知识条目。"""
        stmt = select(KnowledgeEntry).where(
            KnowledgeEntry.entry_type.in_(entry_types),
            KnowledgeEntry.status != "deprecated"
        )

        filters = []
        for kw in keywords:
            like = f"%{kw}%"
            filters.append(KnowledgeEntry.title.ilike(like))
            filters.append(KnowledgeEntry.content.ilike(like))
            filters.append(KnowledgeEntry.category.ilike(like))
            filters.append(KnowledgeEntry.tags.contains([kw]))

        if filters:
            stmt = stmt.where(or_(*filters))

        result = await db.execute(stmt)
        entries = result.scalars().all()

        scored = []
        for entry in entries:
            score, _ = cls._score_entry(entry, keywords)
            scored.append({"entry": entry, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)

        return [
            {
                "id": item["entry"].id,
                "title": item["entry"].title,
                "entry_type": item["entry"].entry_type,
                "category": item["entry"].category,
                "tags": item["entry"].tags or [],
                "content": item["entry"].content,
                "score": item["score"],
            }
            for item in scored[:limit]
        ]

    @classmethod
    def _score_entry(cls, entry: KnowledgeEntry, keywords: List[str]) -> tuple:
        """计算条目与关键词的匹配得分。"""
        text = " ".join([
            (entry.title or "").lower(),
            (entry.category or "").lower(),
            (entry.content or "").lower(),
            " ".join(t.lower() for t in (entry.tags or []))
        ])

        score = 0
        matched = []
        for kw in keywords:
            if kw in text:
                score += 1
                matched.append(kw)
            elif len(kw) >= 2:
                grams = [kw[i:i+2] for i in range(len(kw) - 1)]
                gram_hits = sum(1 for g in grams if g in text)
                if gram_hits:
                    score += gram_hits / len(grams)
                    matched.append(kw)
        return round(score, 2), matched


def format_context_for_llm(context: Dict[str, Any]) -> str:
    """将判定上下文格式化为 LLM 可读的文本。"""
    lines = []

    sections = [
        ("相关判定规则", context.get("rules", [])),
        ("相关基线指标", context.get("baselines", [])),
        ("相关失败模式", context.get("patterns", [])),
        ("相关测试用例", context.get("cases", [])),
        ("相关设备画像", context.get("device_profiles", [])),
    ]

    for title, items in sections:
        if not items:
            continue
        lines.append(f"\n## {title}")
        for item in items:
            content = (item.get("content") or "").strip()
            if content:
                # 限制长度，避免 prompt 过长
                content = content[:400]
            lines.append(f"- {item.get('title', '')}：{content}")

    return "\n".join(lines)
