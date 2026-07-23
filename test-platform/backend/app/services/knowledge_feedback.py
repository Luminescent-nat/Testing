"""测试执行对知识库的反哺：更新命中/通过/失败次数，沉淀实践经验。"""
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeEntry, TestRecord, TestItem

logger = logging.getLogger(__name__)


class KnowledgeFeedbackService:
    """根据测试记录更新知识库条目的实践统计。"""

    FEEDBACK_ENTRY_TYPES = {"test_case", "rule", "baseline", "failure_pattern", "skill"}

    @classmethod
    async def update_from_record(
        cls,
        db: AsyncSession,
        record: TestRecord,
        item: Optional[TestItem] = None
    ):
        """根据单条测试记录更新关联知识条目的统计。"""
        if not item:
            result = await db.execute(select(TestItem).where(TestItem.id == record.item_id))
            item = result.scalar_one_or_none()

        if not item:
            return

        # 命中：根据测试项标签/技能/名称匹配相关知识条目
        matched = await cls._find_matching_entries(db, item)
        if not matched:
            return

        for entry in matched:
            entry.hit_count = (entry.hit_count or 0) + 1
            if record.status == "pass":
                entry.pass_count = (entry.pass_count or 0) + 1
            elif record.status in ("fail", "error"):
                entry.fail_count = (entry.fail_count or 0) + 1

            # 在 meta 中记录最近关联的测试记录
            feedback_history = (entry.meta or {}).get("feedback_history", [])
            feedback_history.append({
                "record_id": record.id,
                "item_id": record.item_id,
                "item_name": item.name,
                "status": record.status,
            })
            entry.meta = {
                **(entry.meta or {}),
                "feedback_history": feedback_history[-20:]  # 仅保留最近 20 条
            }

        await db.commit()

    @classmethod
    async def _find_matching_entries(
        cls,
        db: AsyncSession,
        item: TestItem
    ) -> List[KnowledgeEntry]:
        """查找与测试项相关的知识条目。"""
        stmt = select(KnowledgeEntry).where(
            KnowledgeEntry.entry_type.in_(cls.FEEDBACK_ENTRY_TYPES),
            KnowledgeEntry.status != "deprecated"
        )
        result = await db.execute(stmt)
        candidates = result.scalars().all()

        item_tags = set(item.tags or [])
        item_skills = set(item.skills or [])
        item_name_lower = (item.name or "").lower()

        matched = []
        for entry in candidates:
            entry_tags = set(entry.tags or [])
            # 标签或技能交集
            if item_tags & entry_tags or item_skills & entry_tags:
                matched.append(entry)
                continue

            # 标题或内容包含测试项名称关键词
            if item_name_lower and len(item_name_lower) >= 3:
                if item_name_lower in (entry.title or "").lower():
                    matched.append(entry)
                    continue
                if item_name_lower in (entry.content or "").lower():
                    matched.append(entry)
                    continue

            # meta 中显式关联的测试项 ID
            related_ids = (entry.meta or {}).get("related_item_ids", []) or (entry.meta or {}).get("suggested_item_ids", [])
            if item.id in related_ids:
                matched.append(entry)

        return matched
