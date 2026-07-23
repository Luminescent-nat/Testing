import re
import logging
import statistics
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TestRecord, FailurePattern, Baseline, GoldenCase

logger = logging.getLogger(__name__)


class FailurePatternService:
    """失败模式服务：自动归类测试失败原因。"""

    DEFAULT_PATTERNS = [
        {
            "name": "ADB 设备未找到",
            "category": "adb",
            "pattern": r"device\s+['\"]?[^'\"\n]*['\"]?\s+not found|no devices/emulators found",
            "description": "ADB 无法找到目标设备，可能设备未连接或 USB 调试未开启。",
            "suggested_fix": "检查 USB 连接、adb 权限，或重新插拔设备。"
        },
        {
            "name": "ADB 设备离线",
            "category": "adb",
            "pattern": r"error:\s*device\s*offline",
            "description": "设备处于 offline 状态。",
            "suggested_fix": "执行 adb kill-server && adb start-server，或重新授权 USB 调试。"
        },
        {
            "name": "命令超时",
            "category": "timeout",
            "pattern": r"timeout after \d+ seconds|timed out",
            "description": "命令执行超过设定超时时间。",
            "suggested_fix": "增大测试项 timeout，或检查设备是否卡死。"
        },
        {
            "name": "权限不足",
            "category": "permission",
            "pattern": r"permission denied|operation not permitted",
            "description": "设备端命令权限不足。",
            "suggested_fix": "确认是否已 root，或调整命令执行路径/权限。"
        },
        {
            "name": "二进制缺失",
            "category": "compat",
            "pattern": r"no such file or directory",
            "description": "目标可执行文件或脚本在设备上不存在。",
            "suggested_fix": "检查 push 是否成功，或工具架构与设备是否匹配。"
        },
        {
            "name": "兼容性不满足",
            "category": "compat",
            "pattern": r"架构不兼容|设备缺少必要能力|主板平台不兼容|硬件名称不兼容|Android版本",
            "description": "设备不满足测试项的兼容性要求。",
            "suggested_fix": "检查设备画像与测试项兼容性配置。"
        }
    ]

    @classmethod
    async def seed_default_patterns(cls, db: AsyncSession, user_id: Optional[int] = None):
        """初始化默认失败模式。"""
        for pattern_data in cls.DEFAULT_PATTERNS:
            result = await db.execute(
                select(FailurePattern).where(FailurePattern.name == pattern_data["name"])
            )
            if result.scalar_one_or_none():
                continue

            pattern = FailurePattern(
                name=pattern_data["name"],
                category=pattern_data["category"],
                pattern=pattern_data["pattern"],
                description=pattern_data["description"],
                suggested_fix=pattern_data["suggested_fix"],
                created_by=user_id
            )
            db.add(pattern)
            logger.info("创建失败模式: %s", pattern.name)
        await db.commit()

    @classmethod
    async def match_record(cls, db: AsyncSession, record: TestRecord) -> List[Dict[str, Any]]:
        """为测试记录匹配失败模式。"""
        if record.status not in ("fail", "error"):
            return []

        result = await db.execute(select(FailurePattern))
        patterns = result.scalars().all()

        text = f"{record.output or ''}\n{record.fail_reason or ''}"
        matches = []

        for pattern in patterns:
            if re.search(pattern.pattern, text, re.IGNORECASE):
                pattern.occurrence_count += 1
                pattern.updated_at = datetime.now(timezone.utc)
                matches.append({
                    "pattern_id": pattern.id,
                    "name": pattern.name,
                    "category": pattern.category,
                    "description": pattern.description,
                    "suggested_fix": pattern.suggested_fix
                })

        if matches:
            await db.commit()

        return matches


