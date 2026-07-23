"""记忆体服务单元测试。"""
import pytest
from sqlalchemy import select

from app.models import Baseline, FailurePattern, GoldenCase, TestRecord
from app.services.memory_engine import (
    BaselineService,
    FailurePatternService,
    GoldenCaseService,
)


@pytest.mark.asyncio
async def test_seed_default_patterns(test_db):
    """默认失败模式种子数据。"""
    await FailurePatternService.seed_default_patterns(test_db, user_id=1)
    result = await test_db.execute(select(FailurePattern))
    patterns = result.scalars().all()
    assert len(patterns) == len(FailurePatternService.DEFAULT_PATTERNS)


@pytest.mark.asyncio
async def test_match_record_increments_count(test_db):
    await FailurePatternService.seed_default_patterns(test_db, user_id=1)
    record = TestRecord(
        task_id=1,
        item_id=1,
        status="fail",
        output="error: device offline",
        fail_reason="device offline",
    )
    test_db.add(record)
    await test_db.commit()

    matches = await FailurePatternService.match_record(test_db, record)
    assert len(matches) >= 1
    assert any(m["name"] == "ADB 设备离线" for m in matches)

    # 计数增加
    result = await test_db.execute(
        select(FailurePattern).where(FailurePattern.name == "ADB 设备离线")
    )
    pattern = result.scalar_one()
    assert pattern.occurrence_count >= 1


@pytest.mark.asyncio
async def test_baseline_create_on_pass(test_db):
    record = TestRecord(
        task_id=1,
        item_id=1,
        status="pass",
        extracted_data={"bw_mbps": 200},
    )
    test_db.add(record)
    await test_db.commit()

    await BaselineService.update_from_record(test_db, record, "rk3568")

    result = await test_db.execute(select(Baseline))
    baseline = result.scalar_one()
    assert baseline.device_model == "rk3568"
    assert baseline.metric_name == "bw_mbps"
    assert float(baseline.avg_value) == 200.0
    assert baseline.sample_count == 1


@pytest.mark.asyncio
async def test_baseline_update_avg_min_max(test_db):
    record1 = TestRecord(
        task_id=1,
        item_id=1,
        status="pass",
        extracted_data={"bw_mbps": 100},
    )
    record2 = TestRecord(
        task_id=2,
        item_id=1,
        status="pass",
        extracted_data={"bw_mbps": 200},
    )
    test_db.add_all([record1, record2])
    await test_db.commit()

    await BaselineService.update_from_record(test_db, record1, "rk3568")
    await BaselineService.update_from_record(test_db, record2, "rk3568")

    result = await test_db.execute(select(Baseline))
    baseline = result.scalar_one()
    assert float(baseline.avg_value) == 150.0
    assert float(baseline.min_value) == 100.0
    assert float(baseline.max_value) == 200.0
    assert baseline.sample_count == 2


@pytest.mark.asyncio
async def test_golden_case_create_on_pass(test_db):
    record = TestRecord(
        task_id=1,
        item_id=1,
        status="pass",
        output="expected output",
    )
    test_db.add(record)
    await test_db.commit()

    await GoldenCaseService.update_from_record(test_db, record, "rk3568")

    result = await test_db.execute(select(GoldenCase))
    case = result.scalar_one()
    assert case.device_model == "rk3568"
    assert case.item_id == 1
    assert case.pass_count == 1


@pytest.mark.asyncio
async def test_golden_case_skip_fail_record(test_db):
    record = TestRecord(
        task_id=1,
        item_id=1,
        status="fail",
        output="error",
    )
    test_db.add(record)
    await test_db.commit()

    await GoldenCaseService.update_from_record(test_db, record, "rk3568")

    result = await test_db.execute(select(GoldenCase))
    assert result.scalar_one_or_none() is None
