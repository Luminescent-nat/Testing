"""测试编排接口集成测试。"""
import pytest
from httpx import AsyncClient

from app.models import TestItem, TestModule


@pytest.mark.asyncio
async def test_list_modules(client: AsyncClient, admin_token: str):
    """TC-MOD-001: 获取测试模块列表。"""
    from app.main import app
    print("LIFESPAN FUNC:", app.router.lifespan_context)
    response = await client.get(
        "/api/v1/modules",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    print("MODULE DATA:", data)
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_create_module_admin(client: AsyncClient, admin_token: str):
    """TC-MOD-002: 管理员创建模块。"""
    response = await client.post(
        "/api/v1/modules",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "NewModule", "category": "test", "description": "desc"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "NewModule"


@pytest.mark.asyncio
async def test_create_module_forbidden_for_normal(
    client: AsyncClient, normal_token: str
):
    """TC-MOD-003: 普通用户不能创建模块。"""
    response = await client.post(
        "/api/v1/modules",
        headers={"Authorization": f"Bearer {normal_token}"},
        json={"name": "NormalModule", "category": "test"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_module_detail(
    client: AsyncClient, admin_token: str, sample_module: TestModule
):
    """TC-MOD-004: 获取模块详情。"""
    response = await client.get(
        f"/api/v1/modules/{sample_module.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "TestModule"


@pytest.mark.asyncio
async def test_list_items_in_module(
    client: AsyncClient, admin_token: str, sample_module: TestModule, sample_item: TestItem
):
    """TC-MOD-005: 获取模块下测试项列表。"""
    response = await client.get(
        f"/api/v1/modules/{sample_module.id}/items",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Sample Item"


@pytest.mark.asyncio
async def test_create_item_admin(
    client: AsyncClient, admin_token: str, sample_module: TestModule
):
    """TC-MOD-006: 管理员创建测试项。"""
    response = await client.post(
        f"/api/v1/modules/{sample_module.id}/items",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "module_id": sample_module.id,
            "name": "NewItem",
            "exec_type": "adb_shell",
            "exec_command": "echo test",
            "parameters": {},
            "compatibility": {},
            "judgement_type": "assertion",
            "result_parse": {"pass_pattern": "test"},
            "timeout": 30,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "NewItem"


@pytest.mark.asyncio
async def test_update_item_admin(
    client: AsyncClient,
    admin_token: str,
    sample_module: TestModule,
    sample_item: TestItem,
):
    """TC-MOD-007: 管理员更新测试项。"""
    response = await client.put(
        f"/api/v1/modules/{sample_module.id}/items/{sample_item.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "UpdatedItem"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "UpdatedItem"


@pytest.mark.asyncio
async def test_delete_item_admin(
    client: AsyncClient,
    admin_token: str,
    sample_module: TestModule,
    sample_item: TestItem,
):
    """TC-MOD-008: 管理员删除测试项。"""
    response = await client.delete(
        f"/api/v1/modules/{sample_module.id}/items/{sample_item.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
