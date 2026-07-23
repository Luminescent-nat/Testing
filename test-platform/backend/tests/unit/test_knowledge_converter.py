"""知识库转测试资产服务单元测试。"""
import pytest

from app.services.knowledge_converter import KnowledgeConverter
from app.models import TestItem, FailurePattern, Baseline


@pytest.fixture
def converter():
    """无 LLM 的转换器，用于测试纯数据转换逻辑。"""
    return KnowledgeConverter(client=None)


@pytest.mark.asyncio
async def test_convert_test_item_creates_module_and_item(converter, test_db, admin_user):
    """document/test_case 类型应能创建模块和测试项。"""
    preview_data = {
        "module_name": "EMMC",
        "module_category": "storage",
        "name": "EMMC 顺序读带宽",
        "objective": "验证 EMMC 顺序读带宽",
        "precondition": "设备已 root",
        "steps": "fio --name=seqread --rw=read --bs=128k --size=1G",
        "expected_result": "带宽大于 100 MB/s",
        "exec_type": "adb_shell",
        "exec_command": "fio --name=seqread --rw=read --bs=128k --size=1G",
        "judgement_type": "assertion",
        "conditional_rules": [{"operator": "gt", "metric": "bw_mbps", "expected": 100}],
        "timeout": 600,
        "tags": ["performance", "emmc"]
    }

    from app.models import KnowledgeEntry
    entry = KnowledgeEntry(title="EMMC 规范", entry_type="document", content="test")

    result = await converter.convert(
        db=test_db,
        entry=entry,
        target_type="test_item",
        preview_data=preview_data,
        current_user_id=admin_user.id
    )

    assert result["asset_type"] == "test_item"
    assert result["module_name"] == "EMMC"
    assert result["item_name"] == "EMMC 顺序读带宽"
    assert result["module_id"] > 0
    assert result["item_id"] > 0

    # 数据库验证
    item = await test_db.get(TestItem, result["item_id"])
    assert item is not None
    assert item.exec_type == "adb_shell"
    assert item.judgement_type == "assertion"


@pytest.mark.asyncio
async def test_convert_failure_pattern(converter, test_db, admin_user):
    """failure_pattern 类型应创建 FailurePattern 记录。"""
    preview_data = {
        "name": "ADB 设备离线",
        "category": "adb",
        "pattern": "device.*offline|no devices",
        "description": "ADB 连接断开",
        "suggested_fix": "重新插拔 USB 或 adb reconnect"
    }

    from app.models import KnowledgeEntry
    entry = KnowledgeEntry(title="ADB 错误", entry_type="document", content="test")

    result = await converter.convert(
        db=test_db,
        entry=entry,
        target_type="failure_pattern",
        preview_data=preview_data,
        current_user_id=admin_user.id
    )

    assert result["asset_type"] == "failure_pattern"
    assert result["name"] == "ADB 设备离线"

    pattern = await test_db.get(FailurePattern, result["pattern_id"])
    assert pattern is not None
    assert pattern.category == "adb"


@pytest.mark.asyncio
async def test_convert_baseline(converter, test_db):
    """baseline 类型应创建 Baseline 记录。"""
    preview_data = {
        "device_model": "rk3568",
        "item_name": "EMMC 顺序读带宽",
        "metric_name": "bw_read_mbps",
        "avg_value": "240",
        "min_value": "200",
        "max_value": "280",
        "sample_count": 10
    }

    from app.models import KnowledgeEntry
    entry = KnowledgeEntry(title="基线", entry_type="baseline", content="test")

    result = await converter.convert(
        db=test_db,
        entry=entry,
        target_type="baseline",
        preview_data=preview_data,
        current_user_id=1
    )

    assert result["asset_type"] == "baseline"
    assert result["device_model"] == "rk3568"

    baseline = await test_db.get(Baseline, result["baseline_id"])
    assert baseline is not None
    assert baseline.metric_name == "bw_read_mbps"


@pytest.mark.asyncio
async def test_convert_unknown_type_raises(converter, test_db):
    """未知目标类型应抛 ValueError。"""
    from app.models import KnowledgeEntry
    entry = KnowledgeEntry(title="test", entry_type="document", content="test")

    with pytest.raises(ValueError):
        await converter.convert(
            db=test_db,
            entry=entry,
            target_type="unknown",
            preview_data={},
            current_user_id=1
        )
