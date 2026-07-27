from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload, selectinload
from typing import Optional, List
from datetime import datetime, timezone

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin
from app.models import User, Device, TestTask, TestItem, TestRecord
from app.schemas import (
    TestTaskCreate, TestTaskResponse, TestTaskDetail, 
    TestRecordResponse, TestRecordDetail, ResponseModel, TaskStatus
)
from app.services.device import DeviceService
from app.services.execution_engine import EngineFactory, validate_custom_param_value
from app.services.task_executor import TaskExecutor
from app.services.scheduler import compute_next_run, SCHEDULE_IMMEDIATE, SCHEDULE_ONCE

router = APIRouter(prefix="/tasks", tags=["测试任务"])
device_service = DeviceService()


@router.post("", response_model=ResponseModel)
async def create_task(
    task_data: TestTaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建测试任务"""
    # 检查设备
    device = await device_service.get_device_by_serial(db, task_data.device_serial)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    # 检查设备是否可用：离线/维护中拒绝创建；设备被占用（testing）不再拒绝，
    # 任务以 pending 排队，由执行器的设备锁按 FIFO 串行化执行（修复并发创建的 TOCTOU 竞态）
    if device.status == "offline":
        raise HTTPException(status_code=400, detail="设备离线")

    if device.status == "maintenance":
        raise HTTPException(status_code=400, detail="设备维护中")
    
    # 检查测试项
    for item_id in task_data.item_ids:
        result = await db.execute(select(TestItem).where(TestItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail=f"测试项不存在: {item_id}")

    # 自定义参数安全校验：值会拼入 shell 命令，拒绝 shell 元字符（防命令注入）
    for key, value in (task_data.custom_parameters or {}).items():
        error = validate_custom_param_value(value)
        if error:
            raise HTTPException(status_code=400, detail=f"参数 {key} 不合法: {error}")
    
    # 调度配置：immediate 创建后立即启动；once/daily 计算下次触发时间，
    # 任务保持 pending，由后台调度器到期启动
    schedule_type = task_data.schedule_type.value
    next_run_at = None
    if schedule_type != SCHEDULE_IMMEDIATE:
        if not task_data.scheduled_time:
            raise HTTPException(status_code=400, detail="定时任务必须指定执行时间")
        try:
            next_run_at = compute_next_run(schedule_type, task_data.scheduled_time)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="执行时间格式不正确（定时一次用 YYYY-MM-DD HH:MM，每日定时用 HH:MM）"
            )
        if schedule_type == SCHEDULE_ONCE and next_run_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="定时时间已过，请重新选择")

    # 创建设备任务
    task = TestTask(
        user_id=current_user.id,
        device_id=device.id,
        name=task_data.name or f"测试任务_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        selected_items=task_data.item_ids,
        custom_parameters=task_data.custom_parameters or {},
        status="pending",
        schedule_type=schedule_type,
        scheduled_time=task_data.scheduled_time if schedule_type != SCHEDULE_IMMEDIATE else None,
        next_run_at=next_run_at
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    if schedule_type == SCHEDULE_IMMEDIATE:
        # 更新设备状态并立即启动异步任务执行
        await device_service.update_device_status(db, device.id, "testing")
        TaskExecutor.start_task(task.id)

    # 预加载 device 关系，确保返回中包含 device_serial
    result = await db.execute(
        select(TestTask).options(joinedload(TestTask.device)).where(TestTask.id == task.id)
    )
    task_with_device = result.scalar_one()

    response_data = TestTaskResponse.model_validate(task_with_device).model_dump()
    if task_with_device.device:
        response_data["device_serial"] = task_with_device.device.serial_number

    return ResponseModel(
        code=200,
        message="任务创建成功",
        data=response_data
    )


@router.get("", response_model=ResponseModel)
async def list_tasks(
    status: Optional[TaskStatus] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取任务列表"""
    query = select(TestTask).options(selectinload(TestTask.records))
    
    # 权限控制
    if current_user.role != "admin":
        query = query.where(TestTask.user_id == current_user.id)
    
    if status:
        query = query.where(TestTask.status == status)
    
    query = query.order_by(desc(TestTask.created_at))
    
    # 获取总数
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())
    
    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return ResponseModel(
        code=200,
        data={
            "items": [TestTaskResponse.model_validate(t) for t in tasks],
            "total": total,
            "page": page,
            "page_size": page_size
        }
    )


