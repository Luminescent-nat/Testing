from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.api.auth import get_current_user
from app.models import User, Device, TestTask
from app.schemas import ResponseModel
from app.services.task_executor import TaskExecutor
from app.services.nl_task_planner import NLTaskPlanner
from app.services.llm_client import LLMClient

router = APIRouter(prefix="/ai/tasks", tags=["AI 测试"])


@router.post("/natural", response_model=ResponseModel)
async def create_task_from_natural_language(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """通过自然语言创建测试任务。

    请求示例:
    {
        "text": "对 rk3568 设备做 DDR 稳定性测试"
    }
    """
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="输入文本不能为空")

    pc_identifier = current_user.pc_identifier or ""

    # 初始化 LLM 客户端（如果配置了 API Key）
    llm_client = None
    llm_available = False
    try:
        llm_client = LLMClient.get_default_client()
        if llm_client and llm_client.api_key:
            llm_available = True
    except Exception:
        llm_client = None

    planner = NLTaskPlanner(db, llm_client)
    plan = await planner.plan(text, current_user.id, pc_identifier)

    if not plan:
        raise HTTPException(status_code=400, detail="无法从输入中识别目标设备或测试意图")

    # 标记是否使用了 LLM 增强，以及降级原因
    plan["llm_used"] = llm_available and planner.llm_invoked
    plan["llm_available"] = llm_available

    if not plan.get("item_ids"):
        raise HTTPException(status_code=400, detail="未找到匹配的测试项")

    # 检查设备状态
    device_id = plan["device_id"]
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    if device.status == "testing":
        raise HTTPException(status_code=409, detail="设备正在执行其他任务")

    if device.status == "offline":
        raise HTTPException(status_code=400, detail="设备离线")

    # 创建任务，并保存 AI 规划快照
    task = TestTask(
        user_id=current_user.id,
        device_id=device.id,
        name=plan["intent"] or f"AI任务_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        selected_items=plan["item_ids"],
        custom_parameters={},
        status="pending",
        plan=plan
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 更新设备状态并启动执行
    device.status = "testing"
    await db.commit()

    TaskExecutor.start_task(task.id)

    return ResponseModel(
        code=200,
        message="AI 任务已创建并开始执行",
        data={
            "task_id": task.id,
            "plan": plan,
            "device_serial": device.serial_number
        }
    )
