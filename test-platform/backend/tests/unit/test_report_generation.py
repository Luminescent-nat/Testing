"""任务收尾后台报告生成落盘的单元测试。"""
import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.config import get_settings
from tests.unit.test_task_executor import _cleanup_executor, _run_single_item_task


async def _wait_for_report_path(test_db, task, timeout=5.0):
    """轮询等待后台报告生成回填 report_path。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await test_db.refresh(task)
        if task.report_path:
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_completed_task_generates_report_files(
    test_db, mock_adb, admin_user, monkeypatch, tmp_path
):
    """TC-RPT-FILE-001: 任务完成后 report_path 赋值且 JSON/HTML 报告文件已落盘。"""
    monkeypatch.setattr(get_settings(), "REPORTS_PATH", str(tmp_path))
    mock_adb.execute_shell = AsyncMock(return_value=("ok", "", 0))

    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="report-file-serial",
        item_kwargs={"result_parse": {"pass_pattern": "ok"}, "timeout": 30},
    )
    try:
        await test_db.refresh(task)
        assert task.status == "completed"

        # 报告由后台任务异步生成：轮询等待 report_path 回填
        assert await _wait_for_report_path(test_db, task), "报告未在超时内生成"
        assert task.report_path == f"task_{task.id}/report.json"

        json_path = tmp_path / f"task_{task.id}" / "report.json"
        html_path = tmp_path / f"task_{task.id}" / "report.html"
        assert json_path.exists()
        assert html_path.exists()
        assert f'"task_id": {task.id}' in json_path.read_text(encoding="utf-8")
        assert "<html" in html_path.read_text(encoding="utf-8")
    finally:
        await _cleanup_executor(task.id)


@pytest.mark.asyncio
async def test_report_generation_failure_does_not_affect_task(
    test_db, mock_adb, admin_user, monkeypatch, tmp_path
):
    """TC-RPT-FILE-002: 后台报告生成失败不影响任务收尾状态。"""
    monkeypatch.setattr(get_settings(), "REPORTS_PATH", str(tmp_path))
    mock_adb.execute_shell = AsyncMock(return_value=("ok", "", 0))
    build_mock = AsyncMock(side_effect=RuntimeError("报告生成爆炸"))
    monkeypatch.setattr("app.api.reports._build_report", build_mock)

    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="report-fail-serial",
        item_kwargs={"result_parse": {"pass_pattern": "ok"}, "timeout": 30},
    )
    try:
        await test_db.refresh(task)
        assert task.status == "completed"

        # 等后台报告任务确实执行过（并失败，异常被吞掉仅记日志）
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and build_mock.call_count == 0:
            await asyncio.sleep(0.05)
        assert build_mock.call_count >= 1

        # 任务收尾状态不受影响，report_path 未回填、文件未生成
        await test_db.refresh(task)
        assert task.status == "completed"
        assert task.report_path is None
        assert not (tmp_path / f"task_{task.id}" / "report.json").exists()
    finally:
        await _cleanup_executor(task.id)