@router.get("/{task_id}", response_model=ResponseModel)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取任务详情"""
    result = await db.execute(
        select(TestTask)
        .options(joinedload(TestTask.device), joinedload(TestTask.user), selectinload(TestTask.records))
        .where(TestTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 权限检查
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限查看此任务")
    
    response_data = TestTaskDetail.model_validate(task).model_dump()
    if task.device:
        response_data["device_serial"] = task.device.serial_number
    if task.user:
        response_data["executor"] = {
            "user_id": task.user.id,
            "username": task.user.username,
            "role": task.user.role
        }
    
    return ResponseModel(code=200, data=response_data)


@router.post("/{task_id}/cancel", response_model=ResponseModel)
async def cancel_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """取消任务"""
    result = await db.execute(
        select(TestTask).where(TestTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 权限检查
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限取消此任务")
    
    # 只能取消pending或running的任务
    if task.status not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="任务无法取消")
    
    # 先通知执行器取消正在运行的协程，避免后台任务继续执行并把状态覆盖回 completed
    executor_cancelled = TaskExecutor.cancel_task(task_id)
    
    task.status = "cancelled"
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()
    
    # 设备释放：若执行器侧任务仍在运行，由其收尾逻辑（含 adb 探活）负责释放，
    # 避免把离线设备误置 online；否则由 API 层直接释放
    if not executor_cancelled:
        await device_service.update_device_status(db, task.device_id, "online")
    
    return ResponseModel(code=200, message="任务已取消")


@router.post("/{task_id}/rerun-failed", response_model=ResponseModel)
async def rerun_failed_items(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """重跑失败项：取该任务中失败/错误/超时的测试项创建新任务执行"""
    result = await db.execute(
        select(TestTask)
        .options(joinedload(TestTask.device))
        .where(TestTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 权限检查（与创建任务一致：登录用户，且只能操作自己的任务）
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限重跑此任务")

    # 收集失败/错误/超时记录对应的测试项，保持原任务的测试项顺序
    records_result = await db.execute(
        select(TestRecord).where(TestRecord.task_id == task_id)
    )
    records = records_result.scalars().all()
    failed_item_ids = {r.item_id for r in records if r.status in ("fail", "error", "timeout")}
    item_ids = [item_id for item_id in task.selected_items if item_id in failed_item_ids]

    if not item_ids:
        raise HTTPException(status_code=400, detail="任务没有失败项，无需重跑")

    # 检查设备（与创建任务一致：离线/维护中拒绝，testing 排队执行）
    device = task.device
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.status == "offline":
        raise HTTPException(status_code=400, detail="设备离线")
    if device.status == "maintenance":
        raise HTTPException(status_code=400, detail="设备维护中")

    # 只保留失败项的自定义参数
    failed_keys = {str(item_id) for item_id in item_ids}
    custom_parameters = {
        k: v for k, v in (task.custom_parameters or {}).items() if k in failed_keys
    }

    new_task = TestTask(
        user_id=current_user.id,
        device_id=device.id,
        name=f"{task.name or f'测试任务_{task.id}'}（重跑）",
        selected_items=item_ids,
        custom_parameters=custom_parameters,
        status="pending"
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)

    # 更新设备状态
    await device_service.update_device_status(db, device.id, "testing")

    # 启动异步任务执行
    TaskExecutor.start_task(new_task.id)

    response_data = TestTaskResponse.model_validate(new_task).model_dump()
    response_data["device_serial"] = device.serial_number

    return ResponseModel(
        code=200,
        message="已创建重跑任务",
        data=response_data
    )


@router.get("/{task_id}/records", response_model=ResponseModel)
async def get_task_records(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取任务的测试记录"""
    result = await db.execute(
        select(TestTask).where(TestTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 权限检查
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限查看")
    
    # 获取记录，同时加载测试项与模块名称
    records_result = await db.execute(
        select(TestRecord)
        .where(TestRecord.task_id == task_id)
        .options(joinedload(TestRecord.item).joinedload(TestItem.module))
    )
    records = records_result.scalars().all()
    
    return ResponseModel(
        code=200,
        data={
            "items": [TestRecordDetail.model_validate(r) for r in records],
            "total": len(records)
        }
    )


@router.delete("/{task_id}", response_model=ResponseModel)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除任务（管理员）"""
    result = await db.execute(
        select(TestTask).where(TestTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    await db.delete(task)
    await db.commit()
    
    return ResponseModel(code=200, message="任务已删除")
