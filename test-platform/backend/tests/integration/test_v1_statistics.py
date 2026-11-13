"""V1-06 统一统计 / 进度 / result 口径集成测试（T-08）。

覆盖 verification-rules §4 的 STAT-01/02/03、DASH-01、ZERO-01，并补充
skip+pass、零记录、pending、cancelled、平台 failed 真值表；同时核对
任务详情 / WebSocket / 报告三处口径一致。

权威口径：docs/design/execution-state-machine.md §3/§5/§6。
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, TestItem, TestModule, TestRecord, TestTask, User
from app.services import statistics
from app.websocket import build_progress_message

FINAL = ("pass", "fail", "skip", "error", "timeout")


async def _seed_task(
    db: AsyncSession,
    user: User,
    device: Device,
    statuses,
    *,
    status: str = "completed",
    name: str = "stat-task",
    specs=None,
):
    """直接落库一个任务与对应测试记录。

    statuses: 每条记录的状态序列（顺序即 selected_items 顺序）。
    specs: 与 statuses 等长的 dict 列表，可含 name/execution_time/extracted_data/fail_reason。
    """
    module = TestModule(
        name=f"StatModule-{uuid.uuid4().hex[:8]}", category="stat", created_by=user.id
    )
    db.add(module)
    await db.flush()

    items = []
    for i, _ in enumerate(statuses):
        spec = specs[i] if specs else {}
        item = TestItem(
            module_id=module.id,
            name=spec.get("name", f"Item-{i}"),
            exec_type="adb_shell",
            exec_command="echo ok",
            created_by=user.id,
        )
        db.add(item)
        await db.flush()
        items.append(item)

    task = TestTask(
        user_id=user.id,
        device_id=device.id,
        name=name,
        selected_items=[it.id for it in items],
        status=status,
        progress_percent=0,
    )
    if status in ("completed", "failed", "cancelled"):
        task.completed_at = datetime.now(timezone.utc)
    db.add(task)
    await db.flush()

    for i, (item, st) in enumerate(zip(items, statuses)):
        spec = specs[i] if specs else {}
        db.add(
            TestRecord(
                task_id=task.id,
                item_id=item.id,
                status=st,
                execution_time=spec.get("execution_time"),
                extracted_data=spec.get("extracted_data"),
                fail_reason=spec.get("fail_reason"),
                completed_at=(
                    datetime.now(timezone.utc) if st in FINAL else None
                ),
            )
        )
    await db.commit()
    await db.refresh(task)
    return task, items


async def _get_detail(client: AsyncClient, token: str, task_id: int) -> dict:
    resp = await client.get(
        f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _get_report(client: AsyncClient, token: str, task_id: int) -> dict:
    resp = await client.get(
        f"/api/v1/reports/{task_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# =========================================================================== #
# STAT-01：pass2/fail1/timeout1/skip2 → C=6、progress=100、pass_rate=50.0
# 并核对详情 / WS / 报告三处一致
# =========================================================================== #
@pytest.mark.asyncio
async def test_stat01_pass2_fail1_timeout1_skip2_consistent(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
    test_db: AsyncSession,
    sample_device: Device,
):
    statuses = ["pass", "pass", "fail", "timeout", "skip", "skip"]
    task, _items = await _seed_task(
        test_db, admin_user, sample_device, statuses, status="completed", name="STAT-01"
    )

    detail = await _get_detail(client, admin_token, task.id)
    assert detail["status"] == "completed"
    assert detail["result"] == "failed"
    assert detail["total_items"] == 6
    assert detail["completed_items"] == 6
    assert detail["progress_percent"] == 100
    assert detail["pass_rate"] == 50.0
    assert detail["counts"] == {
        "pass": 2, "fail": 1, "skip": 2, "error": 0, "timeout": 1,
    }

    ws = await build_progress_message(task.id)
    ws_data = ws["data"]
    assert ws_data["task_status"] == "completed"
    assert ws_data["result"] == "failed"
    assert ws_data["completed_items"] == 6
    assert ws_data["total_items"] == 6
    assert ws_data["progress_percent"] == 100
    assert ws_data["pass_rate"] == 50.0
    assert ws_data["counts"] == {
        "pass": 2, "fail": 1, "skip": 2, "error": 0, "timeout": 1,
    }

    report = await _get_report(client, admin_token, task.id)
    summary = report["summary"]
    assert summary["total_items"] == 6
    assert summary["passed"] == 2
    assert summary["failed"] == 2  # fail + timeout（展示口径）
    assert summary["skipped"] == 2
    assert summary["error"] == 0
    assert summary["timeout"] == 1
    assert summary["pass_rate"] == 50.0
    assert report["task_result"] == "failed"
    assert report["task_status"] == "completed"
    assert summary["counts"] == {
        "pass": 2, "fail": 1, "skip": 2, "error": 0, "timeout": 1,
    }

    # 三处口径一致
    assert detail["pass_rate"] == ws_data["pass_rate"] == summary["pass_rate"] == 50.0
    assert detail["counts"] == ws_data["counts"] == summary["counts"]


# =========================================================================== #
# STAT-02：全 skip → completed/result=null、pass_rate=null（不是 0 也不是 "0%"）
# =========================================================================== #
@pytest.mark.asyncio
async def test_stat02_all_skip_result_and_pass_rate_null(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
    test_db: AsyncSession,
    sample_device: Device,
):
    task, _ = await _seed_task(
        test_db, admin_user, sample_device, ["skip", "skip", "skip"],
        status="completed", name="STAT-02",
    )

    detail = await _get_detail(client, admin_token, task.id)
    assert detail["status"] == "completed"
    assert detail["result"] is None
    assert detail["completed_items"] == 3
    assert detail["progress_percent"] == 100
    assert detail["pass_rate"] is None

    ws_data = (await build_progress_message(task.id))["data"]
    assert ws_data["result"] is None
    assert ws_data["pass_rate"] is None
    assert ws_data["completed_items"] == 3

    report = await _get_report(client, admin_token, task.id)
    assert report["summary"]["pass_rate"] is None
    assert report["task_result"] is None
    # 明确不是字符串 0%
    assert report["summary"]["pass_rate"] != "0%"
    assert report["summary"]["total_items"] == 3
    assert report["summary"]["skipped"] == 3


# =========================================================================== #
# STAT-03：一项 running，其余 pass → running 不计完成、任务不得 completed
# =========================================================================== #
@pytest.mark.asyncio
async def test_stat03_running_not_counted_task_not_completed(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
    test_db: AsyncSession,
    sample_device: Device,
):
    task, _ = await _seed_task(
        test_db, admin_user, sample_device, ["pass", "pass", "pass", "running"],
        status="running", name="STAT-03",
    )

    detail = await _get_detail(client, admin_token, task.id)
    assert detail["status"] == "running"
    assert detail["status"] != "completed"
    assert detail["result"] is None
    assert detail["completed_items"] == 3  # running 不计入
    assert detail["total_items"] == 4
    assert detail["progress_percent"] == 75  # floor(3/4*100)
    assert detail["counts"] == {
        "pass": 3, "fail": 0, "skip": 0, "error": 0, "timeout": 0,
    }

    ws_data = (await build_progress_message(task.id))["data"]
    assert ws_data["task_status"] == "running"
    assert ws_data["completed_items"] == 3
    assert ws_data["result"] is None
    assert ws_data["pass_rate"] == 100.0  # 分母仅 pass（running 不计入）


# =========================================================================== #
# 补充真值表：skip+pass、零记录、pending、cancelled、平台 failed
# =========================================================================== #
@pytest.mark.asyncio
async def test_truth_table_skip_pass_zero_pending_cancelled_platform_failed(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
    test_db: AsyncSession,
    sample_device: Device,
):
    # skip+pass：completed，有 pass → passed，pass_rate=100（skip 不进分母）
    t_skip_pass, _ = await _seed_task(
        test_db, admin_user, sample_device, ["pass", "skip"],
        status="completed", name="skip+pass",
    )
    d = await _get_detail(client, admin_token, t_skip_pass.id)
    assert d["result"] == "passed"
    assert d["completed_items"] == 2
    assert d["counts"]["pass"] == 1 and d["counts"]["skip"] == 1
    assert d["pass_rate"] == 100.0

    # 零记录：completed 但 N=0 → result null、pass_rate null、progress 0
    t_zero, _ = await _seed_task(
        test_db, admin_user, sample_device, [], status="completed", name="zero"
    )
    d = await _get_detail(client, admin_token, t_zero.id)
    assert d["result"] is None
    assert d["completed_items"] == 0
    assert d["progress_percent"] == 0
    assert d["pass_rate"] is None

    # pending：无记录 → result null
    t_pending, _ = await _seed_task(
        test_db, admin_user, sample_device, [], status="pending", name="pending"
    )
    d = await _get_detail(client, admin_token, t_pending.id)
    assert d["status"] == "pending"
    assert d["result"] is None
    assert d["pass_rate"] is None

    # cancelled：即便有 pass 记录，任务 cancelled → result null
    t_cancelled, _ = await _seed_task(
        test_db, admin_user, sample_device, ["pass"], status="cancelled", name="cancelled"
    )
    d = await _get_detail(client, admin_token, t_cancelled.id)
    assert d["status"] == "cancelled"
    assert d["result"] is None

    # 平台 failed：有 error 记录，但任务 status=failed → 不得出现业务 passed/failed
    t_platform, _ = await _seed_task(
        test_db, admin_user, sample_device, ["error"], status="failed", name="platform-failed"
    )
    d = await _get_detail(client, admin_token, t_platform.id)
    assert d["status"] == "failed"
    assert d["result"] is None


# =========================================================================== #
# DASH-01：passed/failed/全skip/running/平台failed/cancelled/零记录 混合
# =========================================================================== #
@pytest.mark.asyncio
async def test_dash01_mixed_outcomes_only_valid_completed_in_rate(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
    test_db: AsyncSession,
    sample_device: Device,
):
    await _seed_task(test_db, admin_user, sample_device, ["pass"], name="dash-pass")
    await _seed_task(test_db, admin_user, sample_device, ["fail"], name="dash-fail")
    await _seed_task(
        test_db, admin_user, sample_device, ["skip", "skip"], name="dash-all-skip"
    )
    await _seed_task(
        test_db, admin_user, sample_device, ["pass", "running"],
        status="running", name="dash-running",
    )
    await _seed_task(
        test_db, admin_user, sample_device, ["error"], status="failed",
        name="dash-platform-failed",
    )
    await _seed_task(
        test_db, admin_user, sample_device, ["pass"], status="cancelled",
        name="dash-cancelled",
    )
    # 零记录 completed
    await _seed_task(test_db, admin_user, sample_device, [], name="dash-zero-record")

    resp = await client.get(
        "/api/v1/dashboard/stats", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    today = data["today"]
    # reporting-v1.0 §5：today 直接含完整分列（保留既有兼容键）
    assert set(today.keys()) == {
        "tasks", "passed", "failed", "pass_rate",
        "completed", "no_result", "execution_failed", "cancelled", "running", "pending",
    }
    # 仅 completed 且 result∈(passed,failed) 进入分母：passed1 + failed1 → 50.0
    assert today["tasks"] == 7
    assert today["completed"] == 4  # passed1 + failed1 + no_result2
    assert today["passed"] == 1
    assert today["failed"] == 1
    assert today["no_result"] == 2  # 全 skip + 零记录
    assert today["execution_failed"] == 1  # 平台 failed
    assert today["cancelled"] == 1
    assert today["running"] == 1
    assert today["pending"] == 0
    assert today["pass_rate"] == 50.0

    # today 内各分列之和 = 今日任务总数（每个任务只归一类）
    assert (
        today["passed"] + today["failed"] + today["no_result"]
        + today["execution_failed"] + today["cancelled"]
        + today["running"] + today["pending"]
    ) == today["tasks"]

    outcomes = data["task_outcomes"]
    assert outcomes["passed"] == 1
    assert outcomes["failed"] == 1
    assert outcomes["no_result"] == 2  # 全 skip + 零记录
    assert outcomes["execution_failed"] == 1  # 平台 failed
    assert outcomes["cancelled"] == 1
    assert outcomes["running"] == 1
    assert outcomes["pending"] == 0
    # today 分列与 task_outcomes 同源同值
    for key in ("passed", "failed", "no_result", "execution_failed", "cancelled", "running", "pending"):
        assert today[key] == outcomes[key]

    # 分列计数之和 = 今日任务总数，且非 passed/failed 不进入分母
    assert sum(outcomes.values()) == today["tasks"]
    assert data["running_tasks"] >= 1
    assert "pending_tasks" in data


@pytest.mark.asyncio
async def test_dash01_zero_records_pass_rate_null(
    client: AsyncClient, admin_token: str
):
    """零任务：分母 0 → pass_rate 为 null。"""
    resp = await client.get(
        "/api/v1/dashboard/stats", headers={"Authorization": f"Bearer {admin_token}"}
    )
    data = resp.json()["data"]
    today = data["today"]
    assert set(today.keys()) == {
        "tasks", "passed", "failed", "pass_rate",
        "completed", "no_result", "execution_failed", "cancelled", "running", "pending",
    }
    assert today["tasks"] == 0
    assert today["completed"] == 0
    assert today["passed"] == 0
    assert today["failed"] == 0
    assert today["no_result"] == 0
    assert today["execution_failed"] == 0
    assert today["cancelled"] == 0
    assert today["running"] == 0
    assert today["pending"] == 0
    assert today["pass_rate"] is None


# =========================================================================== #
# ZERO-01：耗时 0、提取值 0、无对应项、重名不同 ID
# =========================================================================== #
@pytest.mark.asyncio
async def test_zero01_zero_values_item_id_alignment_and_missing_metric(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
    test_db: AsyncSession,
    sample_device: Device,
):
    specs = [
        {
            "name": "性能测试A",
            "execution_time": 0,
            "extracted_data": {"bw_mbps": 0, "iops": 0, "max_iops": None},
        },
        {
            "name": "性能测试A",  # 重名，不同 item_id
            "execution_time": 0,
            "extracted_data": {"bw_mbps": 5, "iops": 0},
        },
    ]
    task, items = await _seed_task(
        test_db, admin_user, sample_device, ["pass", "pass"],
        status="completed", name="ZERO-01", specs=specs,
    )

    report = await _get_report(client, admin_token, task.id)
    results = report["results"]
    perf_entries = [r for r in results if r["item_name"] == "性能测试A"]
    assert len(perf_entries) == 2  # 重名不合并
    assert len({r["item_id"] for r in perf_entries}) == 2  # 按 item_id 区分

    # 耗时 0 保留为 0（不得变为 None/缺失）
    for entry in perf_entries:
        assert entry["execution_time"] == 0
    # 提取值 0 保留为 0
    assert perf_entries[0]["extracted_data"]["bw_mbps"] == 0
    assert perf_entries[0]["extracted_data"]["iops"] == 0
    assert perf_entries[1]["extracted_data"]["bw_mbps"] == 5

    # 展示层：0 显示为 0，缺失值显示为 "-"，不得把 0 显示为 "-"
    from app.api.reports import _extract_perf_results, _generate_markdown, _fmt_metric

    perf = _extract_perf_results(results)
    assert len(perf) == 2
    by_name = perf[0]
    assert by_name["bw_mbps"] == 0 and by_name["iops"] == 0
    assert by_name["max_iops"] is None  # 无对应项
    assert _fmt_metric(0) == "0"
    assert _fmt_metric(None) == "-"

    markdown = _generate_markdown(report)
    # 性能表格行应保留真实零值（只取表格行，排除下方测试卡标题）
    perf_lines = [
        ln for ln in markdown.splitlines()
        if ln.startswith("| ") and "性能测试A" in ln and "| pass |" in ln
    ]
    assert len(perf_lines) == 2
    first_cells = [c.strip() for c in perf_lines[0].split("|")]
    # | 测试项 | 状态 | 带宽 | IOPS | MAX IOPS | ...
    assert first_cells[3] == "0"  # bw_mbps 0
    assert first_cells[4] == "0"  # iops 0
    assert first_cells[5] == "-"  # max_iops 缺失 → 不可对比占位

    # Excel 导出可生成且不因零值报错
    from app.api.reports import _generate_excel

    assert len(_generate_excel(report)) > 0


# =========================================================================== #
# 契约补充：Device 数据对象含 version: integer（device-authorization §2，从 1 开始）
# =========================================================================== #
@pytest.mark.asyncio
async def test_device_response_includes_version(
    client: AsyncClient, admin_token: str, sample_device: Device
):
    resp = await client.get(
        "/api/v1/devices", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    target = next(i for i in items if i["serial_number"] == sample_device.serial_number)
    assert target["version"] == 1


def test_statistics_module_single_source_of_truth():
    stats = statistics.compute_task_statistics(
        "completed", 6, ["pass", "pass", "fail", "timeout", "skip", "skip"]
    )
    assert stats["completed_items"] == 6
    assert stats["progress_percent"] == 100
    assert stats["pass_rate"] == 50.0
    assert stats["result"] == "failed"

    # 全 skip：completed 但 result null、pass_rate null
    stats = statistics.compute_task_statistics("completed", 2, ["skip", "skip"])
    assert stats["result"] is None
    assert stats["pass_rate"] is None
    assert stats["progress_percent"] == 100

    # 非 completed 一律 result null
    for status in ("pending", "running", "failed", "cancelled"):
        assert statistics.compute_task_statistics(status, 2, ["pass", "pass"])["result"] is None

    # 通过率分母 0 → None
    assert statistics.compute_pass_rate({"pass": 0, "fail": 0, "error": 0, "timeout": 0, "skip": 5}) is None
    # skip 不进分母
    assert statistics.compute_pass_rate({"pass": 1, "fail": 1, "error": 0, "timeout": 0, "skip": 9}) == 50.0


# =========================================================================== #
# 空报告汇总空态（T-25 演示问题 2）：空库 200 空汇总，前端消费字段兼容
# =========================================================================== #
@pytest.mark.asyncio
async def test_summary_all_empty_state_frontend_consumer_fields(
    client: AsyncClient, admin_token: str
):
    """空库 summary/all：200 空汇总；counts/pass_rate/result 消费字段语义安全。"""
    resp = await client.get(
        "/api/v1/reports/summary/all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # 五类计数全 0（形状与统计口径一致），pass_rate=null，不得为 0/"0%"
    summary = data["summary"]
    assert summary["counts"] == {s: 0 for s in FINAL}
    assert summary["pass_rate"] is None
    assert summary["pass_rate"] != 0
    assert summary["total_items"] == 0

    # 任务/结果空数组：前端遍历不会取到 undefined；result 语义为“无结果”
    assert data["tasks"] == []
    assert data["results"] == []
    assert data["task_count"] == 0
    # 非空复用同一 batch 结构（report_type/version 一致）
    assert data["report_type"] == "batch"
    assert data["report_version"] == "1.1"
