"""WebSocket 任务进度推送测试。"""
import asyncio
import os
import tempfile

import pytest
import pytest_asyncio
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import AsyncSessionLocal, Base, engine, get_db
from app.main import app
from app.models import Device, TestItem, TestModule, TestTask, User
from app.services.auth import create_access_token, get_password_hash


async def _prepare_ws_context(test_db):
    """
    在测试数据库中创建 WebSocket 测试所需的完整数据：
    用户、设备、模块、测试项、任务，并返回 token 与 task_id。
    """
    # 创建测试用户
    user = User(
        username="wsadmin",
        password_hash=get_password_hash("wsadmin123"),
        role="admin",
        status="active",
        pc_identifier="test-pc",
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    token, _ = create_access_token(data={"sub": user.username})

    # 创建测试设备
    device = Device(
        serial_number="rk3568-ws",
        model="rk3568",
        brand="rockchip",
        android_version="11",
        sdk_version="30",
        cpu_abi="arm64-v8a",
        status="online",
        owner_id=user.id,
        pc_identifier=user.pc_identifier,
        board="rk3568",
        hardware="rk3568-evb",
        features=["wifi"],
    )
    test_db.add(device)
    await test_db.flush()

    # 复用已存在的 CPU 模块或新建一个
    module_result = await test_db.execute(
        select(TestModule).where(TestModule.name == "CPU")
    )
    module = module_result.scalar_one_or_none()
    if not module:
        module = TestModule(name="CPU", category="processor", created_by=user.id)
        test_db.add(module)
        await test_db.flush()

    # 创建测试项
    item = TestItem(
        module_id=module.id,
        name="WS Test Item",
        exec_type="adb_shell",
        exec_command="echo ok",
        judgement_type="assertion",
        result_parse={"pass_pattern": "ok"},
        timeout=30,
        created_by=user.id,
    )
    test_db.add(item)
    await test_db.flush()

    # 创建任务
    task = TestTask(
        user_id=user.id,
        device_id=device.id,
        name="WS Task",
        selected_items=[item.id],
        status="pending",
        progress_percent=0,
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    return {"token": token, "task_id": task.id}


@pytest_asyncio.fixture(name="ws_context")
async def _ws_context_fixture(test_db, mock_adb):
    """基于测试数据库准备 WS 上下文，并阻止 lifespan 心跳访问真实 ADB。"""
    ctx = await _prepare_ws_context(test_db)
    yield ctx


def test_websocket_invalid_token(ws_context):
    """WS-001: 无效 token 应被断开（首条消息认证）。"""
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/tasks/{ws_context['task_id']}") as ws:
            ws.send_json({"token": "invalid"})
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_json()
            assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


def test_websocket_auth_timeout(ws_context, monkeypatch):
    """WS-002: 超时未发送认证消息应被断开。"""
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr("app.websocket.AUTH_TIMEOUT", 0.05)
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/tasks/{ws_context['task_id']}") as ws:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_json()
            assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


@pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
def test_websocket_ping_pong(ws_context, mock_adb):
    """WS-003: WebSocket ping/pong 正常，且 lifespan 心跳不得绕过 Mock ADB。"""
    import app.main as main_module

    # main.py 在导入时保存 ADBService 引用；此断言防止只 patch device 模块而漏掉 lifespan。
    assert main_module.ADBService() is mock_adb

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/ws/tasks/{ws_context['task_id']}"
        ) as ws:
            # 首条消息发送 token 完成认证
            ws.send_json({"token": ws_context["token"]})
            # 认证通过后会收到当前进度消息
            first = ws.receive_json()
            assert first["type"] == "test_progress"
            assert first["task_id"] == ws_context["task_id"]

            ws.send_text('{"action":"ping"}')
            pong = ws.receive_json()
            assert pong["type"] == "pong"
