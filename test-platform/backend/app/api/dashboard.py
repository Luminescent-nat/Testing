from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models import Device, TestTask, User
from app.schemas import ResponseModel
from app.services import statistics

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/stats", response_model=ResponseModel)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """仪表盘头部统计卡片数据（今日任务/通过率/失败数/运行中/设备）。

    V1-06 统一口径：任务通过率仅统计 ``status=completed`` 且业务 result ∈
    (passed, failed) 的任务；全 skip / 零记录（no_result）、平台 failed、cancelled、
    running、pending 分别计数且不进入分母。分母 0 → null。
    普通用户仅统计自己创建的任务与本人 pc_identifier 的设备，管理员统计全平台。
    趋势图与模块通过率复用 /reports/stats/trend、/reports/stats/by-module。
    """
    own_only = current_user.role != "admin"
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)

    # ---- 今日任务（含记录，用于按任务 status + result 统一聚合）----
    # daily 模板（task_kind=daily_template）不执行、不进入执行统计（R16）
    stmt = (
        select(TestTask)
        .options(selectinload(TestTask.records))
        .where(TestTask.created_at >= today_start, TestTask.task_kind == "instance")
    )
    if own_only:
        stmt = stmt.where(TestTask.user_id == current_user.id)
    today_tasks = (await db.execute(stmt)).scalars().all()

    classifications = []
    for task in today_tasks:
        statuses = [r.status for r in task.records]
        selected = task.selected_items or []
        # 存量任务 selected_items 可能为空但有记录：以记录数兜底，保证已完成任务可判定
        total_items = len(selected) if selected else len(statuses)
        classifications.append(
            statistics.classify_task_for_dashboard(task.status, total_items, statuses)
        )
    breakdown = statistics.build_dashboard_breakdown(classifications)

    today_passed = breakdown["passed"]
    today_failed = breakdown["failed"]
    finished = today_passed + today_failed
    pass_rate = round(today_passed / finished * 100, 1) if finished else None

    # ---- 运行中 / 排队中任务（跨全部任务，不限今日创建；模板不计入）----
    running_stmt = select(func.count()).select_from(TestTask).where(
        TestTask.status == "running", TestTask.task_kind == "instance"
    )
    pending_stmt = select(func.count()).select_from(TestTask).where(
        TestTask.status == "pending", TestTask.task_kind == "instance"
    )
    if own_only:
        running_stmt = running_stmt.where(TestTask.user_id == current_user.id)
        pending_stmt = pending_stmt.where(TestTask.user_id == current_user.id)
    running_tasks = (await db.scalar(running_stmt)) or 0
    pending_tasks = (await db.scalar(pending_stmt)) or 0

    # ---- 设备 ----
    dev_stmt = select(Device.status)
    if own_only:
        dev_stmt = dev_stmt.where(Device.pc_identifier == (current_user.pc_identifier or ""))
    device_statuses = [row[0] for row in (await db.execute(dev_stmt)).all()]

    today_completed = breakdown["passed"] + breakdown["failed"] + breakdown["no_result"]
    return ResponseModel(code=200, data={
        "today": {
            # 既有兼容键
            "tasks": len(today_tasks),
            "passed": today_passed,
            "failed": today_failed,
            "pass_rate": pass_rate,
            # reporting-v1.0 §5 完整分列（每个今日任务只归入一个计数键）
            "completed": today_completed,
            "no_result": breakdown["no_result"],
            "execution_failed": breakdown["execution_failed"],
            "cancelled": breakdown["cancelled"],
            "running": breakdown["running"],
            "pending": breakdown["pending"],
        },
        # 完整分列（兼容旧消费者：与 today 内的分列同源同值）
        "task_outcomes": breakdown,
        "running_tasks": running_tasks,
        "pending_tasks": pending_tasks,
        "devices": {
            "total": len(device_statuses),
            "online": sum(1 for s in device_statuses if s in ("online", "testing")),
        },
    })
