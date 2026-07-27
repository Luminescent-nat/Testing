"""test-tools 插件化注册：扫描 TEST_TOOLS_PATH 下各模块目录的 manifest.yaml，
将测试模块（TestModule）与测试项（TestItem）幂等写入数据库。

manifest 格式见 test-tools/emmc/manifest.yaml：
- module: name/category/description；
- items: 字段名对齐 TestItem 列，host_exec 命令用 {host_tool_dir} 占位（不写绝对路径）。

与 seed_data 的共存约定（两边判重键完全一致，不会互相产生重复数据）：
- 模块判重键：模块名（TestModule.name）；
- 测试项判重键：(module_id, 测试项名 TestItem.name)；
- seed_data 仅在启动时对缺失数据“不存在才创建”，不更新已有行；
- 本服务对 manifest 声明的数据做 upsert：不存在则创建，存在则按 manifest 更新字段。
"""

import glob
import logging
import os
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import TestItem, TestModule, User

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.yaml"

VALID_EXEC_TYPES = {"adb_shell", "push_exec", "host_exec"}

# manifest 测试项允许写入的 TestItem 字段及默认值（未提供的字段按默认值落库）
ITEM_FIELD_DEFAULTS = {
    "description": None,
    "objective": None,
    "precondition": None,
    "steps": None,
    "expected_result": None,
    "sort_order": 0,
    "enabled": True,
    "parameters": dict,
    "parameters_schema": None,
    "compatibility": dict,
    "judgement_type": "assertion",
    "conditional_rules": None,
    "rubric_criteria": None,
    "result_parse": dict,
    "timeout": 300,
    "on_failure": "continue",
    "retry_count": 0,
    "tags": list,
}


def _default_value(default):
    """字段默认值：dict/list 类型表示调用其构造空容器，避免共享可变默认值。"""
    return default() if callable(default) else default


def _load_manifest(path: str) -> dict:
    """读取并校验单个 manifest.yaml，返回规范化后的 {module, items}。

    结构非法时抛出 ValueError，由调用方记入 errors。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("manifest 顶层必须是 YAML 对象")
    module = data.get("module")
    if not isinstance(module, dict) or not module.get("name"):
        raise ValueError("manifest 缺少 module.name")
    items = data.get("items") or []
    if not isinstance(items, list):
        raise ValueError("manifest items 必须是列表")
    return {"module": module, "items": items}


async def _upsert_module(db: AsyncSession, meta: dict, created_by: int) -> TestModule:
    """按模块名 upsert TestModule（存在则更新 category/description）。"""
    result = await db.execute(select(TestModule).where(TestModule.name == meta["name"]))
    module = result.scalar_one_or_none()
    if module:
        if meta.get("category") is not None:
            module.category = meta["category"]
        if meta.get("description") is not None:
            module.description = meta["description"]
    else:
        module = TestModule(
            name=meta["name"],
            category=meta.get("category"),
            description=meta.get("description"),
            created_by=created_by,
        )
        db.add(module)
        await db.flush()
        logger.info("manifest 注册测试模块: %s", module.name)
    return module


async def _upsert_item(
    db: AsyncSession, module: TestModule, data: dict, created_by: int
) -> str:
    """按 (module_id, name) upsert TestItem，返回 'created' 或 'updated'。"""
    row = {field: _default_value(default) for field, default in ITEM_FIELD_DEFAULTS.items()}
    for field in ITEM_FIELD_DEFAULTS:
        if field in data:
            row[field] = data[field]

    result = await db.execute(
        select(TestItem).where(
            TestItem.module_id == module.id,
            TestItem.name == data["name"],
        )
    )
    item = result.scalar_one_or_none()
    if item:
        for field, value in row.items():
            setattr(item, field, value)
        item.exec_type = data["exec_type"]
        item.exec_command = data["exec_command"]
        return "updated"

    item = TestItem(
        module_id=module.id,
        name=data["name"],
        exec_type=data["exec_type"],
        exec_command=data["exec_command"],
        created_by=created_by,
        **row,
    )
    db.add(item)
    await db.flush()
    return "created"


async def scan_and_register(db: AsyncSession, tools_root: Optional[str] = None) -> dict:
    """扫描 tools_root（默认配置 TEST_TOOLS_PATH）下所有 */manifest.yaml 并注册入库。

    单个 manifest 解析/校验失败只记入 errors，不中断整体扫描；
    测试项粒度缺少必填字段（name/exec_type/exec_command）同样只记 errors 跳过该条。
    幂等：重复执行不产生重复数据，已有测试项按 manifest 更新字段。

    返回 {"modules": [{"name", "created_items", "updated_items"}], "errors": [...]}。
    """
    settings = get_settings()
    root = tools_root or settings.TEST_TOOLS_PATH
    pattern = os.path.join(root, "*", MANIFEST_FILENAME)
    manifest_paths = sorted(glob.glob(pattern))

    result = {"modules": [], "errors": []}
    if not manifest_paths:
        logger.warning("未在 %s 下发现任何 %s", root, MANIFEST_FILENAME)

    user = (await db.execute(select(User).order_by(User.id))).scalars().first()
    created_by = user.id if user else 1

    for path in manifest_paths:
        try:
            manifest = _load_manifest(path)
        except (OSError, yaml.YAMLError, ValueError) as exc:
            error = f"{path}: {exc}"
            logger.error("manifest 解析失败: %s", error)
            result["errors"].append(error)
            continue

        module = await _upsert_module(db, manifest["module"], created_by)
        created_items = updated_items = 0
        for data in manifest["items"]:
            if not isinstance(data, dict) or not all(
                data.get(k) for k in ("name", "exec_type", "exec_command")
            ):
                result["errors"].append(
                    f"{path}: 测试项缺少必填字段 name/exec_type/exec_command（{data!r}）"
                )
                continue
            if data["exec_type"] not in VALID_EXEC_TYPES:
                result["errors"].append(
                    f"{path}: 测试项 {data['name']} exec_type 非法: {data['exec_type']}"
                )
                continue
            outcome = await _upsert_item(db, module, data, created_by)
            if outcome == "created":
                created_items += 1
            else:
                updated_items += 1

        await db.commit()
        result["modules"].append(
            {
                "name": module.name,
                "created_items": created_items,
                "updated_items": updated_items,
            }
        )
        logger.info(
            "manifest 注册完成: %s（新建 %d，更新 %d）",
            module.name, created_items, updated_items,
        )

    return result
