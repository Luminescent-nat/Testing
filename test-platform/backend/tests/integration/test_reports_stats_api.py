"""报告统计接口（趋势/按模块）集成测试。"""
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, TestItem, TestModule, TestRecord, TestTask, User


async def _create_task(
    db: AsyncSession, user: User, device: Device, name: str, when: datetime
) -> TestTask:
    """直接落库一个已完成任务，日期可控。"""
    task = TestTask(
        user_id=user.id,
        device_id=device.id,
        name=name,
        selected_items=[],
        status="completed",
        created_at=when,
        completed_at=when,
    )
    db.add(task)
    await db.flush()
    return task


async def _add_record(
    db: AsyncSession, task: TestTask, item: TestItem, status: str
) -> None:
    db.add(TestRecord(task_id=task.id, item_id=item.id, status=status))


@pytest.mark.asyncio
async def test_stats_trend_date_aggregation(
    client: AsyncClient,
    admin_token: str,
    test_db: AsyncSession,
    admin_user: User,
    sample_device: Device,
    sample_item: TestItem,
):
    """TC-RPT-STATS-001: 趋势接口按天聚合任务数/通过数/失败数。"""
    now = datetime.now()
    yesterday = now - timedelta(days=1)

    t1 = await _create_task(test_db, admin_user, sample_device, "t-pass", now)
    t2 = await _create_task(test_db, admin_user, sample_device, "t-pass2", yesterday)
    t3 = await _create_task(test_db, admin_user, sample_device, "t-fail", yesterday)
    await _add_record(test_db, t1, sample_item, "pass")
    await _add_record(test_db, t2, sample_item, "pass")
    await _add_record(test_db, t3, sample_item, "timeout")  # timeout 算失败
    await test_db.commit()

    response = await client.get(
        "/api/v1/reports/stats/trend",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"days": 7},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["days"] == 7
    series = {item["date"]: item for item in data["series"]}
    assert len(data["series"]) == 7

    today_entry = series[now.date().isoformat()]
    assert today_entry["total"] == 1
    assert today_entry["passed"] == 1
    assert today_entry["failed"] == 0
    assert today_entry["pass_rate"] == 100.0

    yesterday_entry = series[yesterday.date().isoformat()]
    assert yesterday_entry["total"] == 2
    assert yesterday_entry["passed"] == 1
    assert yesterday_entry["failed"] == 1
    assert yesterday_entry["pass_rate"] == 50.0


@pytest.mark.asyncio
async def test_stats_trend_default_days_and_empty(
    client: AsyncClient, admin_token: str
):
    """TC-RPT-STATS-002: 默认 30 天且无任务时返回全零序列。"""
    response = await client.get(
        "/api/v1/reports/stats/trend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["days"] == 30
    assert len(data["series"]) == 30
    assert all(item["total"] == 0 for item in data["series"])


@pytest.mark.asyncio
async def test_stats_trend_normal_user_only_own_tasks(
    client: AsyncClient,
    admin_token: str,
    normal_token: str,
    test_db: AsyncSession,
    admin_user: User,
    normal_user: User,
    sample_device: Device,
    sample_item: TestItem,
):
    """TC-RPT-STATS-003: 普通用户仅统计自己的任务。"""
    now = datetime.now()
    t_admin = await _create_task(test_db, admin_user, sample_device, "admin-task", now)
    t_normal = await _create_task(test_db, normal_user, sample_device, "normal-task", now)
    await _add_record(test_db, t_admin, sample_item, "pass")
    await _add_record(test_db, t_normal, sample_item, "fail")
    await test_db.commit()

    response = await client.get(
        "/api/v1/reports/stats/trend",
        headers={"Authorization": f"Bearer {normal_token}"},
        params={"days": 1},
    )
    assert response.status_code == 200
    series = {item["date"]: item for item in response.json()["data"]["series"]}
    today_entry = series[now.date().isoformat()]
    assert today_entry["total"] == 1
    assert today_entry["passed"] == 0
    assert today_entry["failed"] == 1


@pytest.mark.asyncio
async def test_stats_by_module(
    client: AsyncClient,
    admin_token: str,
    test_db: AsyncSession,
    admin_user: User,
    sample_device: Device,
    sample_item: TestItem,
    sample_module: TestModule,
):
    """TC-RPT-STATS-004: 按模块统计通过率，timeout 计入失败，skip 不计入。"""
    now = datetime.now()
    task = await _create_task(test_db, admin_user, sample_device, "t-module", now)
    await _add_record(test_db, task, sample_item, "pass")
    await _add_record(test_db, task, sample_item, "fail")
    await _add_record(test_db, task, sample_item, "timeout")
    await _add_record(test_db, task, sample_item, "skip")
    await test_db.commit()

    response = await client.get(
        "/api/v1/reports/stats/by-module",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    entry = next(i for i in items if i["module_name"] == sample_module.name)
    # pass + fail + timeout 计入，skip 不计入
    assert entry["total"] == 3
    assert entry["passed"] == 1
    assert entry["failed"] == 2
    assert entry["pass_rate"] == round(1 / 3 * 100, 1)


@pytest.mark.asyncio
async def test_stats_endpoints_require_auth(client: AsyncClient):
    """TC-RPT-STATS-005: 未登录访问统计接口返回 401（契约：未认证为 401 UNAUTHENTICATED）。"""
    for path in ("/api/v1/reports/stats/trend", "/api/v1/reports/stats/by-module"):
        response = await client.get(path)
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"
