import logging
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Device, TestModule, TestItem, TestTool
from app.services.memory_engine import FailurePatternService

logger = logging.getLogger(__name__)


async def seed_default_data(db: AsyncSession):
    """初始化测试模块、用例模板与失败模式。不自动创建用户，第一个注册用户自动成为 admin。"""
    # 不再自动创建默认用户，避免虚构账号和固定密码泄漏风险。
    # 第一个通过 /auth/register 注册的用户会自动分配 admin 角色。
    # 如需系统初始化账号，请注册后使用 admin 创建其他用户。

    # 使用一个虚拟 created_by=1 初始化模板数据；若已有真实用户则优先使用第一个用户
    result = await db.execute(select(User).order_by(User.id))
    user = result.scalars().first()
    user_id = user.id if user else 1

    # 不再自动创建示例设备，避免产生虚构测试数据。
    # 真实设备通过 /api/v1/devices/refresh 接口发现并同步。
    # await _seed_sample_device(db, user)
    await _cleanup_legacy_fake_data(db)
    await _seed_default_modules_and_items(db, user_id)
    await FailurePatternService.seed_default_patterns(db, user_id)


async def _cleanup_legacy_fake_data(db: AsyncSession):
    """清理历史版本遗留的虚假/硬编码数据（幂等，失败只记日志不影响启动）。

    - 删除占位 memtester 工具及其"DDR 压力测试"用例：该工具内容只是 echo "ok"，
      不真测内存也永远 PASS，会产生虚假测试结论；
    - 剥离测试项 parameters 中硬编码的 host_tool_dir 绝对路径：
      引擎现在会自动将 {host_tool_dir} 解析为 TEST_TOOLS_PATH 配置目录。
    """
    try:
        result = await db.execute(
            select(TestItem).where(TestItem.name == "DDR 压力测试")
        )
        for item in result.scalars().all():
            await db.delete(item)
            logger.info("删除虚假测试项: DDR 压力测试 (id=%s)", item.id)

        result = await db.execute(select(TestTool).where(TestTool.name == "memtester"))
        for tool in result.scalars().all():
            await db.delete(tool)
            logger.info("删除占位测试工具: memtester (id=%s)", tool.id)

        result = await db.execute(select(TestItem))
        for item in result.scalars().all():
            params = item.parameters or {}
            host_dir = params.get("host_tool_dir")
            if host_dir and os.path.isabs(str(host_dir)):
                params = {k: v for k, v in params.items() if k != "host_tool_dir"}
                item.parameters = params
                logger.info("剥离测试项硬编码 host_tool_dir: %s (id=%s)", item.name, item.id)

        await db.commit()
    except Exception:
        logger.exception("历史数据清理失败（不影响启动）")
        await db.rollback()


async def _seed_sample_device(db: AsyncSession, user: User):
    """初始化示例设备，补充默认硬件画像，便于无真实设备时验证 AI 规划链路。"""
    result = await db.execute(select(Device).where(Device.serial_number == "rk3568-test-001"))
    device = result.scalar_one_or_none()
    if not device:
        device = Device(
            serial_number="rk3568-test-001",
            model="rk3568",
            brand="rockchip",
            android_version="11",
            sdk_version="30",
            cpu_abi="arm64-v8a",
            status="online",
            owner_id=user.id,
            pc_identifier="",
            board="rk3568",
            hardware="rk3568-evb",
            ddr_info={"total_mb": 2048, "type": "LPDDR4", "frequency_mhz": 1600},
            emmc_info={"total_gb": 32, "model": "Samsung KLMAG1JETD-B041", "health": "good"},
            wifi_chip="AP6255",
            bt_chip="AP6255",
            eth_interfaces=["eth0"],
            features=["wifi", "bluetooth", "ethernet"]
        )
        db.add(device)
        logger.info("创建示例设备: %s", device.serial_number)
    else:
        # 补齐缺失的硬件画像字段，确保参数渲染不失败
        if not device.ddr_info:
            device.ddr_info = {"total_mb": 2048, "type": "LPDDR4", "frequency_mhz": 1600}
        if not device.emmc_info:
            device.emmc_info = {"total_gb": 32, "model": "Samsung KLMAG1JETD-B041", "health": "good"}
        if not device.features:
            device.features = ["wifi", "bluetooth", "ethernet"]
        logger.info("更新示例设备画像: %s", device.serial_number)
    await db.commit()


