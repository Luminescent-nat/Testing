from fastapi import APIRouter, Depends, Header, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import joinedload, selectinload
from typing import Optional, List
from datetime import datetime, timezone

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin
from app.errors import build_error_body
from app.models import User, Device, TestTask, TestItem, TestRecord
from app.schemas import (
    TestTaskCreate, TestTaskResponse, TestTaskDetail, 
    TestRecordResponse, TestRecordDetail, ResponseModel, TaskStatus
)
from app.services.device import DeviceService
from app.services.authorization import ensure_can_create_task_on_device
from app.services.execution_engine import EngineFactory, validate_custom_param_value
from app.services.task_executor import TaskExecutor
from app.services.scheduler import compute_next_run, SCHEDULE_IMMEDIATE, SCHEDULE_ONCE
from app.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyKeyError,
    run_idempotent,
    validate_idempotency_key,
    OPERATION_TASK_CREATE,
    OPERATION_TASK_RERUN,
)

router = APIRouter(prefix="/tasks", tags=["测试任务"])
device_service = DeviceService()


class _ItemValidationError(Exception):
    """测试项存在性/禁用校验失败（R14：非法 item_id 为 400，details.field=item_ids.<下标>）。"""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


def _validation_error_response(
    field: str, reason: str, message: str = "任务参数不合法"
) -> JSONResponse:
    """按契约错误外层返回 400 VALIDATION_ERROR，details.field 精确到字段路径。"""
    return JSONResponse(
        status_code=400,
        content=build_error_body(
            "VALIDATION_ERROR", message, {"field": field, "reason": reason}
        ),
    )


def _resolve_idempotency_key(header_value: Optional[str]) -> Optional[str]:
    """解析 Idempotency-Key 请求头（契约第 3 节：8～128 可打印 ASCII）。

    缺失 → None（兼容策略：不强幂等，正常执行并在 T-10 记录偏差待确认）；
    提供但不合法 → 400 VALIDATION_ERROR。
    """
    if header_value is None:
        return None
    try:
        return validate_idempotency_key(header_value)
    except IdempotencyKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("", response_model=ResponseModel, status_code=201)
