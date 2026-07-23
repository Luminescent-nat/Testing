"""记忆体接口集成测试。"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Baseline, FailurePattern, GoldenCase, TestRecord


@pytest.mark.asyncio
async def test_list_failure_patterns(client: AsyncClient, admin_token: str):
    """TC-MEM-001: 查询失败模式库。"""
    response = await client.get(
        "/api/v1/memory/failure-patterns",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    patterns = response.json()["data"]
    assert len(patterns) >= 1
    assert any(p["name"] == "ADB 设备离线" for p in patterns)


@pytest.mark.asyncio
async def test_list_failure_patterns_filter_category(
    client: AsyncClient, admin_token: str
):
    """TC-MEM-002: 按类别过滤失败模式。"""
    response = await client.get(
        "/api/v1/memory/failure-patterns",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"category": "adb"},
    )
    assert response.status_code == 200
    patterns = response.json()["data"]
    assert all(p["category"] == "adb" for p in patterns)


@pytest.mark.asyncio
async def test_list_baselines(
    client: AsyncClient, admin_token: str, test_db
):
    """TC-MEM-003: 查询统计基线。"""
    baseline = Baseline(
        device_model="rk3568",
        item_id=1,
        metric_name="bw_mbps",
        avg_value="150",
        min_value="100",
        max_value="200",
        sample_count=2,
    )
    test_db.add(baseline)
    await test_db.commit()

    response = await client.get(
        "/api/v1/memory/baselines",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"device_model": "rk3568"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["device_model"] == "rk3568"


@pytest.mark.asyncio
async def test_list_golden_cases(
    client: AsyncClient, admin_token: str, test_db
):
    """TC-MEM-004: 查询黄金案例。"""
    case = GoldenCase(
        item_id=1,
        device_model="rk3568",
        expected_status="pass",
        sample_output="ok",
        pass_count=5,
        total_count=5,
        is_active=True,
    )
    test_db.add(case)
    await test_db.commit()

    response = await client.get(
        "/api/v1/memory/golden-cases",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"device_model": "rk3568"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["device_model"] == "rk3568"
