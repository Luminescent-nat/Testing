"""V1.1 task-C2：报告 HTML 导出落盘/读取竞态稳定性测试。

RR-V1-REFINAL §3.4：reviewer 两轮独立全量中 test_export_report_html 各出现 1 次
响应体空（`'<html' not in ''`），隔离 3/3 通过 → 判定为导出缓存文件的
「后台落盘与导出读取」竞态：

- 旧实现 `_write_report_file` 直接 `open(path, "wb")`：打开瞬间目标文件即被截断为
  0 字节，内容随后才写入（慢盘/大报告时窗口更宽）；
- 导出端点以 `os.path.exists(file_path)` 判定缓存命中，随后 FileResponse 在发送时
  `os.stat` 并按 stat 大小回读——若 stat 落在「已截断、未写完」窗口内，
  content-length=0 → 响应体为空。

本模块：
1) `test_export_html_mid_write_cache_never_serves_empty_body`：确定性复现该竞态
   （模拟慢速磁盘写，写线程处于 mid-write 窗口时并发导出）——修复前 RED、修复后 GREEN；
2) `test_export_html_20_consecutive_exports_non_empty`：验收要求——模块级连续 20 次
   导出，断言响应体非空且含 <html（混合缓存命中与现算+落盘两条路径）；
3) `test_export_html_concurrent_rewrite_loop`：真实并发重写循环下的非空断言回归。
"""
import asyncio
import builtins
import os
import time
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import reports as reports_module
from app.config import get_settings
from app.models import Device, TestItem, TestTask
from app.services.task_executor import TaskExecutor


async def _create_completed_task(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    sample_item: TestItem,
    mock_adb,
) -> int:
    """通过 API 创建并同步执行完成一个单测试项任务，返回 task_id。"""
    mock_adb.execute_shell = AsyncMock(return_value=("ok", "", 0))
    create_res = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "ExportStabilityTask",
            "item_ids": [sample_item.id],
        },
    )
    assert create_res.status_code == 201, create_res.text
    task_id = create_res.json()["data"]["id"]

    # 等待 API 启动的后台执行任务完成
    running = TaskExecutor._running_tasks.get(task_id)
    if running:
        await running
    return task_id


async def _wait_report_cache_ready(
    test_db: AsyncSession, task_id: int, timeout: float = 5.0
) -> bool:
    """等待收尾后台报告生成完成（report_path 回填且 report.html 落盘）。"""
    deadline = time.monotonic() + timeout
    html_path = os.path.join(
        get_settings().REPORTS_PATH, f"task_{task_id}", "report.html"
    )
    while time.monotonic() < deadline:
        result = await test_db.execute(
            select(TestTask.report_path).where(TestTask.id == task_id)
        )
        report_path = result.scalar_one_or_none()
        if report_path and os.path.exists(html_path) and os.path.getsize(html_path) > 0:
            return True
        await asyncio.sleep(0.05)
    return False


def _report_html_path(task_id: int) -> str:
    return os.path.join(
        get_settings().REPORTS_PATH, f"task_{task_id}", "report.html"
    )


def _export_url(task_id: int) -> str:
    return f"/api/v1/reports/{task_id}/export"


