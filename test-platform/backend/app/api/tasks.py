import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update
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
from app.services.authorization import ensure_can_create_task_on_device
from app.services.task_creation import (
    ItemValidationError,
    create_task_instance,
    resolve_idempotency_key,
    validation_error_response,
)
from app.services.task_executor import TaskExecutor
from app.services.idempotency import (
    IdempotencyConflictError,
    run_idempotent,
    OPERATION_TASK_RERUN,
)

router = APIRouter(prefix="/tasks", tags=["测试任务"])
device_service = DeviceService()


@router.post("", response_model=ResponseModel, status_code=201)
async def create_task(
    task_data: TestTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """创建测试任务（HTTP 201；携带 Idempotency-Key 时同键同体重放返回首次响应）。

    薄委托统一创建服务 app/services/task_creation.py（契约 v1.1 §10：
    校验/授权/可用性/item/调度/幂等/落库/启动全部收口同一服务）。
    """
    try:
        return await create_task_instance(
            db,
            user=current_user,
            request=task_data,
            idempotency_key=idempotency_key,
        )
    except ItemValidationError as exc:
        return validation_error_response(exc.field, exc.reason)


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

    task-C1：预检后以条件更新（仅 pending/running → cancelled）落库，提交先于
    响应返回（happens-before）；输掉竞态不覆盖终态，重读当前状态幂等返回。
    SQLite 并发写者交错时可能立即返回 BUSY（死锁规避不等待），带退避重试，
    保证并发取消全部正常返回（无 500）。
    """
    # 提前取标量：重试回滚会 expire 会话内全部 ORM 对象（含依赖注入的
    # current_user），循环内再访问其属性会触发同步惰性加载（MissingGreenlet）
    is_admin = current_user.role == "admin"
    requesting_user_id = current_user.id
    executor_cancelled = False
    for attempt in range(1, 7):
        last_attempt = attempt == 6
        try:
            # 标量查询（非 ORM 对象）：重试回滚会 expire 会话内 ORM 对象，
            # 后续属性访问会触发同步惰性加载（MissingGreenlet）；标量行无此陷阱
            row = (await db.execute(
                select(TestTask.user_id, TestTask.status, TestTask.device_id)
                .where(TestTask.id == task_id)
            )).first()

            if row is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            owner_id, current_status, device_id = row

            # 权限检查
            if not is_admin and owner_id != requesting_user_id:
                raise HTTPException(status_code=403, detail="无权限取消此任务")

            # 只能取消pending或running的任务
            if current_status not in ["pending", "running"]:
                raise HTTPException(status_code=400, detail="任务无法取消")

            # 先通知执行器取消正在运行的协程（单次投递，避免打断取消收尾本身）
            if not executor_cancelled:
                executor_cancelled = TaskExecutor.cancel_task(task_id)

            # 条件更新：仅 pending/running → cancelled；输掉竞态（预检后已被并发
            # 收尾为其他终态）时不覆盖任何状态，重读当前状态幂等返回
            cancelled_at = datetime.now(timezone.utc)
            update_result = await db.execute(
                update(TestTask)
                .where(TestTask.id == task_id, TestTask.status.in_(["pending", "running"]))
                .values(status="cancelled", completed_at=cancelled_at)
            )
            await db.commit()

            if not update_result.rowcount:
                current_status = (await db.execute(
                    select(TestTask.status).where(TestTask.id == task_id)
                )).scalar_one()
                if current_status != "cancelled":
                    # 已被并发收尾为其他终态：按既有非终态语义返回 400
                    raise HTTPException(
                        status_code=400,
                        detail=f"任务当前状态为 {current_status}，无法取消",
                    )

            # 设备释放：若执行器侧任务仍在运行，由其收尾逻辑（含 adb 探活）负责释放，
            # 避免把离线设备误置 online；否则由 API 层直接释放
            if not executor_cancelled:
                await device_service.update_device_status(db, device_id, "online")

            return ResponseModel(code=200, message="任务已取消")
        except HTTPException:
            raise
        except OperationalError:
            if last_attempt:
                raise
            await db.rollback()
            await asyncio.sleep(0.25 * attempt)


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
    key = resolve_idempotency_key(idempotency_key)
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
