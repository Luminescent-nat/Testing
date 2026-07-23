"""任务定时/周期调度器：后台周期扫描到期的调度任务并启动执行。

调度语义：
- schedule_type = immediate：创建后立即启动，不经过调度器；
- schedule_type = once：scheduled_time 为 "YYYY-MM-DD HH:MM"（服务器本地时间），
  到期一次性触发，触发后清除 next_run_at；
- schedule_type = daily：scheduled_time 为 "HH:MM"（服务器本地时间），
  到期触发并把 next_run_at 顺延到下一日同一时刻；
- 设备被占用不影响触发，执行器设备锁（DeviceLock）会按 FIFO 排队执行；
- 任务被取消/删除后 status 不再是 pending，调度器自然不再触发。
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import TestTask
from app.services.task_executor import TaskExecutor

logger = logging.getLogger(__name__)

SCHEDULE_IMMEDIATE = "immediate"
SCHEDULE_ONCE = "once"
SCHEDULE_DAILY = "daily"


def _to_utc(dt: datetime) -> datetime:
    """统一为 UTC aware 时间（SQLite 读回的 DateTime 是 naive，按 UTC 处理）。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_next_run(schedule_type: str, scheduled_time: str, now: datetime = None) -> datetime:
    """计算下次触发时间（输入为服务器本地时间，返回 UTC aware 时间）。

    - once：scheduled_time 为 "YYYY-MM-DD HH:MM"，原样转换为 UTC；
    - daily：scheduled_time 为 "HH:MM"，取当天该时刻，已过则顺延到次日。
    格式非法时抛 ValueError，由调用方（API 层）转为 400。
    """
    now = now or datetime.now(timezone.utc)
    if schedule_type == SCHEDULE_ONCE:
        local = datetime.strptime(scheduled_time.strip(), "%Y-%m-%d %H:%M")
        # naive 时间按服务器本地时区解释，再转 UTC
        return local.astimezone(timezone.utc)
    if schedule_type == SCHEDULE_DAILY:
        hour, minute = map(int, scheduled_time.strip().split(":"))
        local_now = now.astimezone()
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)
    return None


async def trigger_due_tasks(db: AsyncSession) -> list:
    """扫描并启动 next_run_at 到期的调度任务，返回被启动的任务 ID 列表。

    先在数据库中推进/清除 next_run_at 再启动执行，保证调度器异常或重启
    不会重复触发同一个 once 任务。
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TestTask).where(
            TestTask.status == "pending",
            TestTask.next_run_at.isnot(None),
        )
    )
    triggered = []
    for task in result.scalars().all():
        if _to_utc(task.next_run_at) > now:
            continue  # 未到期
        if task.schedule_type == SCHEDULE_DAILY:
            task.next_run_at = compute_next_run(SCHEDULE_DAILY, task.scheduled_time, now)
        else:
            # once（及未知类型兜底）一次性触发后清除
            task.next_run_at = None
        triggered.append(task.id)
    await db.commit()

    for task_id in triggered:
        TaskExecutor.start_task(task_id)
        logger.info("调度器启动到期任务 %s", task_id)
    return triggered


async def scheduler_loop():
    """后台调度循环：按 SCHEDULER_INTERVAL 周期扫描到期任务。

    单次扫描异常只记日志，循环继续；仅 CancelledError 退出。
    """
    settings = get_settings()
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await trigger_due_tasks(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("任务调度扫描失败，将在下个周期重试")
        await asyncio.sleep(settings.SCHEDULER_INTERVAL)
