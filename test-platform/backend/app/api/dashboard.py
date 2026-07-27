from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models import Device, TestTask, User
from app.schemas import ResponseModel

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/stats", response_model=ResponseModel)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """仪表盘头部统计卡片数据（今日任务/通过率/失败数/运行中/设备）。

    普通用户仅统计自己创建的任务与本人 pc_identifier 的设备，管理员统计全平台。
    趋势图与模块通过率复用 /reports/stats/trend、/reports/stats/by-module。
    """
    own_only = current_user.role != "admin"
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)

    # ---- 今日任务 ----
    stmt = select(TestTask.status).where(TestTask.created_at >= today_start)
    if own_only:
        stmt = stmt.where(TestTask.user_id == current_user.id)
    today_statuses = [row[0] for row in (await db.execute(stmt)).all()]
    today_passed = sum(1 for s in today_statuses if s == "completed")
    today_failed = sum(1 for s in today_statuses if s in ("failed", "cancelled"))
    finished = today_passed + today_failed

    # ---- 运行中/排队中任务 ----
    running_stmt = select(TestTask.id).where(TestTask.status.in_(["running", "pending"]))
    if own_only:
        running_stmt = running_stmt.where(TestTask.user_id == current_user.id)
    running_tasks = len((await db.execute(running_stmt)).all())

    # ---- 设备 ----
    dev_stmt = select(Device.status)
    if own_only:
        dev_stmt = dev_stmt.where(Device.pc_identifier == (current_user.pc_identifier or ""))
    device_statuses = [row[0] for row in (await db.execute(dev_stmt)).all()]

    return ResponseModel(code=200, data={
        "today": {
            "tasks": len(today_statuses),
            "passed": today_passed,
            "failed": today_failed,
            "pass_rate": round(today_passed / finished * 100, 1) if finished else None,
        },
        "running_tasks": running_tasks,
        "devices": {
            "total": len(device_statuses),
            "online": sum(1 for s in device_statuses if s in ("online", "testing")),
        },
    })
