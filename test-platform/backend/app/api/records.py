import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.api.auth import get_current_user
from app.models import User, TestRecord, TestTask

router = APIRouter(prefix="/records", tags=["测试记录"])


@router.get("/{record_id}/log")
async def download_record_log(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """下载测试记录的完整日志文件（执行过程中实时落盘的内容）。"""
    result = await db.execute(select(TestRecord).where(TestRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    # 权限检查（与任务查看一致：管理员或任务创建者）
    result = await db.execute(select(TestTask).where(TestTask.id == record.task_id))
    task = result.scalar_one_or_none()
    if task and current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限查看")

    if not record.log_file_path:
        raise HTTPException(status_code=404, detail="日志文件不存在")

    log_path = os.path.join(get_settings().LOGS_PATH, record.log_file_path)
    if not os.path.isfile(log_path):
        raise HTTPException(status_code=404, detail="日志文件不存在")

    return FileResponse(
        log_path,
        media_type="text/plain",
        filename=os.path.basename(log_path)
    )