async def create_task(
    task_data: TestTaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """创建测试任务（HTTP 201；携带 Idempotency-Key 时同键同体重放返回首次响应）"""
    key = _resolve_idempotency_key(idempotency_key)
    request_payload = task_data.model_dump(mode="json")

    async def _execute() -> dict:
        # 检查设备
        device = await device_service.get_device_by_serial(db, task_data.device_serial)
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

        # 统一设备授权（契约 device-authorization §1，写前校验）：
        # 管理员任意；普通用户仅 owner=本人且 PC 一致；他人/null/PC 不一致一律 403，零写入。
        ensure_can_create_task_on_device(current_user, device)

        # 设备不可用属冲突（契约 task-execution §2/V1-04）：offline/maintenance → 409 CONFLICT；
        # testing 不再拒绝，任务以 pending 排队，由执行器的设备锁按 FIFO 串行化执行
        if device.status == "offline":
            raise HTTPException(status_code=409, detail="设备离线")

        if device.status == "maintenance":
            raise HTTPException(status_code=409, detail="设备维护中")

        # 测试项存在性/禁用校验（R14：非法 item_id 为 400，details.field=item_ids.<下标>；
        # 写前校验，任何任务写入前拒绝）
        items_result = await db.execute(
            select(TestItem).where(TestItem.id.in_(task_data.item_ids))
        )
        existing_items = {item.id: item for item in items_result.scalars().all()}
        for index, item_id in enumerate(task_data.item_ids):
            item = existing_items.get(item_id)
            if not item:
                raise _ItemValidationError(f"item_ids.{index}", "测试项不存在")
            if not item.enabled:
                raise _ItemValidationError(f"item_ids.{index}", "测试项已禁用")

        # 自定义参数安全校验：值会拼入 shell 命令，拒绝 shell 元字符（防命令注入）
        for key_, value in (task_data.custom_parameters or {}).items():
            error = validate_custom_param_value(value)
            if error:
                raise HTTPException(status_code=400, detail=f"参数 {key_} 不合法: {error}")

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

        response_data = TestTaskResponse.model_validate(task_with_device).model_dump(mode="json")
        if task_with_device.device:
            response_data["device_serial"] = task_with_device.device.serial_number

        return ResponseModel(
            code=201,
            message="任务创建成功",
            data=response_data
        ).model_dump(mode="json")

    if key is None:
        # 兼容策略：缺失 Idempotency-Key = 不强幂等（正常创建，每次都执行）
        try:
            return await _execute()
        except _ItemValidationError as exc:
            return _validation_error_response(exc.field, exc.reason)

    try:
        response, _record = await run_idempotent(
            db,
            user_id=current_user.id,
            operation=OPERATION_TASK_CREATE,
            idempotency_key=key,
            request_payload=request_payload,
            execute=_execute,
            task_id_extractor=lambda resp: resp["data"]["id"],
        )
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency-Key 已被不同的请求体使用")
    except _ItemValidationError as exc:
        return _validation_error_response(exc.field, exc.reason)
    return response


@router.get("", response_model=ResponseModel)
async def list_tasks(
    status: Optional[TaskStatus] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取任务列表（status 精确匹配、search 任务名模糊匹配，均在分页前生效）"""
    filters = []

    # 软删除排除（契约 task-execution §8）：默认列表不返回 deleted_at 非空的任务
    filters.append(TestTask.deleted_at.is_(None))

    # 权限控制
    if current_user.role != "admin":
        filters.append(TestTask.user_id == current_user.id)

    if status:
        filters.append(TestTask.status == status)

    if search and search.strip():
        filters.append(TestTask.name.contains(search.strip()))

    query = (
        select(TestTask)
        .options(selectinload(TestTask.records))
        .where(*filters)
        .order_by(desc(TestTask.created_at))
    )

    # 获取总数（与筛选结果一致）
    total = await db.scalar(
        select(func.count()).select_from(TestTask).where(*filters)
    )

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return ResponseModel(
        code=200,
        data={
            "items": [TestTaskResponse.model_validate(t) for t in tasks],
            "total": total or 0,
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
        .where(TestTask.id == task_id, TestTask.deleted_at.is_(None))
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
    """取消任务

    Deprecated: legacy 路径 POST /tasks/{task_id}/cancel（契约 v1.0 第 4 节），
    仅作短期适配；目标路径为 POST /tasks/{task_id}/cancellations，两者委托同一业务函数。
    """
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


@router.post("/{task_id}/rerun-failed", response_model=ResponseModel, status_code=201)
async def rerun_failed_items(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """重跑失败项：取该任务中失败/错误/超时的测试项创建新任务执行（HTTP 201）

    Deprecated: legacy 路径 POST /tasks/{task_id}/rerun-failed（契约 v1.0 第 4 节），
    仅作短期适配；目标路径为 POST /tasks/{task_id}/reruns，两者委托同一业务函数，
    复用同一 Idempotency-Key 幂等语义（operation=task_rerun，请求体含 task_id）。
    """
    key = _resolve_idempotency_key(idempotency_key)
    request_payload = {"task_id": task_id}

    async def _execute() -> dict:
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

        # 重跑同样复用统一设备授权（写前校验）：源任务 owner 校验之外，
        # 还需当前用户对目标设备具备创建任务权限，防止设备归属变更后越权重跑。
        ensure_can_create_task_on_device(current_user, device)

        if device.status == "offline":
            raise HTTPException(status_code=409, detail="设备离线")
        if device.status == "maintenance":
            raise HTTPException(status_code=409, detail="设备维护中")

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

        response_data = TestTaskResponse.model_validate(new_task).model_dump(mode="json")
        response_data["device_serial"] = device.serial_number

        return ResponseModel(
            code=201,
            message="已创建重跑任务",
            data=response_data
        ).model_dump(mode="json")

    if key is None:
        return await _execute()

    try:
        response, _record = await run_idempotent(
            db,
            user_id=current_user.id,
            operation=OPERATION_TASK_RERUN,
            idempotency_key=key,
            request_payload=request_payload,
            execute=_execute,
            task_id_extractor=lambda resp: resp["data"]["id"],
        )
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency-Key 已被不同的请求体使用")
    return response


# ---- 目标契约路由（POST 创建对应名词子资源，契约 v1.0 通用传输约定第 2 节）----
# 两个别名直接委托既有业务函数，不复制逻辑：同一鉴权（get_current_user）与
# 同一服务/权限语义。取消不做幂等（条件更新天然重复安全）；重跑复用 T-10
# Idempotency-Key 幂等语义（见 create_task_rerun → rerun_failed_items）。
@router.post("/{task_id}/cancellations", response_model=ResponseModel)
async def create_task_cancellation(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """目标路径：创建任务取消动作（POST /tasks/{task_id}/cancellations）。

    委托 legacy cancel_task 处理函数，鉴权与业务语义完全一致（无第二套权限语义）。
    """
    return await cancel_task(task_id=task_id, db=db, current_user=current_user)


@router.post("/{task_id}/reruns", response_model=ResponseModel, status_code=201)
async def create_task_rerun(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """目标路径：创建失败项重跑子资源（POST /tasks/{task_id}/reruns，HTTP 201）。

    委托 legacy rerun_failed_items 处理函数，鉴权、业务与 Idempotency-Key 幂等语义
    完全一致（无第二套权限/幂等语义）。
    """
    return await rerun_failed_items(
        task_id=task_id,
        db=db,
        current_user=current_user,
        idempotency_key=idempotency_key,
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
    """删除任务（管理员，契约 task-execution §8：终态软删除）

    - running/pending → 409 CONFLICT（防止孤儿执行数据）；
    - 终态任务写 deleted_at 软删除，记录/日志/报告引用保留（artifacts=retained）；
    - 重复删除幂等返回 200（不 500、不重复改写）；
    - 非 active 管理员（含 disabled/普通用户）由 get_current_admin → 403。
    """
    result = await db.execute(
        select(TestTask).where(TestTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 幂等重放：已软删除的任务再次删除返回相同当前状态（200）
    if task.deleted_at is not None:
        return ResponseModel(
            code=200,
            message="任务已删除",
            data={"id": task.id, "deleted": True, "artifacts": "retained"},
        )

    # pending/running 禁止删除，防止孤儿执行数据
    if task.status in ("pending", "running"):
        raise HTTPException(status_code=409, detail="当前状态不可删除")

    # 终态软删除：条件写入 deleted_at，记录/日志/报告引用保留
    task.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    return ResponseModel(
        code=200,
        message="任务已删除",
        data={"id": task.id, "deleted": True, "artifacts": "retained"},
    )
