"""任务定时/周期调度器：后台周期扫描到期的调度任务并启动执行。

调度语义（契约 scheduler-and-data §2）：
- schedule_type = immediate：创建后立即启动，不经过调度器；
- schedule_type = once：scheduled_time 为 "YYYY-MM-DD HH:MM"（服务器本地时间），
  到期一次性触发原任务（instance），触发后清除 next_run_at；
- schedule_type = daily：任务行为 daily_template（task_kind=daily_template），
  到期不执行模板本身，而是在事务内：
  1. 计算不晚于 now 的最近一次计划时刻 scheduled_for（UTC）；
  2. 以 (template_id, scheduled_for) 插入独立 pending 实例（UNIQUE 索引兜底，
     并发扫描/重启重复触发至多创建一个实例，冲突即跳过）；
  3. 成功后才启动该实例；前一实例仍 running 时新实例 pending 排队等锁；
  4. 模板 next_run_at 推进到严格晚于 now 的下一计划时刻；
  服务停机跨多个日期至多创建上述最近一次实例，不逐日补跑；
- 设备被占用不影响触发，执行器设备锁（DeviceLock）会按 FIFO 排队执行；
- 任务被取消/删除后 status 不再是 pending，调度器自然不再触发。
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


def compute_last_planned_time(scheduled_time: str, now: datetime) -> datetime:
    """daily：计算不晚于 now 的最近一次计划时刻（UTC aware）。

    服务停机跨多个日期也只取最近一次（不逐日补跑，契约 §2 步骤 2）。
    """
    hour, minute = map(int, scheduled_time.strip().split(":"))
    local_now = now.astimezone()
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate > local_now:
        candidate -= timedelta(days=1)
    return candidate.astimezone(timezone.utc)


async def trigger_due_tasks(db: AsyncSession) -> list:
    """扫描并启动 next_run_at 到期的调度任务，返回被启动的任务 ID 列表。

    先在数据库中推进/清除 next_run_at 再启动执行，保证调度器异常或重启
    不会重复触发同一个 once 任务；daily 实例的唯一索引保证同一计划时刻
    至多一个实例（并发扫描的重复插入被 IntegrityError 拦截）。
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TestTask).where(
            TestTask.status == "pending",
            TestTask.next_run_at.isnot(None),
            TestTask.deleted_at.is_(None),
        )
    )
    triggered = []
    for task in result.scalars().all():
        if _to_utc(task.next_run_at) > now:
            continue  # 未到期

        if task.schedule_type == SCHEDULE_DAILY:
            instance_id = await _trigger_daily_template(db, task, now)
            if instance_id is not None:
                triggered.append(instance_id)
            continue

        # once（及未知类型兜底）：一次性触发原任务后清除 next_run_at
        task.next_run_at = None
        await db.commit()
        triggered.append(task.id)

    for task_id in triggered:
        TaskExecutor.start_task(task_id)
        logger.info("调度器启动到期任务 %s", task_id)
    return triggered


async def _trigger_daily_template(
    db: AsyncSession, template: TestTask, now: datetime
) -> "int | None":
    """daily 模板到期触发（契约 §2 步骤 1～5），返回新实例 ID；重复触发返回 None。

    - 查询重 + 唯一索引双重兜底：同 scheduled_for 的实例已存在（并发扫描或
      重启重复触发）时跳过创建，仅推进模板 next_run_at；
    - 实例快照复制模板快照（模板创建时已固化测试项配置）。
    """
    scheduled_for = compute_last_planned_time(template.scheduled_time, now)
    next_run_at = compute_next_run(SCHEDULE_DAILY, template.scheduled_time, now)

    existing = await db.scalar(
        select(TestTask.id).where(
            TestTask.template_id == template.id,
            TestTask.scheduled_for == scheduled_for,
        )
    )
    instance_id = None
    if existing is None:
        instance = TestTask(
            user_id=template.user_id,
            device_id=template.device_id,
            name=template.name,
            selected_items=template.selected_items,
            custom_parameters=template.custom_parameters,
            status="pending",
            schedule_type=SCHEDULE_ONCE,  # 实例是一次性执行
            task_kind="instance",
            template_id=template.id,
            scheduled_for=scheduled_for,
            item_snapshot=template.item_snapshot,
            item_snapshot_status=template.item_snapshot_status or "complete",
        )
        db.add(instance)
        try:
            await db.flush()
            instance_id = instance.id
        except IntegrityError:
            # 唯一索引兜底：其他扫描已创建同计划时刻实例，本次不重复创建/启动
            await db.rollback()
            logger.info(
                "daily 模板 %s 的计划实例 %s 已存在（并发扫描去重）",
                template.id, scheduled_for,
            )
            # rollback 后模板对象已游离，重新加载并只推进 next_run_at
            fresh = await db.get(TestTask, template.id)
            if fresh is not None:
                fresh.next_run_at = next_run_at
                await db.commit()
            return None

    template.next_run_at = next_run_at
    await db.commit()
    if instance_id is not None:
        logger.info(
            "daily 模板 %s 生成计划实例 %s（scheduled_for=%s）",
            template.id, instance_id, scheduled_for,
        )
    return instance_id


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
