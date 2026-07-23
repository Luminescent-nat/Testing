"""设备画像与知识库匹配服务：根据设备硬件指纹推荐相关知识条目。"""
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, KnowledgeEntry

logger = logging.getLogger(__name__)


class DeviceKnowledgeMatcher:
    """根据设备画像匹配知识库中的设备画像、基线、规则、用例等。"""

    # 从设备画像中提取用于匹配的关键词
    @staticmethod
    def _extract_device_keywords(device: Device) -> List[str]:
        """提取设备关键词，用于与知识库条目匹配。"""
        keywords = []
        fields = [
            device.model,
            device.brand,
            device.board,
            device.hardware,
            device.cpu_abi,
            device.android_version,
            device.wifi_chip,
            device.bt_chip,
        ]
        for value in fields:
            if value:
                keywords.append(str(value).strip().lower())

        # DDR 信息
        ddr = device.ddr_info or {}
        for key in ["type", "vendor", "model"]:
            val = ddr.get(key)
            if val:
                keywords.append(str(val).strip().lower())
        ddr_capacity = ddr.get("total_mb") or ddr.get("capacity_mb")
        if ddr_capacity:
            keywords.append(f"{ddr_capacity}mb")
            keywords.append(f"{int(ddr_capacity) // 1024}gb")

        # EMMC 信息
        emmc = device.emmc_info or {}
        for key in ["model", "vendor", "type"]:
            val = emmc.get(key)
            if val:
                keywords.append(str(val).strip().lower())
        emmc_size = emmc.get("size_gb") or emmc.get("total_gb")
        if emmc_size:
            keywords.append(f"{emmc_size}gb")

        # 去重并过滤太短或无意义的词
        seen = set()
        result = []
        for kw in keywords:
            if len(kw) >= 2 and kw not in seen and kw not in {"null", "none", "unknown", ""}:
                seen.add(kw)
                result.append(kw)
        return result

    @classmethod
    async def match(
        cls,
        db: AsyncSession,
        device: Device,
        entry_types: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        为设备匹配相关知识条目。

        匹配逻辑：
        1. 先按 entry_type 过滤（默认 device_profile / baseline / rule / test_case / failure_pattern）；
        2. 再按关键词在标题/分类/内容/标签中命中任一即入选；
        3. 按命中关键词数量排序，返回前 limit 条。
        """
        if not device:
            return []

        entry_types = entry_types or ["device_profile", "baseline", "rule", "test_case", "failure_pattern"]
        keywords = cls._extract_device_keywords(device)
        if not keywords:
            return []

        stmt = select(KnowledgeEntry).where(
            KnowledgeEntry.entry_type.in_(entry_types),
            KnowledgeEntry.status != "deprecated"
        )

        # 构建关键词 OR 条件
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
        candidates = result.scalars().all()

        scored = []
        for entry in candidates:
            score, matched = cls._score_entry(entry, keywords)
            scored.append({
                "entry": entry,
                "score": score,
                "matched_keywords": matched
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
                "score": item["score"],
                "matched_keywords": item["matched_keywords"],
            }
            for item in scored[:limit]
        ]

    @classmethod
    def _score_entry(cls, entry: KnowledgeEntry, keywords: List[str]) -> tuple:
        """计算条目与设备关键词的匹配得分和命中词。"""
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
            else:
                # 2-gram 兜底，适配中文
                if len(kw) >= 2:
                    grams = [kw[i:i+2] for i in range(len(kw) - 1)]
                    gram_hits = sum(1 for g in grams if g in text)
                    if gram_hits:
                        score += gram_hits / len(grams)
                        matched.append(kw)

        return round(score, 2), matched


async def get_device_knowledge(
    db: AsyncSession,
    device: Device,
    entry_types: Optional[List[str]] = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """便捷函数：获取设备相关知识条目。"""
    return await DeviceKnowledgeMatcher.match(db, device, entry_types, limit)
