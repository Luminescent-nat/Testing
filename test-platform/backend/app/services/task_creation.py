"""统一任务创建服务（契约 v1.1 task-execution §10 / CHANGES 变更包 2 B3）。

手动创建（POST /tasks）与 AI 自然语言创建（POST /ai/tasks/natural）都收口到
本服务的 `create_task_instance`，复用完全相同的：设备查找 → 设备授权（403）→
设备可用性（409）→ item 存在/禁用（400，R14）→ 自定义参数/调度校验 → 幂等
（claim/replay/409）→ 建任务（AI 附带 plan 快照）→ immediate 启动 → 统一 201 响应。

入口不得自行写 TestTask / 推进设备状态。
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.errors import build_error_body
from app.models import Device, TestItem, TestTask
from app.schemas import ResponseModel, TestTaskCreate, TestTaskResponse
from app.services.authorization import ensure_can_create_task_on_device
from app.services.device import DeviceService
from app.services.param_contract import (
    ParamValidationError,
    validate_custom_parameters,
)
from app.services.idempotency import (
    OPERATION_TASK_CREATE,
    IdempotencyConflictError,
    IdempotencyKeyError,
    canonical_request_sha256,
    check_replay_or_conflict,
    run_idempotent,
    validate_idempotency_key,
    wait_for_response,
)
from app.services.scheduler import SCHEDULE_DAILY, SCHEDULE_IMMEDIATE, SCHEDULE_ONCE, compute_next_run
from app.services.task_executor import TaskExecutor
from app.services.task_snapshot import build_item_snapshot

logger = logging.getLogger(__name__)

# AI 入口独立幂等 operation（契约 v1.1 §10：与手动创建同一幂等服务、不同操作类型）
OPERATION_TASK_CREATE_AI = "task_create_ai"

device_service = DeviceService()


class ItemValidationError(Exception):
    """item_ids 存在性/禁用校验失败（R14：400，details.field=item_ids.<下标>）。"""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


def validation_error_response(
    field: str, reason: str, message: str = "任务参数不合法"
) -> JSONResponse:
    """按契约错误外层返回 400 VALIDATION_ERROR，details.field 精确到字段路径。"""
    return JSONResponse(
        status_code=400,
        content=build_error_body(
            "VALIDATION_ERROR", message, {"field": field, "reason": reason}
        ),
    )


def resolve_idempotency_key(header_value: Optional[str]) -> str:
    """解析 Idempotency-Key 请求头（契约 §2：必填，8～128 可打印 ASCII）。

    缺失 → 400 VALIDATION_ERROR（U-D1 已确认收紧为强制必填）；
    提供但不合法 → 400 VALIDATION_ERROR。
    """
    if header_value is None:
        raise HTTPException(
            status_code=400, detail="缺少必填请求头 Idempotency-Key"
        )
    try:
        return validate_idempotency_key(header_value)
    except IdempotencyKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def find_idempotent_replay(
    db: AsyncSession,
    *,
    user_id: int,
    operation: str,
    idempotency_key: Optional[str],
    request_payload: Any,
) -> Optional[dict]:
    """幂等重放预检（AI 入口专用，契约 v1.1 §10）。

    AI 流程在统一创建服务之外还有授权与设备可用性检查；为避免「设备进入 testing
    后同键重放被 409 掩盖」，先查已有成功响应并直接重放（不执行任何业务检查、
    不触发知识/LLM）。同键不同请求体抛 IdempotencyConflictError（409）；
    无记录或首次执行尚在写回响应时返回 None，调用方继续正常流程。
    """
    if idempotency_key is None:
        return None
    validate_idempotency_key(idempotency_key)
    request_sha256 = canonical_request_sha256(request_payload)
    record = await check_replay_or_conflict(
        db,
        user_id=user_id,
        operation=operation,
        idempotency_key=idempotency_key,
        request_sha256=request_sha256,
    )
    if record is None:
        return None
    if record.response_json is not None:
        return record.response_json
    waited = await wait_for_response(db, record)
    if waited is not None and waited.response_json is not None:
        return waited.response_json
    return None


async def create_task_instance(
    db: AsyncSession,
    *,
    user,
    request: TestTaskCreate,
    plan: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    operation: str = OPERATION_TASK_CREATE,
    request_payload: Optional[Any] = None,
) -> dict:
    """统一任务创建（手动与 AI 共用）。

    - plan：AI 规划快照（仅 AI 入口传入，落库到 TestTask.plan；手动为 None）；
    - operation：幂等操作类型（手动 task_create，AI task_create_ai）；
    - request_payload：幂等请求摘要来源（AI 传 {"text":..., "device_serial":...}，
      因为响应体形状与手动一致而 name 来自规划结果，不能直接用请求模型 dump）；
    - 成功返回 ResponseModel dict（HTTP 201，code=201）。
    """
    key = resolve_idempotency_key(idempotency_key)
    payload_for_sha = request_payload if request_payload is not None else request.model_dump(mode="json")

    async def _execute() -> dict:
        # 设备查找
        device = await device_service.get_device_by_serial(db, request.device_serial)
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

        # 统一设备授权（契约 device-authorization §1，写前校验）：
        # 管理员任意；普通用户仅 owner=本人且 PC 一致；他人/null/PC 不一致一律 403，零写入。
        ensure_can_create_task_on_device(user, device)

        # 设备不可用属冲突（契约 task-execution §2/V1-04）：offline/maintenance → 409 CONFLICT；
        # testing 不再拒绝，任务以 pending 排队，由执行器的设备锁按 FIFO 串行化执行
        if device.status == "offline":
            raise HTTPException(status_code=409, detail="设备离线")

        if device.status == "maintenance":
            raise HTTPException(status_code=409, detail="设备维护中")

        # 测试项存在性/禁用校验（R14：非法 item_id 为 400，details.field=item_ids.<下标>；
        # 写前校验，任何任务写入前拒绝）
        items_result = await db.execute(
            select(TestItem).where(TestItem.id.in_(request.item_ids))
        )
        existing_items = {item.id: item for item in items_result.scalars().all()}
        for index, item_id in enumerate(request.item_ids):
            item = existing_items.get(item_id)
            if not item:
                raise ItemValidationError(f"item_ids.{index}", "测试项不存在")
            if not item.enabled:
                raise ItemValidationError(f"item_ids.{index}", "测试项已禁用")

        # 自定义参数契约校验（R13/R14）：外层键=已选 item_id 十进制串，内层扁平白名单；
        # 非法时走与 item_ids 相同的 ItemValidationError 通道（400，details.field 精确路径）
        try:
            validate_custom_parameters(
                request.custom_parameters or {}, request.item_ids, existing_items
            )
        except ParamValidationError as exc:
            raise ItemValidationError(exc.field, exc.reason)

        # 调度配置：immediate 创建后立即启动；once/daily 计算下次触发时间，
        # 任务保持 pending，由后台调度器到期启动
        schedule_type = request.schedule_type.value
        next_run_at = None
        if schedule_type != SCHEDULE_IMMEDIATE:
            if not request.scheduled_time:
                raise HTTPException(status_code=400, detail="定时任务必须指定执行时间")
            try:
                next_run_at = compute_next_run(schedule_type, request.scheduled_time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="执行时间格式不正确（定时一次用 YYYY-MM-DD HH:MM，每日定时用 HH:MM）"
                )
            if schedule_type == SCHEDULE_ONCE and next_run_at <= datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="定时时间已过，请重新选择")

        # 创建设备任务（AI 附带 plan 快照；daily 创建模板行，实例由调度器生成）
        snapshot = build_item_snapshot([existing_items[iid] for iid in request.item_ids])
        is_daily_template = schedule_type == SCHEDULE_DAILY
        task = TestTask(
            user_id=user.id,
            device_id=device.id,
            name=request.name or f"测试任务_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            selected_items=request.item_ids,
            custom_parameters=request.custom_parameters or {},
            status="pending",
            schedule_type=schedule_type,
            scheduled_time=request.scheduled_time if schedule_type != SCHEDULE_IMMEDIATE else None,
            next_run_at=next_run_at,
            plan=plan,
            task_kind="daily_template" if is_daily_template else "instance",
            item_snapshot=snapshot,
            item_snapshot_status="complete",
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
            message="daily 模板创建成功" if is_daily_template else "任务创建成功",
            data=response_data
        ).model_dump(mode="json")

    try:
        response, _record = await run_idempotent(
            db,
            user_id=user.id,
            operation=operation,
            idempotency_key=key,
            request_payload=payload_for_sha,
            execute=_execute,
            task_id_extractor=lambda resp: resp["data"]["id"],
        )
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency-Key 已被不同的请求体使用")
    return response