async def _seed_default_modules_and_items(db: AsyncSession, user_id: int):
    """初始化默认测试模块与用例模板。"""

    modules = [
        {
            "name": "DDR",
            "category": "memory",
            "description": "DDR 内存基础测试",
            "items": [
                {
                    "name": "容量校验",
                    "description": "通过 /proc/meminfo 读取 DDR 总容量",
                    "exec_type": "adb_shell",
                    "exec_command": "cat /proc/meminfo | grep MemTotal",
                    "tags": ["functional"],
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "MemTotal"}
                }
            ]
        },
        {
            "name": "EMMC",
            "category": "storage",
            "description": "EMMC 存储性能与信息采集（对齐 emmc_tools.py 流程）",
            "items": [
                {
                    "name": "节点检测",
                    "description": "自动识别设备主存储 eMMC 节点",
                    "exec_type": "adb_shell",
                    "exec_command": "ls /sys/block/ | grep mmcblk | head -5",
                    "tags": ["functional"],
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "mmcblk"}
                },
                {
                    "name": "EXT_CSD 寄存器读取",
                    "description": "通过 mmc_utils 读取 eMMC 扩展寄存器信息",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_extcsd_runner.py\" --serial {serial}",
                    "parameters": {},
                    "tags": ["functional"],
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "mmc_node"},
                    "timeout": 120
                },
                {
                    "name": "顺序读性能",
                    "description": "fio --rw=read --bs=128k --iodepth=64 --runtime=60 --rounds=3",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_fio_runner.py\" --serial {serial} --mode seq_read --runtime 60 --rounds 3",
                    "parameters": {},
                    "tags": ["performance"],
                    "judgement_type": "rubric",
                    "rubric_criteria": {
                        "bw_mbps": {
                            "extract_pattern": "\"bw_mbps\"\\s*:\\s*([\\d.]+)",
                            "source": "baseline",
                            "metric": "bw_mbps",
                            "operator": ">=",
                            "baseline_field": "avg_value",
                            "tolerance": "0%",
                            "fallback_levels": [
                                {"score": 4, "threshold": 200},
                                {"score": 3, "threshold": 150},
                                {"score": 2, "threshold": 100},
                                {"score": 1}
                            ]
                        }
                    },
                    "timeout": 300
                },
                {
                    "name": "顺序写性能",
                    "description": "fio --rw=write --bs=128k --iodepth=64 --runtime=60 --rounds=3",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_fio_runner.py\" --serial {serial} --mode seq_write --runtime 60 --rounds 3",
                    "parameters": {},
                    "tags": ["performance"],
                    "judgement_type": "rubric",
                    "rubric_criteria": {
                        "bw_mbps": {
                            "extract_pattern": "\"bw_mbps\"\\s*:\\s*([\\d.]+)",
                            "source": "baseline",
                            "metric": "bw_mbps",
                            "operator": ">=",
                            "baseline_field": "avg_value",
                            "tolerance": "0%",
                            "fallback_levels": [
                                {"score": 4, "threshold": 150},
                                {"score": 3, "threshold": 100},
                                {"score": 2, "threshold": 50},
                                {"score": 1}
                            ]
                        }
                    },
                    "timeout": 300
                },
                {
                    "name": "随机读性能",
                    "description": "fio --rw=randread --bs=4k --iodepth=64 --runtime=60 --rounds=3",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_fio_runner.py\" --serial {serial} --mode rand_read --runtime 60 --rounds 3",
                    "parameters": {},
                    "tags": ["performance"],
                    "judgement_type": "rubric",
                    "rubric_criteria": {
                        "iops": {
                            "extract_pattern": "\"iops\"\\s*:\\s*([\\d.]+)",
                            "source": "baseline",
                            "metric": "iops",
                            "operator": ">=",
                            "baseline_field": "avg_value",
                            "tolerance": "0%",
                            "fallback_levels": [
                                {"score": 4, "threshold": 8000},
                                {"score": 3, "threshold": 5000},
                                {"score": 2, "threshold": 2000},
                                {"score": 1}
                            ]
                        }
                    },
                    "timeout": 300
                },
                {
                    "name": "随机写性能",
                    "description": "fio --rw=randwrite --bs=4k --iodepth=64 --runtime=60 --rounds=3",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_fio_runner.py\" --serial {serial} --mode rand_write --runtime 60 --rounds 3",
                    "parameters": {},
                    "tags": ["performance"],
                    "judgement_type": "rubric",
                    "rubric_criteria": {
                        "iops": {
                            "extract_pattern": "\"iops\"\\s*:\\s*([\\d.]+)",
                            "source": "baseline",
                            "metric": "iops",
                            "operator": ">=",
                            "baseline_field": "avg_value",
                            "tolerance": "0%",
                            "fallback_levels": [
                                {"score": 4, "threshold": 5000},
                                {"score": 3, "threshold": 3000},
                                {"score": 2, "threshold": 1000},
                                {"score": 1}
                            ]
                        }
                    },
                    "timeout": 300
                },
                {
                    "name": "顺序读稳定性（BW/IOPS 曲线）",
                    "description": "fio stability --rw=read --bs=128k --runtime=300 --rounds=1，生成 BW/IOPS 曲线图，人工判定",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_stability_runner.py\" --serial {serial} --mode seq_read --runtime 300 --rounds 1",
                    "parameters": {},
                    "tags": ["stability", "curve"],
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "status"},
                    "timeout": 600
                },
                {
                    "name": "顺序写稳定性（BW/IOPS 曲线）",
                    "description": "fio stability --rw=write --bs=128k --runtime=300 --rounds=1，生成 BW/IOPS 曲线图，人工判定",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_stability_runner.py\" --serial {serial} --mode seq_write --runtime 300 --rounds 1",
                    "parameters": {},
                    "tags": ["stability", "curve"],
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "status"},
                    "timeout": 600
                },
                {
                    "name": "随机读稳定性（BW/IOPS 曲线）",
                    "description": "fio stability --rw=randread --bs=4k --runtime=300 --rounds=1，生成 BW/IOPS 曲线图，人工判定",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_stability_runner.py\" --serial {serial} --mode rand_read --runtime 300 --rounds 1",
                    "parameters": {},
                    "tags": ["stability", "curve"],
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "status"},
                    "timeout": 600
                },
                {
                    "name": "随机写稳定性（BW/IOPS 曲线）",
                    "description": "fio stability --rw=randwrite --bs=4k --runtime=300 --rounds=1，生成 BW/IOPS 曲线图，人工判定",
                    "exec_type": "host_exec",
                    "exec_command": "python \"{host_tool_dir}/emmc/host/emmc_stability_runner.py\" --serial {serial} --mode rand_write --runtime 300 --rounds 1",
                    "parameters": {},
                    "tags": ["stability", "curve"],
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "status"},
                    "timeout": 600
                }
            ]
        },
        {
            "name": "WIFI",
            "category": "network",
            "description": "WIFI 无线基础测试",
            "items": [
                {
                    "name": "WIFI 开关状态",
                    "description": "检查 WIFI 是否启用",
                    "exec_type": "adb_shell",
                    "exec_command": "dumpsys wifi | grep 'Wi-Fi is'",
                    "tags": ["functional"],
                    "compatibility": {"required_features": ["wifi"]},
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "enabled|enabled"}
                },
                {
                    "name": "WIFI 信号强度",
                    "description": "读取当前连接 WIFI 的信号强度",
                    "exec_type": "adb_shell",
                    "exec_command": "dumpsys wifi | grep -i rssi",
                    "tags": ["performance"],
                    "compatibility": {"required_features": ["wifi"]},
                    "judgement_type": "rubric",
                    "rubric_criteria": {
                        "signal_strength": {
                            "extract_pattern": "rssi[=:]\\s*(-?\\d+)",
                            "levels": [
                                {"score": 4, "threshold": -50},
                                {"score": 3, "threshold": -60},
                                {"score": 2, "threshold": -70},
                                {"score": 1}
                            ]
                        }
                    }
                }
            ]
        },
        {
            "name": "蓝牙",
            "category": "network",
            "description": "蓝牙基础测试",
            "items": [
                {
                    "name": "蓝牙开关状态",
                    "description": "检查蓝牙是否启用",
                    "exec_type": "adb_shell",
                    "exec_command": "dumpsys bluetooth_manager | grep 'enabled'",
                    "tags": ["functional"],
                    "compatibility": {"required_features": ["bluetooth"]},
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "enabled:\\s*true", "fail_pattern": "enabled:\\s*false"}
                }
            ]
        },
        {
            "name": "以太网",
            "category": "network",
            "description": "以太网有线基础测试",
            "items": [
                {
                    "name": "链路状态",
                    "description": "检查以太网接口链路状态",
                    "exec_type": "adb_shell",
                    "exec_command": "cat /sys/class/net/eth0/carrier",
                    "tags": ["functional"],
                    "compatibility": {"required_features": ["ethernet"]},
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "^1\\s*$", "fail_pattern": "^0\\s*$"}
                },
                {
                    "name": "Ping 网关",
                    "description": "测试以太网连通性",
                    "exec_type": "adb_shell",
                    "exec_command": "ping -c 3 8.8.8.8",
                    "tags": ["functional"],
                    "compatibility": {"required_features": ["ethernet"]},
                    "judgement_type": "assertion",
                    "result_parse": {"pass_pattern": "3 received|0% packet loss"}
                }
            ]
        },
        {
            "name": "CPU",
            "category": "processor",
            "description": "CPU 基础测试",
            "items": [
                {
                    "name": "CPU 信息",
                    "description": "读取 CPU 型号与核心数",
                    "exec_type": "adb_shell",
                    "exec_command": "cat /proc/cpuinfo | grep 'Hardware\\|Processor' | head -5",
                    "tags": ["functional"],
                    "judgement_type": "assertion"
                }
            ]
        }
    ]

    for module_data in modules:
        result = await db.execute(select(TestModule).where(TestModule.name == module_data["name"]))
        module = result.scalar_one_or_none()
        if not module:
            module = TestModule(
                name=module_data["name"],
                category=module_data.get("category"),
                description=module_data.get("description"),
                created_by=user_id
            )
            db.add(module)
            await db.flush()
            logger.info("创建测试模块: %s", module.name)

        for item_data in module_data.get("items", []):
            result = await db.execute(
                select(TestItem).where(
                    TestItem.module_id == module.id,
                    TestItem.name == item_data["name"]
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                continue

            # 如果测试项指定了工具名，查询对应 tool_id
            tool_id = None
            tool_name = item_data.get("tool_name")
            if tool_name:
                tool_result = await db.execute(select(TestTool).where(TestTool.name == tool_name))
                tool = tool_result.scalar_one_or_none()
                if tool:
                    tool_id = tool.id
                else:
                    logger.warning("测试项 %s 依赖的工具 %s 不存在", item_data["name"], tool_name)

            new_item = TestItem(
                module_id=module.id,
                name=item_data["name"],
                description=item_data.get("description"),
                exec_type=item_data["exec_type"],
                exec_command=item_data["exec_command"],
                parameters=item_data.get("parameters", {}),
                compatibility=item_data.get("compatibility", {}),
                judgement_type=item_data.get("judgement_type", "assertion"),
                conditional_rules=item_data.get("conditional_rules"),
                rubric_criteria=item_data.get("rubric_criteria"),
                result_parse=item_data.get("result_parse", {}),
                timeout=item_data.get("timeout", 300),
                tags=item_data.get("tags", []),
                tool_id=tool_id,
                created_by=user_id
            )
            db.add(new_item)
            logger.info("创建测试项: %s / %s", module.name, new_item.name)

    await db.commit()
    logger.info("默认用例模板初始化完成")
