"""tool_registry manifest 扫描注册集成测试：入库、幂等更新、容错。"""
import pytest
import yaml
from sqlalchemy import func, select

from app.models import TestItem, TestModule
from app.services import tool_registry

pytestmark = pytest.mark.asyncio


def _write_manifest(root, module_dir, manifest):
    module_path = root / module_dir
    module_path.mkdir(parents=True, exist_ok=True)
    with open(module_path / "manifest.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, allow_unicode=True)


def _demo_manifest(name, items):
    return {
        "module": {"name": name, "category": "storage", "description": f"{name} 模块"},
        "items": items,
    }


def _demo_item(name, timeout=60, exec_command="echo {serial}"):
    return {
        "name": name,
        "description": f"{name} 描述",
        "exec_type": "adb_shell",
        "exec_command": exec_command,
        "parameters": {},
        "compatibility": {},
        "judgement_type": "assertion",
        "result_parse": {"pass_pattern": "ok"},
        "timeout": timeout,
        "tags": ["functional"],
        "sort_order": 1,
    }


async def test_scan_registers_modules_and_items(test_db, tmp_path):
    """两个 manifest → 两个模块、各自测试项入库，字段按 manifest 落库。"""
    _write_manifest(tmp_path, "emmc", _demo_manifest(
        "EMMC", [_demo_item("节点检测", timeout=120), _demo_item("顺序读性能")]
    ))
    _write_manifest(tmp_path, "upfm", _demo_manifest("UPFM", [_demo_item("T1-01 ping")]))

    result = await tool_registry.scan_and_register(test_db, tools_root=str(tmp_path))

    assert result["errors"] == []
    assert {m["name"] for m in result["modules"]} == {"EMMC", "UPFM"}
    for m in result["modules"]:
        expected = 2 if m["name"] == "EMMC" else 1
        assert m["created_items"] == expected
        assert m["updated_items"] == 0

    module = (await test_db.execute(
        select(TestModule).where(TestModule.name == "EMMC")
    )).scalar_one()
    assert module.category == "storage"
    items = (await test_db.execute(
        select(TestItem).where(TestItem.module_id == module.id)
    )).scalars().all()
    assert len(items) == 2
    by_name = {i.name: i for i in items}
    assert by_name["节点检测"].timeout == 120
    assert by_name["节点检测"].result_parse == {"pass_pattern": "ok"}
    # 未提供的字段按默认值落库
    assert by_name["顺序读性能"].judgement_type == "assertion"
    assert by_name["顺序读性能"].on_failure == "continue"


async def test_scan_is_idempotent_and_updates_fields(test_db, tmp_path):
    """重复扫描不产生重复数据；manifest 字段变更会更新已有测试项。"""
    _write_manifest(tmp_path, "emmc", _demo_manifest(
        "EMMC", [_demo_item("节点检测", timeout=120)]
    ))
    first = await tool_registry.scan_and_register(test_db, tools_root=str(tmp_path))
    assert first["modules"][0]["created_items"] == 1

    item_count = (await test_db.execute(
        select(func.count()).select_from(TestItem)
    )).scalar_one()
    module_count = (await test_db.execute(
        select(func.count()).select_from(TestModule)
    )).scalar_one()

    # 修改 timeout 与描述后重扫：应更新而非新建
    _write_manifest(tmp_path, "emmc", _demo_manifest(
        "EMMC", [{**_demo_item("节点检测", timeout=999), "description": "更新后的描述"}]
    ))
    second = await tool_registry.scan_and_register(test_db, tools_root=str(tmp_path))
    assert second["errors"] == []
    assert second["modules"][0]["created_items"] == 0
    assert second["modules"][0]["updated_items"] == 1

    assert (await test_db.execute(
        select(func.count()).select_from(TestItem)
    )).scalar_one() == item_count
    assert (await test_db.execute(
        select(func.count()).select_from(TestModule)
    )).scalar_one() == module_count

    item = (await test_db.execute(select(TestItem))).scalar_one()
    assert item.timeout == 999
    assert item.description == "更新后的描述"


async def test_scan_coexists_with_seed_style_data(test_db, tmp_path):
    """与 seed_data 判重键一致：已存在的同名模块/测试项只更新、不重复创建。"""
    module = TestModule(name="EMMC", category="storage", description="seed 创建")
    test_db.add(module)
    await test_db.flush()
    test_db.add(TestItem(
        module_id=module.id, name="节点检测", exec_type="adb_shell",
        exec_command="old command", parameters={}, compatibility={},
        result_parse={}, timeout=300,
    ))
    await test_db.commit()

    _write_manifest(tmp_path, "emmc", _demo_manifest(
        "EMMC", [_demo_item("节点检测", exec_command="ls /sys/block/")]
    ))
    result = await tool_registry.scan_and_register(test_db, tools_root=str(tmp_path))

    assert result["errors"] == []
    assert result["modules"][0]["created_items"] == 0
    assert result["modules"][0]["updated_items"] == 1
    assert (await test_db.execute(
        select(func.count()).select_from(TestItem)
    )).scalar_one() == 1
    item = (await test_db.execute(select(TestItem))).scalar_one()
    assert item.exec_command == "ls /sys/block/"


async def test_scan_bad_manifest_recorded_in_errors(test_db, tmp_path):
    """单个 manifest 解析失败只记入 errors，不中断其他模块注册。"""
    bad_dir = tmp_path / "broken"
    bad_dir.mkdir()
    with open(bad_dir / "manifest.yaml", "w", encoding="utf-8") as f:
        f.write("module: [not, a, valid, structure\n")
    _write_manifest(tmp_path, "upfm", _demo_manifest("UPFM", [_demo_item("T1-01 ping")]))

    result = await tool_registry.scan_and_register(test_db, tools_root=str(tmp_path))

    assert len(result["errors"]) == 1
    assert "broken" in result["errors"][0]
    assert [m["name"] for m in result["modules"]] == ["UPFM"]
    assert (await test_db.execute(
        select(func.count()).select_from(TestItem)
    )).scalar_one() == 1


async def test_scan_item_missing_required_fields_skipped(test_db, tmp_path):
    """测试项缺必填字段：该条记入 errors 跳过，其余正常注册。"""
    _write_manifest(tmp_path, "emmc", _demo_manifest("EMMC", [
        {"name": "缺命令项"},  # 缺 exec_type/exec_command
        _demo_item("正常项"),
    ]))

    result = await tool_registry.scan_and_register(test_db, tools_root=str(tmp_path))

    assert len(result["errors"]) == 1
    assert result["modules"][0]["created_items"] == 1
    names = (await test_db.execute(select(TestItem.name))).scalars().all()
    assert names == ["正常项"]


async def test_scan_modules_api_as_admin(client, admin_token, tmp_path, monkeypatch):
    """POST /tools/scan-modules：admin 触发扫描并返回结果摘要。"""
    from app.api.tools import settings as tools_settings

    _write_manifest(tmp_path, "upfm", _demo_manifest("UPFM", [_demo_item("T1-01 ping")]))
    monkeypatch.setattr(tools_settings, "TEST_TOOLS_PATH", str(tmp_path))

    response = await client.post(
        "/api/v1/tools/scan-modules",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["errors"] == []
    assert body["data"]["modules"] == [
        {"name": "UPFM", "created_items": 1, "updated_items": 0}
    ]


async def test_scan_modules_api_forbidden_for_normal_user(client, normal_token):
    """POST /tools/scan-modules：普通用户 403。"""
    response = await client.post(
        "/api/v1/tools/scan-modules",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert response.status_code == 403
