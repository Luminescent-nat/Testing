#!/usr/bin/env python3
"""将 EMMC 测试项同步到数据库（不删除已有数据）。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import TestModule, TestItem


EMMC_ITEMS = [
    {
        "name": "节点检测",
        "description": "自动识别设备主存储 eMMC 节点",
        "exec_type": "adb_shell",
        "exec_command": "ls /sys/block/ | grep mmcblk | head -5",
        "tags": ["functional"],
        "judgement_type": "assertion",
        "result_parse": {"pass_pattern": "mmcblk"},
        "timeout": 300,
    },
    {
        "name": "EXT_CSD 寄存器读取",
        "description": "通过 mmc_utils 读取 eMMC 扩展寄存器信息",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_extcsd_runner.py" --serial {serial}',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["functional"],
        "judgement_type": "assertion",
        "result_parse": {"pass_pattern": "mmc_node"},
        "timeout": 120,
    },
    {
        "name": "顺序读性能",
        "description": "fio --rw=read --bs=128k --iodepth=64 --runtime=60 --rounds=3",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_fio_runner.py" --serial {serial} --mode seq_read --runtime 60 --rounds 3',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["performance"],
        "judgement_type": "rubric",
        "rubric_criteria": {
            "bw_mbps": {
                "extract_pattern": '"bw_mbps"\\s*:\\s*([\\d.]+)',
                "source": "baseline",
                "metric": "bw_mbps",
                "operator": ">=",
                "baseline_field": "avg_value",
                "tolerance": "0%",
                "fallback_levels": [
                    {"score": 4, "threshold": 200},
                    {"score": 3, "threshold": 150},
                    {"score": 2, "threshold": 100},
                    {"score": 1},
                ],
            }
        },
        "timeout": 300,
    },
    {
        "name": "顺序写性能",
        "description": "fio --rw=write --bs=128k --iodepth=64 --runtime=60 --rounds=3",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_fio_runner.py" --serial {serial} --mode seq_write --runtime 60 --rounds 3',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["performance"],
        "judgement_type": "rubric",
        "rubric_criteria": {
            "bw_mbps": {
                "extract_pattern": '"bw_mbps"\\s*:\\s*([\\d.]+)',
                "source": "baseline",
                "metric": "bw_mbps",
                "operator": ">=",
                "baseline_field": "avg_value",
                "tolerance": "0%",
                "fallback_levels": [
                    {"score": 4, "threshold": 150},
                    {"score": 3, "threshold": 100},
                    {"score": 2, "threshold": 50},
                    {"score": 1},
                ],
            }
        },
        "timeout": 300,
    },
    {
        "name": "随机读性能",
        "description": "fio --rw=randread --bs=4k --iodepth=64 --runtime=60 --rounds=3",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_fio_runner.py" --serial {serial} --mode rand_read --runtime 60 --rounds 3',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["performance"],
        "judgement_type": "rubric",
        "rubric_criteria": {
            "iops": {
                "extract_pattern": '"iops"\\s*:\\s*([\\d.]+)',
                "source": "baseline",
                "metric": "iops",
                "operator": ">=",
                "baseline_field": "avg_value",
                "tolerance": "0%",
                "fallback_levels": [
                    {"score": 4, "threshold": 8000},
                    {"score": 3, "threshold": 5000},
                    {"score": 2, "threshold": 2000},
                    {"score": 1},
                ],
            }
        },
        "timeout": 300,
    },
    {
        "name": "随机写性能",
        "description": "fio --rw=randwrite --bs=4k --iodepth=64 --runtime=60 --rounds=3",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_fio_runner.py" --serial {serial} --mode rand_write --runtime 60 --rounds 3',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["performance"],
        "judgement_type": "rubric",
        "rubric_criteria": {
            "iops": {
                "extract_pattern": '"iops"\\s*:\\s*([\\d.]+)',
                "source": "baseline",
                "metric": "iops",
                "operator": ">=",
                "baseline_field": "avg_value",
                "tolerance": "0%",
                "fallback_levels": [
                    {"score": 4, "threshold": 5000},
                    {"score": 3, "threshold": 3000},
                    {"score": 2, "threshold": 1000},
                    {"score": 1},
                ],
            }
        },
        "timeout": 300,
    },
    {
        "name": "顺序读稳定性（BW/IOPS 曲线）",
        "description": "fio stability --rw=read --bs=128k --runtime=300 --rounds=1，生成 BW/IOPS 曲线图，人工判定",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_stability_runner.py" --serial {serial} --mode seq_read --runtime 300 --rounds 1',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["stability", "curve"],
        "judgement_type": "assertion",
        "result_parse": {"pass_pattern": "status"},
        "timeout": 600,
    },
    {
        "name": "顺序写稳定性（BW/IOPS 曲线）",
        "description": "fio stability --rw=write --bs=128k --runtime=300 --rounds=1，生成 BW/IOPS 曲线图，人工判定",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_stability_runner.py" --serial {serial} --mode seq_write --runtime 300 --rounds 1',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["stability", "curve"],
        "judgement_type": "assertion",
        "result_parse": {"pass_pattern": "status"},
        "timeout": 600,
    },
    {
        "name": "随机读稳定性（BW/IOPS 曲线）",
        "description": "fio stability --rw=randread --bs=4k --runtime=300 --rounds=1，生成 BW/IOPS 曲线图，人工判定",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_stability_runner.py" --serial {serial} --mode rand_read --runtime 300 --rounds 1',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["stability", "curve"],
        "judgement_type": "assertion",
        "result_parse": {"pass_pattern": "status"},
        "timeout": 600,
    },
    {
        "name": "随机写稳定性（BW/IOPS 曲线）",
        "description": "fio stability --rw=randwrite --bs=4k --runtime=300 --rounds=1，生成 BW/IOPS 曲线图，人工判定",
        "exec_type": "host_exec",
        "exec_command": 'python "{host_tool_dir}/emmc/host/emmc_stability_runner.py" --serial {serial} --mode rand_write --runtime 300 --rounds 1',
        "parameters": {"host_tool_dir": "D:/MCTEST/test-platform/test-tools"},
        "tags": ["stability", "curve"],
        "judgement_type": "assertion",
        "result_parse": {"pass_pattern": "status"},
        "timeout": 600,
    },
]


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TestModule).where(TestModule.name == "EMMC"))
        module = result.scalar_one_or_none()
        if not module:
            print("EMMC 模块不存在，请先创建")
            return

        existing_result = await db.execute(select(TestItem).where(TestItem.module_id == module.id))
        existing_items = {item.name: item for item in existing_result.scalars().all()}

        for idx, item_data in enumerate(EMMC_ITEMS):
            existing = existing_items.get(item_data["name"])
            if existing:
                existing.description = item_data["description"]
                existing.exec_command = item_data["exec_command"]
                existing.parameters = item_data.get("parameters", {})
                existing.tags = item_data.get("tags", [])
                existing.judgement_type = item_data.get("judgement_type", "assertion")
                existing.rubric_criteria = item_data.get("rubric_criteria")
                existing.result_parse = item_data.get("result_parse", {})
                existing.timeout = item_data.get("timeout", 300)
                existing.sort_order = idx
                print(f"更新: {item_data['name']}")
            else:
                new_item = TestItem(
                    module_id=module.id,
                    name=item_data["name"],
                    description=item_data["description"],
                    exec_type=item_data["exec_type"],
                    exec_command=item_data["exec_command"],
                    parameters=item_data.get("parameters", {}),
                    tags=item_data.get("tags", []),
                    judgement_type=item_data.get("judgement_type", "assertion"),
                    rubric_criteria=item_data.get("rubric_criteria"),
                    result_parse=item_data.get("result_parse", {}),
                    timeout=item_data.get("timeout", 300),
                    sort_order=idx,
                    created_by=module.created_by or 1,
                )
                db.add(new_item)
                print(f"新增: {item_data['name']}")

        await db.commit()
        print("EMMC 测试项同步完成")


if __name__ == "__main__":
    asyncio.run(main())
