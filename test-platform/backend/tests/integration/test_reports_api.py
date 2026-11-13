"""报告管理接口集成测试。"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock

from app.config import get_settings
from app.models import Device, TestItem, TestTask
from app.services.task_executor import TaskExecutor


@pytest_asyncio.fixture(scope="function")
async def completed_task(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    sample_item: TestItem,
    mock_adb,
):
    """创建一个已同步执行完成的任务。"""
    mock_adb.execute_shell = AsyncMock(return_value=("ok", "", 0))
    create_res = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "ReportTask",
            "item_ids": [sample_item.id],
        },
    )
    task_id = create_res.json()["data"]["id"]
    # 等待 API 启动的后台任务完成
    running = TaskExecutor._running_tasks.get(task_id)
    if running:
        await running
    return task_id


@pytest.mark.asyncio
async def test_get_single_task_report(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-001: 获取单任务报告。"""
    response = await client.get(
        f"/api/v1/reports/{completed_task}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task_id"] == completed_task
    assert data["summary"]["total_items"] == 1
    assert data["summary"]["passed"] == 1


@pytest.mark.asyncio
async def test_export_report_json(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-002: 导出 JSON 报告。"""
    response = await client.get(
        f"/api/v1/reports/{completed_task}/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"format": "json"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["task_id"] == completed_task


@pytest.mark.asyncio
async def test_export_report_html(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-003: 导出 HTML 报告。"""
    response = await client.get(
        f"/api/v1/reports/{completed_task}/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"format": "html"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<html" in response.text


@pytest.mark.asyncio
async def test_export_report_markdown(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-004: 导出 Markdown 报告。"""
    response = await client.get(
        f"/api/v1/reports/{completed_task}/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"format": "markdown"},
    )
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert response.text.startswith("# ")
    assert "报告" in response.text


@pytest.mark.asyncio
async def test_export_report_excel(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-005: 导出 Excel 报告。"""
    response = await client.get(
        f"/api/v1/reports/{completed_task}/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"format": "excel"},
    )
    assert response.status_code == 200
    assert "spreadsheetml.sheet" in response.headers["content-type"]
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_export_report_word(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-006: 导出 Word 报告。"""
    response = await client.get(
        f"/api/v1/reports/{completed_task}/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"format": "word"},
    )
    assert response.status_code == 200
    assert "wordprocessingml.document" in response.headers["content-type"]
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_get_summary_report(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-007: 获取全部任务总报告。"""
    response = await client.get(
        "/api/v1/reports/summary/all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["report_type"] == "batch"
    assert data["summary"]["total_items"] >= 1
    # 汇总报告中的每个任务应携带自身创建时间，而不是统一使用报告生成时间
    for task in data.get("tasks", []):
        assert "created_at" in task


# ---------------------------------------------------------------- 空态收口（T-25 演示问题 2）
@pytest.mark.asyncio
async def test_summary_all_empty_db_returns_200_empty_state(
    client: AsyncClient, admin_token: str
):
    """空库/无任务：GET /reports/summary/all 返回 200 空汇总（不再 404）。"""
    response = await client.get(
        "/api/v1/reports/summary/all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    data = body["data"]

    # 顶层形状与非空 batch 汇总一致
    assert data["report_type"] == "batch"
    assert data["report_version"] == "1.1"
    assert data["task_count"] == 0
    assert data["tasks"] == []
    assert data["results"] == []
    assert data["module_statistics"] == {}
    assert "executor" in data and "created_at" in data

    # summary 五类计数全 0、pass_rate=null、total_items=0；counts 形状为五类
    summary = data["summary"]
    assert summary["total_items"] == 0
    assert summary["passed"] == 0
    assert summary["failed"] == 0
    assert summary["skipped"] == 0
    assert summary["error"] == 0
    assert summary["timeout"] == 0
    assert summary["counts"] == {
        "pass": 0, "fail": 0, "skip": 0, "error": 0, "timeout": 0
    }
    assert summary["pass_rate"] is None

    # 前端空态兼容字段（items/total），且 JSON 可序列化（response.json 已证明）
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_summary_all_nonempty_shape_unchanged(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """非空库：汇总形状与统计口径不变（同一 batch 结构，pass_rate 按五类分母）。"""
    response = await client.get(
        "/api/v1/reports/summary/all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["report_type"] == "batch"
    assert data["task_count"] >= 1
    assert len(data["tasks"]) == data["task_count"]
    summary = data["summary"]
    assert set(summary["counts"]) == {"pass", "fail", "skip", "error", "timeout"}
    assert summary["total_items"] >= 1
    assert summary["pass_rate"] == 100.0  # 完成 1 项 pass，无失败


@pytest.mark.asyncio
async def test_single_report_missing_task_still_404(
    client: AsyncClient, admin_token: str
):
    """单任务 /reports/{id} 不存在仍按契约 404（空态收口不影响单任务语义）。"""
    response = await client.get(
        "/api/v1/reports/999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_batch_export_report(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-008: 批量导出报告。"""
    response = await client.get(
        "/api/v1/reports/batch/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"task_ids": str(completed_task), "format": "html"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_batch_export_nonexistent_tasks_still_4xx(
    client: AsyncClient, admin_token: str
):
    """显式批量导出：任务全部不存在时仍整体失败（空态收口不影响 batch 语义）。"""
    response = await client.get(
        "/api/v1/reports/batch/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"task_ids": "999998,999999", "format": "json"},
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_get_item_log(
    client: AsyncClient, admin_token: str, completed_task: int, sample_item: TestItem
):
    """TC-RPT-009: 获取测试项日志。"""
    response = await client.get(
        f"/api/v1/reports/{completed_task}/items/{sample_item.id}/log",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["item_id"] == sample_item.id


@pytest.mark.asyncio
async def test_get_nonexistent_item_log(
    client: AsyncClient, admin_token: str, completed_task: int
):
    """TC-RPT-010: 获取不存在的测试项日志应 404。"""
    response = await client.get(
        f"/api/v1/reports/{completed_task}/items/99999/log",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


@pytest_asyncio.fixture(scope="function")
async def cached_report_task(
    test_db, admin_user, sample_device: Device, monkeypatch, tmp_path
):
    """创建一个已完成任务并预置落盘缓存文件，REPORTS_PATH 指向临时目录。"""
    monkeypatch.setattr(get_settings(), "REPORTS_PATH", str(tmp_path))
    task = TestTask(
        user_id=admin_user.id,
        device_id=sample_device.id,
        name="cached-report-task",
        selected_items=[],
        status="completed",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    report_dir = tmp_path / f"task_{task.id}"
    report_dir.mkdir(parents=True)
    return task, report_dir


@pytest.mark.asyncio
async def test_export_report_serves_cached_file(
    client: AsyncClient, admin_token: str, cached_report_task, monkeypatch
):
    """TC-RPT-011: 报告文件已落盘时导出接口直接返回文件内容，不再现算。"""
    task, report_dir = cached_report_task
    cached_html = "<html><body>cached-report-content</body></html>"
    (report_dir / "report.html").write_text(cached_html, encoding="utf-8")

    build_mock = AsyncMock(side_effect=AssertionError("缓存存在时不应重新计算报告"))
    monkeypatch.setattr("app.api.reports._build_report", build_mock)

    response = await client.get(
        f"/api/v1/reports/{task.id}/export",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"format": "html"},
    )
    assert response.status_code == 200
    assert response.text == cached_html
    assert build_mock.call_count == 0


@pytest.mark.asyncio
async def test_get_report_serves_cached_json(
    client: AsyncClient, admin_token: str, cached_report_task, monkeypatch
):
    """TC-RPT-012: 报告 JSON 已落盘时获取接口返回文件内容，不再现算。"""
    task, report_dir = cached_report_task
    (report_dir / "report.json").write_text(
        f'{{"task_id": {task.id}, "marker": "cached-report"}}', encoding="utf-8"
    )

    build_mock = AsyncMock(side_effect=AssertionError("缓存存在时不应重新计算报告"))
    monkeypatch.setattr("app.api.reports._build_report", build_mock)

    response = await client.get(
        f"/api/v1/reports/{task.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["marker"] == "cached-report"
    assert data["task_id"] == task.id
    assert build_mock.call_count == 0
