import asyncio
import json
import logging
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import AsyncSessionLocal
from app.models import TestTask, TestRecord, TestItem, TestModule
from app.services.auth import decode_token

logger = logging.getLogger(__name__)
router = APIRouter()

# 首条消息认证等待超时（秒），超时未收到合法认证消息则关闭连接
AUTH_TIMEOUT = 10


class TaskProgressManager:
    """管理任务进度 WebSocket 连接。"""

    def __init__(self):
        # task_id -> List[WebSocket]
        self._connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, task_id: int, websocket: WebSocket):
        """登记连接（websocket 须已完成 accept，认证由端点负责）。"""
        self._connections.setdefault(task_id, []).append(websocket)
        logger.info("WebSocket 连接到任务 %s，当前连接数 %s", task_id, len(self._connections[task_id]))

    def disconnect(self, task_id: int, websocket: WebSocket):
        connections = self._connections.get(task_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self._connections.pop(task_id, None)

    async def broadcast(self, task_id: int, message: dict):
        """向指定任务的所有连接广播消息。"""
        connections = self._connections.get(task_id, [])
        if not connections:
            return

        payload = json.dumps(message, default=str, ensure_ascii=False)
        disconnected = []
        for conn in connections:
            try:
                await conn.send_text(payload)
            except Exception as exc:
                logger.warning("向任务 %s 推送 WebSocket 消息失败: %s", task_id, exc)
                disconnected.append(conn)

        for conn in disconnected:
            self.disconnect(task_id, conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """向单个连接发送消息。"""
        payload = json.dumps(message, default=str, ensure_ascii=False)
        try:
            await websocket.send_text(payload)
        except Exception as exc:
            logger.warning("WebSocket 单播失败: %s", exc)


progress_manager = TaskProgressManager()


async def build_progress_message(task_id: int) -> dict:
    """从数据库构建当前任务进度消息。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TestTask)
            .options(joinedload(TestTask.device))
            .where(TestTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            return {"type": "error", "task_id": task_id, "message": "任务不存在"}

        records_result = await db.execute(
            select(TestRecord, TestItem, TestModule)
            .join(TestItem, TestRecord.item_id == TestItem.id)
            .join(TestModule, TestItem.module_id == TestModule.id)
            .where(TestRecord.task_id == task_id)
            .order_by(TestRecord.id)
        )

        completed_results = []
        current_item = None
        for record, item, module in records_result.all():
            item_data = {
                "id": item.id,
                "record_id": record.id,
                "name": item.name,
                "module_name": module.name,
                "status": record.status,
                "execution_time": record.execution_time,
                "fail_reason": record.fail_reason,
                "extracted_data": record.extracted_data,
            }

            if record.status == "running":
                current_item = item_data
            else:
                completed_results.append(item_data)

        total = len(task.selected_items) if task.selected_items else 0
        completed = len([r for r in completed_results if r["status"] in ("pass", "fail", "skip", "error", "timeout")])
        if current_item:
            completed += 1

        return {
            "type": "test_progress",
            "task_id": task_id,
            "device_serial": task.device.serial_number if task.device else None,
            "data": {
                "total_items": total,
                "completed_items": completed,
                "progress_percent": task.progress_percent,
                "task_status": task.status,
                "current_item": current_item,
                "completed_results": completed_results,
            },
            "timestamp": task.completed_at.isoformat() if task.completed_at else (task.started_at.isoformat() if task.started_at else task.created_at.isoformat()),
        }


async def notify_progress(task_id: int):
    """由 TaskExecutor 调用，主动推送任务进度。"""
    message = await build_progress_message(task_id)
    await progress_manager.broadcast(task_id, message)


async def push_log(task_id: int, record_id: int, line: str):
    """由 TaskExecutor 调用，向监控页推送一条实时日志行。

    不触碰数据库；该任务没有 WebSocket 连接时 broadcast 为 no-op。
    """
    await progress_manager.broadcast(task_id, {
        "type": "log",
        "task_id": task_id,
        "record_id": record_id,
        "line": line,
    })


@router.websocket("/ws/tasks/{task_id}")
async def task_progress_websocket(websocket: WebSocket, task_id: int):
    """任务进度 WebSocket 端点。

    认证方式：accept 后等待客户端首条消息 {"token": "..."}（AUTH_TIMEOUT 秒超时），
    校验 token 有效性与任务归属，全部通过才进入进度推送，否则以 1008 关闭，
    避免 token 出现在 URL 与访问日志中。
    """
    await websocket.accept()

    # 首条消息认证：超时或连接断开直接关闭
    try:
        auth_data = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT)
    except asyncio.TimeoutError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="认证超时")
        return
    except WebSocketDisconnect:
        logger.info("任务 %s WebSocket 在认证前断开连接", task_id)
        return

    token = None
    try:
        token = json.loads(auth_data).get("token")
    except json.JSONDecodeError:
        pass

    # 简单鉴权：校验 token 是否有效
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="缺少 token")
        return

    payload = decode_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="token 无效")
        return

    # 任务归属校验：仅任务创建者或管理员可订阅该任务的进度与日志
    username = payload.get("sub")
    async with AsyncSessionLocal() as db:
        from app.models import User
        user_result = await db.execute(select(User).where(User.username == username))
        user = user_result.scalar_one_or_none()
        task_result = await db.execute(select(TestTask).where(TestTask.id == task_id))
        task = task_result.scalar_one_or_none()

    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="用户不存在")
        return
    if not task:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="任务不存在")
        return
    if user.role != "admin" and task.user_id != user.id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="无权访问该任务")
        return

    await progress_manager.connect(task_id, websocket)

    try:
        # 连接后立即推送一次当前进度
        initial_message = await build_progress_message(task_id)
        await progress_manager.send_personal(websocket, initial_message)

        while True:
            # 保持连接，客户端可发送 ping，服务端回复 pong
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await progress_manager.send_personal(websocket, {"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.info("任务 %s WebSocket 断开连接", task_id)
    except Exception as exc:
        logger.warning("任务 %s WebSocket 异常: %s", task_id, exc)
    finally:
        progress_manager.disconnect(task_id, websocket)