# =========================================================================== #
# ① 确定性竞态复现：后台落盘处于 mid-write（文件已截断、内容未写回）时并发导出
# =========================================================================== #
@pytest.mark.asyncio
async def test_export_html_mid_write_cache_never_serves_empty_body(
    client: AsyncClient,
    admin_token: str,
    test_db: AsyncSession,
    sample_device: Device,
    sample_item: TestItem,
    mock_adb,
    monkeypatch,
):
    """导出读取不得观察到「存在但被截断为 0」的缓存文件。

    模拟慢速磁盘写：写线程 open(..., 'wb') 之后延迟 write —— 旧实现在此窗口内
    目标文件已被截断为 0 字节；导出请求（缓存命中路径）若在此窗口 stat，
    将得到 content-length=0 的空响应（RR-V1-REFINAL §3.4 复现）。
    原子落盘修复后：写方只截断同目录临时文件，目标文件始终是完整旧/新内容。
    """
    task_id = await _create_completed_task(
        client, admin_token, sample_device, sample_item, mock_adb
    )
    assert await _wait_report_cache_ready(test_db, task_id), "后台报告缓存未就绪"

    html_path = _report_html_path(task_id)
    cached = open(html_path, "rb").read()
    assert b"<html" in cached

    delay = 0.4
    real_open = builtins.open

    def slow_open(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        # 仅对报告缓存目录的二进制写放慢（.html 旧实现直写目标；.tmp 修复后的临时文件）
        if "w" in mode and "b" in mode and str(file).endswith((".html", ".tmp")):
            time.sleep(delay)
        return handle

    monkeypatch.setattr(builtins, "open", slow_open)

    # 后台重写（与 generate_task_report_files 的落盘同一路径/同一函数）
    writer = asyncio.create_task(
        asyncio.to_thread(reports_module._write_report_file, html_path, cached)
    )
    # 确保写线程已进入 mid-write 窗口
    await asyncio.sleep(delay * 0.5)

    resp = await client.get(
        _export_url(task_id),
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"format": "html"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.text, "导出响应体为空（缓存文件被并发写截断）"
    assert "<html" in resp.text

    await writer


# =========================================================================== #
# ② 验收：模块级连续 20 次导出，响应体非空且含 <html
# =========================================================================== #
@pytest.mark.asyncio
async def test_export_html_20_consecutive_exports_non_empty(
    client: AsyncClient,
    admin_token: str,
    test_db: AsyncSession,
    sample_device: Device,
    sample_item: TestItem,
    mock_adb,
):
    task_id = await _create_completed_task(
        client, admin_token, sample_device, sample_item, mock_adb
    )
    assert await _wait_report_cache_ready(test_db, task_id), "后台报告缓存未就绪"
    html_path = _report_html_path(task_id)

    for i in range(20):
        if i % 5 == 4 and os.path.exists(html_path):
            # 每 5 次删除一次缓存，混合「现算+落盘」与「缓存命中」两条路径
            os.remove(html_path)
        resp = await client.get(
            _export_url(task_id),
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"format": "html"},
        )
        assert resp.status_code == 200, f"第 {i + 1} 次导出失败: {resp.text}"
        assert resp.text, f"第 {i + 1} 次导出响应体为空"
        assert "<html" in resp.text, f"第 {i + 1} 次导出缺少 <html"


# =========================================================================== #
# ③ 回归：真实并发重写循环（不引入人为延迟）下导出始终非空
# =========================================================================== #
@pytest.mark.asyncio
async def test_export_html_concurrent_rewrite_loop(
    client: AsyncClient,
    admin_token: str,
    test_db: AsyncSession,
    sample_device: Device,
    sample_item: TestItem,
    mock_adb,
):
    task_id = await _create_completed_task(
        client, admin_token, sample_device, sample_item, mock_adb
    )
    assert await _wait_report_cache_ready(test_db, task_id), "后台报告缓存未就绪"
    html_path = _report_html_path(task_id)

    for i in range(20):
        content = open(html_path, "rb").read()
        writer = asyncio.create_task(
            asyncio.to_thread(reports_module._write_report_file, html_path, content)
        )
        try:
            resp = await client.get(
                _export_url(task_id),
                headers={"Authorization": f"Bearer {admin_token}"},
                params={"format": "html"},
            )
            assert resp.status_code == 200, f"第 {i + 1} 轮导出失败: {resp.text}"
            assert resp.text, f"第 {i + 1} 轮导出响应体为空"
            assert "<html" in resp.text, f"第 {i + 1} 轮导出缺少 <html>"
        finally:
            await writer
