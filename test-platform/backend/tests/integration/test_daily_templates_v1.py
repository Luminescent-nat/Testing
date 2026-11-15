"""T-11/12 daily 模板/实例（R16/R17）集成测试：scheduler-and-data §1/§2/§3。

验收场景（契约 §3）：
- 创建 daily 模板：task_kind=daily_template、item_snapshot complete、不启动执行；
- 到期触发生成独立实例（task_kind=instance、template_id、scheduled_for UTC）；
- 同一 scheduled_for 并发/重复扫描恰好一个实例（唯一索引兜底）；
- 跨天未扫描至多一个最近实例，不逐日补跑；
- 取消模板后不再触发；列表 task_kind 过滤正确。
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, TestItem, TestTask
from app.services.scheduler import (
    _to_utc,
    compute_last_planned_time,
    trigger_due_tasks,
)
from app.services.task_executor import TaskExecutor


async def _create_daily_template(
    client: AsyncClient, token: str, device: Device, item: TestItem,
    scheduled_time: str = "00:01",
) -> dict:
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "device_serial": device.serial_number,
            "name": "每日基础测试",
            "item_ids": [item.id],
            "custom_parameters": {},
            "schedule_type": "daily",
            "scheduled_time": scheduled_time,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def stub_start(monkeypatch):
    """记录 start_task 调用但不真实执行（隔离调度器与执行器）。"""
    started: list[int] = []

    def _fake(cls, task_id: int) -> bool:
        started.append(task_id)
        return True

    monkeypatch.setattr(TaskExecutor, "start_task", classmethod(_fake))
    return started


@pytest.mark.asyncio
async def test_create_daily_template_stored_not_executed(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    stub_start,
):
    """创建 daily 模板：201、daily 模板创建成功、task_kind/snapshot 正确、不启动。"""
    body = await _create_daily_template(client, admin_token, sample_device, sample_item)
    assert body["message"] == "daily 模板创建成功"
    data = body["data"]
    assert data["task_kind"] == "daily_template"
    assert data["status"] == "pending"
    assert data["item_snapshot_status"] == "complete"
    assert data["next_run_at"] is not None
    assert stub_start == []  # 模板创建不启动执行

    # 详情返回完整快照（创建时测试项配置）
    detail = await client.get(
        f"/api/v1/tasks/{data['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    snapshot = detail.json()["data"]["item_snapshot"]
    assert snapshot[str(sample_item.id)]["exec_command"] == sample_item.exec_command
    assert snapshot[str(sample_item.id)]["exec_type"] == sample_item.exec_type


@pytest.mark.asyncio
async def test_due_template_spawns_single_instance(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db: AsyncSession, stub_start,
):
    """到期模板生成一个实例：instance/template_id/scheduled_for，随后启动实例而非模板。"""
    body = await _create_daily_template(client, admin_token, sample_device, sample_item)
    template_id = body["data"]["id"]

    # 模拟到期：next_run_at 拨到过去
    template = await test_db.get(TestTask, template_id)
    template.next_run_at = template.next_run_at.replace(year=2000)
    await test_db.commit()

    triggered = await trigger_due_tasks(test_db)
    assert len(triggered) == 1
    assert stub_start == triggered  # 启动的是新实例

    instance = await test_db.get(TestTask, triggered[0])
    assert instance.task_kind == "instance"
    assert instance.template_id == template_id
    assert instance.status == "pending"
    assert instance.scheduled_for is not None
    # scheduled_for = 不晚于 now 的最近一次计划时刻（与算法对拍；SQLite 读回 naive，按 UTC 归一）
    from datetime import datetime, timezone
    expected = compute_last_planned_time(
        template.scheduled_time, datetime.now(timezone.utc)
    )
    assert _to_utc(instance.scheduled_for) == expected

    # 模板 next_run_at 已推进到未来
    await test_db.refresh(template)
    assert template.next_run_at is not None
    assert template.next_run_at.year > 2000


@pytest.mark.asyncio
async def test_repeat_scan_same_scheduled_for_idempotent(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db: AsyncSession, stub_start,
):
    """同一 scheduled_for 重复扫描 10 次：恰好一个实例、一个执行启动，其余无副作用。"""
    body = await _create_daily_template(client, admin_token, sample_device, sample_item)
    template_id = body["data"]["id"]
    template = await test_db.get(TestTask, template_id)
    template.next_run_at = template.next_run_at.replace(year=2000)
    await test_db.commit()

    all_triggered: list[int] = []
    for _ in range(10):
        all_triggered.extend(await trigger_due_tasks(test_db))

    assert len(all_triggered) == 1
    result = await test_db.execute(
        select(TestTask).where(TestTask.template_id == template_id)
    )
    instances = result.scalars().all()
    assert len(instances) == 1  # 唯一索引/查重兜底，不产生重复实例


@pytest.mark.asyncio
async def test_multi_day_outage_single_recent_instance(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db: AsyncSession, stub_start,
):
    """服务停机跨多天：至多创建最近一个计划实例，不逐日补跑。"""
    body = await _create_daily_template(client, admin_token, sample_device, sample_item)
    template_id = body["data"]["id"]
    template = await test_db.get(TestTask, template_id)
    # 模拟停机 3 天：next_run_at 拨到 3 天前
    from datetime import timedelta
    template.next_run_at = template.next_run_at - timedelta(days=3)
    await test_db.commit()

    triggered = await trigger_due_tasks(test_db)
    assert len(triggered) == 1  # 只补最近一个，不逐日补跑

    result = await test_db.execute(
        select(TestTask).where(TestTask.template_id == template_id)
    )
    instances = result.scalars().all()
    assert len(instances) == 1


@pytest.mark.asyncio
async def test_cancelled_template_not_triggered(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db: AsyncSession, stub_start,
):
    """取消 daily 模板后调度器不再触发（历史实例保留）。"""
    body = await _create_daily_template(client, admin_token, sample_device, sample_item)
    template_id = body["data"]["id"]

    cancel = await client.post(
        f"/api/v1/tasks/{template_id}/cancellations",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )
    assert cancel.status_code == 200, cancel.text

    template = await test_db.get(TestTask, template_id)
    template.next_run_at = template.next_run_at.replace(year=2000)
    await test_db.commit()

    triggered = await trigger_due_tasks(test_db)
    assert triggered == []
    assert stub_start == []


@pytest.mark.asyncio
async def test_list_task_kind_filter(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    stub_start,
):
    """列表 task_kind 过滤：默认仅实例；daily_template 仅模板；all 全部。"""
    # 一个 immediate 实例
    immediate = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "item_ids": [sample_item.id],
            "custom_parameters": {},
            "schedule_type": "immediate",
        },
    )
    assert immediate.status_code == 201
    # 一个 daily 模板
    await _create_daily_template(client, admin_token, sample_device, sample_item)

    headers = {"Authorization": f"Bearer {admin_token}"}
    default_list = (await client.get("/api/v1/tasks", headers=headers)).json()["data"]
    assert all(t["task_kind"] == "instance" for t in default_list["items"])
    assert len(default_list["items"]) == 1

    tpl_list = (
        await client.get("/api/v1/tasks", params={"task_kind": "daily_template"}, headers=headers)
    ).json()["data"]
    assert all(t["task_kind"] == "daily_template" for t in tpl_list["items"])
    assert tpl_list["total"] == 1

    all_list = (
        await client.get("/api/v1/tasks", params={"task_kind": "all"}, headers=headers)
    ).json()["data"]
    assert all_list["total"] == 2


@pytest.mark.asyncio
async def test_list_invalid_task_kind_rejected(
    client: AsyncClient, admin_token: str,
):
    response = await client.get(
        "/api/v1/tasks",
        params={"task_kind": "bogus"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_template_excluded_from_dashboard_stats(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    stub_start,
):
    """daily 模板不进入 Dashboard 执行统计（R16）。"""
    await _create_daily_template(client, admin_token, sample_device, sample_item)
    response = await client.get(
        "/api/v1/dashboard/stats",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["today"]["tasks"] == 0
    assert data["today"]["pending"] == 0  # 模板的 pending 不计入今日统计
    assert data["running_tasks"] == 0  # 模板的 pending 不计入排队任务
