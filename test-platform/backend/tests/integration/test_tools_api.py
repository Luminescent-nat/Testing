"""测试工具接口集成测试。"""
import os
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_tools_empty(client: AsyncClient, admin_token: str):
    """TC-TOOL-001: 获取工具列表（空）。"""
    response = await client.get(
        "/api/v1/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "items" in data


@pytest.mark.asyncio
async def test_upload_and_delete_tool(client: AsyncClient, admin_token: str):
    """TC-TOOL-002: 管理员上传并删除工具。"""
    tool_path = os.path.join(
        os.path.dirname(__file__), "..", "storage", "tools", "test_upload_tool"
    )
    os.makedirs(os.path.dirname(tool_path), exist_ok=True)
    with open(tool_path, "wb") as f:
        f.write(b"#!/system/bin/sh\necho ok\n")

    with open(tool_path, "rb") as f:
        response = await client.post(
            "/api/v1/tools",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={
                "name": "test_upload_tool",
                "description": "upload test tool",
                "version": "1.0",
                "architecture": "arm64-v8a",
            },
            files={"file": ("test_upload_tool", f, "application/octet-stream")},
        )
    assert response.status_code == 200, response.text
    tool_id = response.json()["data"]["id"]

    response = await client.get(
        f"/api/v1/tools/{tool_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200

    response = await client.delete(
        f"/api/v1/tools/{tool_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200

    if os.path.exists(tool_path):
        os.remove(tool_path)


@pytest.mark.asyncio
async def test_upload_tool_forbidden_for_normal(client: AsyncClient, normal_token: str):
    """TC-TOOL-003: 普通用户不能上传工具。"""
    response = await client.post(
        "/api/v1/tools",
        headers={"Authorization": f"Bearer {normal_token}"},
        data={"name": "normal_tool"},
        files={"file": ("x", b"x", "application/octet-stream")},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_empty_file_rejected(client: AsyncClient, admin_token: str):
    """TC-TOOL-004: 上传空文件应返回 400。"""
    response = await client.post(
        "/api/v1/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"name": "empty_tool"},
        files={"file": ("empty_tool", b"", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "为空" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_upload_small_file_success(client: AsyncClient, admin_token: str):
    """TC-TOOL-005: 上传正常大小文件应成功并返回工具 ID。"""
    response = await client.post(
        "/api/v1/tools",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={
            "name": "small_tool",
            "description": "small upload test tool",
            "version": "1.0",
            "architecture": "arm64-v8a",
        },
        files={"file": ("small_tool", b"#!/system/bin/sh\necho small\n", "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["name"] == "small_tool"
    assert data["file_size"] == 28
    tool_id = data["id"]

    response = await client.delete(
        f"/api/v1/tools/{tool_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
