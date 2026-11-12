"""端到端完整业务流程测试。"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from app.services.task_executor import TaskExecutor


@pytest.mark.asyncio
async def test_full_workflow(
    client: AsyncClient, mock_adb
):
    """E2E-001: 注册 → 登录 → 发现设备 → 创建任务 → 执行 → 查看报告 → 导出。"""
    # mock adb shell 输出覆盖常见 pass_pattern
    mock_adb.execute_shell = AsyncMock(
        return_value=("MemTotal: 2048 kB\nok\nmmcblk0\nenabled: true\ncarrier 1\n", "", 0)
    )

    # 1. 注册
    register_res = await client.post(
        "/api/v1/auth/register",
        json={"username": "e2euser", "password": "e2epass123", "role": "user"},
    )
    assert register_res.status_code == 200

    # 2. 登录
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"username": "e2euser", "password": "e2epass123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. 刷新设备（mock 返回 rk3568）
    refresh_res = await client.post("/api/v1/devices/refresh", headers=headers)
    assert refresh_res.status_code == 200
    devices = refresh_res.json()["data"]["items"]
    assert len(devices) == 1
    serial = devices[0]["serial_number"]

    # 4. 获取模块与测试项
    modules_res = await client.get("/api/v1/modules", headers=headers)
    assert modules_res.status_code == 200
    modules = modules_res.json()["data"]["items"]
    assert len(modules) >= 1

    # 选择第一个模块的第一个测试项
    first_module = modules[0]
    items_res = await client.get(
        f"/api/v1/modules/{first_module['id']}/items", headers=headers
    )
    assert items_res.status_code == 200
    items = items_res.json()["data"]["items"]
    assert len(items) >= 1
    item_ids = [items[0]["id"]]

    # 5. 创建并执行任务（默认 mock shell 输出已包含 MemTotal，匹配 DDR 容量校验）
    task_res = await client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "device_serial": serial,
            "name": "E2E Full Workflow Task",
            "item_ids": item_ids,
        },
    )
    assert task_res.status_code == 201
    task_id = task_res.json()["data"]["id"]

    # 等待 API 启动的后台任务完成
    running = TaskExecutor._running_tasks.get(task_id)
    if running:
        await running

    # 6. 查看报告
    report_res = await client.get(f"/api/v1/reports/{task_id}", headers=headers)
    assert report_res.status_code == 200
    report_data = report_res.json()["data"]
    assert report_data["summary"]["total_items"] == 1
    assert report_data["summary"]["passed"] == 1

    # 7. 导出 Excel
    export_res = await client.get(
        f"/api/v1/reports/{task_id}/export",
        headers=headers,
        params={"format": "excel"},
    )
    assert export_res.status_code == 200
    assert len(export_res.content) > 0

    # 8. 查看记忆体基线/黄金案例（任务执行后应沉淀）
    baseline_res = await client.get("/api/v1/memory/baselines", headers=headers)
    assert baseline_res.status_code == 200
