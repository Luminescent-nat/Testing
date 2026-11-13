from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.auth import get_current_user
from app.models import User
from app.schemas import ResponseModel, TestTaskCreate
from app.services.authorization import ensure_can_create_task_on_device
from app.services.llm_client import LLMClient
from app.services.nl_task_planner import NLTaskPlanner
from app.services.task_creation import (
    ItemValidationError,
    OPERATION_TASK_CREATE_AI,
    create_task_instance,
    find_idempotent_replay,
    resolve_idempotency_key,
    validation_error_response,
)
from app.services.idempotency import IdempotencyConflictError

router = APIRouter(prefix="/ai/tasks", tags=["AI 测试"])


def _get_llm_client():
    """授权与设备可用性校验通过后才初始化 LLM 客户端（契约 v1.1 §10 授权顺序）。"""
    try:
        client = LLMClient.get_default_client()
        if client and client.api_key:
            return client
    except Exception:
        pass
    return None


@router.post("/natural", response_model=ResponseModel, status_code=201)
async def create_task_from_natural_language(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """通过自然语言创建测试任务（HTTP 201；契约 v1.1 §10 授权顺序 + 统一创建服务）。

    流程：文本 → resolve_device（仅设备候选匹配，不触知识库/LLM）→
    ensure_can_create_task_on_device（403，与手动创建完全一致）→ 设备可用性
    （testing/offline/maintenance → 409）→ 通过后才 plan_for_device（知识/LLM）→
    item_ids 校验 → 统一创建服务（task_creation.create_task_instance，
    幂等 operation=task_create_ai，plan 快照落库），不自行写任务。

    请求示例:
    {
        "text": "对 rk3568 设备做 DDR 稳定性测试"
    }
    """
    text = (data or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="输入文本不能为空")

    pc_identifier = current_user.pc_identifier or ""
    planner = NLTaskPlanner(db, llm_client=None)

    # 1) 仅设备候选匹配（授权前唯一允许的查询）
    device = await planner.resolve_device(text, pc_identifier)
    if not device:
        raise HTTPException(status_code=400, detail="无法从输入中识别目标设备或测试意图")

    # 2) 与手动创建完全相同的设备授权校验（v1.1 §10：授权先于知识/LLM）
    ensure_can_create_task_on_device(current_user, device)

    # 2.5) 幂等重放预检：同键同文本直接返回首次响应（不重复做状态/知识/LLM）；
    #      同键不同文本 → 409。请求摘要与统一创建服务一致。
    key = resolve_idempotency_key(idempotency_key)
    ai_request_payload = {"text": text, "device_serial": device.serial_number}
    try:
        replay = await find_idempotent_replay(
            db,
            user_id=current_user.id,
            operation=OPERATION_TASK_CREATE_AI,
            idempotency_key=key,
            request_payload=ai_request_payload,
        )
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency-Key 已被不同的请求体使用")
    if replay is not None:
        return replay

    # 3) 设备可用性（409 CONFLICT，与手动创建 D2 同口径）
    if device.status == "testing":
        raise HTTPException(status_code=409, detail="设备正在执行其他任务")

    if device.status == "offline":
        raise HTTPException(status_code=409, detail="设备离线")

    if device.status == "maintenance":
        raise HTTPException(status_code=409, detail="设备维护中")

    # 4) 授权/可用性通过后才读取该设备相关知识条目并可能调用 LLM
    planner.llm_client = _get_llm_client()
    plan = await planner.plan_for_device(text, device)

    if not plan.get("item_ids"):
        raise HTTPException(status_code=400, detail="未找到匹配的测试项")

    plan["llm_used"] = planner.llm_invoked
    plan["llm_available"] = planner.llm_client is not None

    # 5) 统一创建服务：同一校验/授权/幂等/落库/启动（AI 附带 plan 快照与独立幂等 operation）
    request = TestTaskCreate(
        device_serial=device.serial_number,
        name=plan.get("intent") or f"AI任务_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        item_ids=plan["item_ids"],
        custom_parameters={},
    )
    try:
        return await create_task_instance(
            db,
            user=current_user,
            request=request,
            plan=plan,
            idempotency_key=idempotency_key,
            operation=OPERATION_TASK_CREATE_AI,
            request_payload=ai_request_payload,
        )
    except ItemValidationError as exc:
        return validation_error_response(exc.field, exc.reason)
