"""AI 自然语言任务接口集成测试。"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from app.models import Device
from app.services.task_executor import TaskExecutor


@pytest.mark.asyncio
async def test_ai_task_natural_ddr(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    mock_adb,
):
    """TC-AI-001: 自然语言创建 DDR 测试任务。"""
    mock_adb.execute_shell = AsyncMock(return_value=("MemTotal: 2048 kB", "", 0))
    response = await client.post(
        "/api/v1/ai/tasks/natural",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"text": "对 rk3568 设备做 DDR 稳定性测试"},
    )
    if response.status_code != 200:
        print("AI TASK RESPONSE:", response.status_code, response.text)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["device_serial"] == sample_device.serial_number
    assert data["plan"]["selected_modules"] == ["ddr"]
    assert len(data["plan"]["item_ids"]) >= 1

    # 等待 API 启动的后台任务完成
    running = TaskExecutor._running_tasks.get(data["task_id"])
    if running:
        await running
    task_res = await client.get(
        f"/api/v1/tasks/{data['task_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert task_res.json()["data"]["status"] in ("completed", "failed")


@pytest.mark.asyncio
async def test_ai_task_no_device(
    client: AsyncClient, admin_token: str
):
    """TC-AI-002: 没有可用设备时无法创建任务。"""
    response = await client.post(
        "/api/v1/ai/tasks/natural",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"text": "对不存在的设备做 DDR 测试"},
    )
    assert response.status_code == 400
    assert "无法" in response.json()["detail"] or "未找到" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ai_task_empty_text(
    client: AsyncClient, admin_token: str
):
    """TC-AI-003: 空文本拒绝。"""
    response = await client.post(
        "/api/v1/ai/tasks/natural",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"text": "   "},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ai_task_no_matching_items(
    client: AsyncClient, admin_token: str, sample_device: Device
):
    """TC-AI-004: 无法匹配到测试项时拒绝。"""
    response = await client.post(
        "/api/v1/ai/tasks/natural",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"text": "对 rk3568 做 nfc 测试"},
    )
    assert response.status_code == 400
    assert "未找到" in response.json()["detail"]