class BaselineService:
    """统计基线服务：聚合同一型号设备在同一测试项上的指标。"""

    @classmethod
    async def update_from_record(
        cls,
        db: AsyncSession,
        record: TestRecord,
        device_model: str
    ):
        """根据测试记录更新基线。"""
        if record.status != "pass" or not record.extracted_data:
            return

        metrics = record.extracted_data
        if isinstance(metrics, dict) and "judgement" in metrics:
            metrics = metrics.get("judgement", {}).get("metrics", {})

        if not isinstance(metrics, dict):
            return

        for metric_name, value in metrics.items():
            if not isinstance(value, (int, float)):
                continue

            await cls._update_metric(db, device_model, record.item_id, metric_name, value, record.id)

    @classmethod
    async def _update_metric(
        cls,
        db: AsyncSession,
        device_model: str,
        item_id: int,
        metric_name: str,
        value: float,
        record_id: int
    ):
        """更新单个指标的基线。"""
        result = await db.execute(
            select(Baseline).where(
                Baseline.device_model == device_model,
                Baseline.item_id == item_id,
                Baseline.metric_name == metric_name
            )
        )
        baseline = result.scalar_one_or_none()

        if not baseline:
            baseline = Baseline(
                device_model=device_model,
                item_id=item_id,
                metric_name=metric_name,
                avg_value=str(value),
                min_value=str(value),
                max_value=str(value),
                sample_count=1,
                last_record_id=record_id
            )
            db.add(baseline)
        else:
            count = baseline.sample_count or 1
            old_avg = float(baseline.avg_value or 0)
            new_avg = (old_avg * count + value) / (count + 1)
            baseline.avg_value = str(round(new_avg, 4))
            baseline.min_value = str(min(float(baseline.min_value or value), value))
            baseline.max_value = str(max(float(baseline.max_value or value), value))
            baseline.sample_count = count + 1
            baseline.last_record_id = record_id
            baseline.updated_at = datetime.now(timezone.utc)

        await db.commit()

    @classmethod
    async def get_baselines(
        cls,
        db: AsyncSession,
        device_model: Optional[str] = None,
        item_id: Optional[int] = None
    ) -> List[Baseline]:
        """查询基线。"""
        query = select(Baseline)
        if device_model:
            query = query.where(Baseline.device_model == device_model)
        if item_id:
            query = query.where(Baseline.item_id == item_id)

        result = await db.execute(query)
        return result.scalars().all()

    @classmethod
    async def get_baseline(
        cls,
        db: AsyncSession,
        device_model: str,
        item_id: int,
        metric_name: str
    ) -> Optional[Baseline]:
        """查询单个指标基线。"""
        result = await db.execute(
            select(Baseline).where(
                Baseline.device_model == device_model,
                Baseline.item_id == item_id,
                Baseline.metric_name == metric_name
            )
        )
        return result.scalar_one_or_none()


class GoldenCaseService:
    """黄金案例服务：积累同一型号设备的标准通过输出。"""

    @classmethod
    async def update_from_record(
        cls,
        db: AsyncSession,
        record: TestRecord,
        device_model: str
    ):
        """根据通过的测试记录更新黄金案例。"""
        if record.status != "pass":
            return

        result = await db.execute(
            select(GoldenCase).where(
                GoldenCase.item_id == record.item_id,
                GoldenCase.device_model == device_model
            )
        )
        case = result.scalar_one_or_none()

        if not case:
            case = GoldenCase(
                item_id=record.item_id,
                device_model=device_model,
                expected_status="pass",
                expected_output_pattern=None,
                sample_output=record.output[:1000] if record.output else None,
                pass_count=1,
                total_count=1,
                is_active=True
            )
            db.add(case)
        else:
            case.pass_count += 1
            case.total_count += 1
            case.sample_output = record.output[:1000] if record.output else case.sample_output
            case.updated_at = datetime.now(timezone.utc)

        await db.commit()

    @classmethod
    async def find_case(
        cls,
        db: AsyncSession,
        item_id: int,
        device_model: str
    ) -> Optional[GoldenCase]:
        """查找黄金案例。"""
        result = await db.execute(
            select(GoldenCase).where(
                GoldenCase.item_id == item_id,
                GoldenCase.device_model == device_model,
                GoldenCase.is_active == True
            )
        )
        return result.scalar_one_or_none()
