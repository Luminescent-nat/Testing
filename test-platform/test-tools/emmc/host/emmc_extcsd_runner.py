#!/usr/bin/env python3
"""
EMMC EXT_CSD 寄存器读取运行器（PC 端）。

通过 ADB 在目标设备上运行 mmc_utils，解析 extcsd 输出为结构化 JSON。

用法示例:
    python emmc/host/emmc_extcsd_runner.py --serial 2492d300b0ae006c
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Windows 默认终端可能是 GBK，遇到无法编码的字符会崩溃；强制使用 UTF-8 并替换不可编码字符。
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 支持从 test-tools 根目录 import common
TOOLS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(TOOLS_ROOT))

from common.adb_runner import AdbRunner
from common.device_info import detect_arch, detect_mmc_node, get_tool_path
from common.logger import setup_logger

logger = setup_logger("emmc_extcsd")


def _parse_hex_val(content: str, pattern: str, default: str = "Unknown") -> str:
    match = re.search(pattern, content, re.IGNORECASE)
    return match.group(1).strip() if match else default


def parse_extcsd(output: str, mmc_node: str) -> dict:
    """解析 mmc_utils extcsd read 输出。"""
    data = {
        "mmc_node": mmc_node,
        "life_time_type_a": _parse_hex_val(output, r"DEVICE_LIFE_TIME_EST_TYP_A.*?:\s*(0x[0-9a-f]+)"),
        "life_time_type_b": _parse_hex_val(output, r"DEVICE_LIFE_TIME_EST_TYP_B.*?:\s*(0x[0-9a-f]+)"),
        "pre_eol_info": _parse_hex_val(output, r"PRE_EOL_INFO.*?:\s*(0x[0-9a-f]+)"),
        "cache_size": "Unknown",
        "sector_count": _parse_hex_val(output, r"SEC_COUNT.*?:\s*(0x[0-9a-f]+)"),
        "capacity_gib": None,
        "max_packed_reads": _parse_hex_val(output, r"MAX_PACKED_READS.*?:\s*(0x[0-9a-f]+)"),
        "max_packed_writes": _parse_hex_val(output, r"MAX_PACKED_WRITES.*?:\s*(0x[0-9a-f]+)"),
        "trim_multiplier": _parse_hex_val(output, r"TRIM_MULT.*?:\s*(0x[0-9a-f]+)"),
        "hc_erase_group_size": _parse_hex_val(output, r"HC_ERASE_GRP_SIZE.*?:\s*(0x[0-9a-f]+)"),
        "hc_wp_group_size": _parse_hex_val(output, r"HC_WP_GRP_SIZE.*?:\s*(0x[0-9a-f]+)"),
        "sleep_current_vcc": _parse_hex_val(output, r"S_C_VCC.*?:\s*(0x[0-9a-f]+)"),
        "sleep_current_vccq": _parse_hex_val(output, r"S_C_VCCQ.*?:\s*(0x[0-9a-f]+)"),
        "sleep_awake_timeout": _parse_hex_val(output, r"S_A_TIMEOUT.*?:\s*(0x[0-9a-f]+)"),
        "init_timeout": _parse_hex_val(output, r"INI_TIMEOUT_AP.*?:\s*(0x[0-9a-f]+)"),
        "cmdq_depth": _parse_hex_val(output, r"CMDQ_DEPTH.*?:\s*(0x[0-9a-f]+)"),
        "cmdq_enabled": _parse_hex_val(output, r"CMDQ_MODE_EN.*?:\s*(0x[0-9a-f]+)"),
        "card_type": "Unknown",
        "firmware_version": "Unknown",
    }

    ch_sz = re.search(r"CACHE_SIZE\]\s*is\s*([^\n\r]+)", output, re.IGNORECASE)
    if ch_sz:
        data["cache_size"] = ch_sz.group(1).strip()
    else:
        data["cache_size"] = _parse_hex_val(output, r"CACHE_SIZE.*?:\s*(0x[0-9a-f]+)")

    if data["sector_count"].startswith("0x"):
        sec_cnt = int(data["sector_count"], 16)
        data["capacity_gib"] = round((sec_cnt * 512) / (1024 ** 3), 2)

    card_m = re.search(
        r"Card Type \[CARD_TYPE: (0x[0-9a-f]+)\](.*?)(?=\r?\n[^\s\-]|\r?\n\r?\n)",
        output,
        re.DOTALL | re.IGNORECASE,
    )
    if card_m:
        data["card_type_raw"] = card_m.group(1).strip()
        desc = card_m.group(2).strip()
        data["card_type"] = desc if desc else data["card_type_raw"]

    fw_ver = re.search(r"eMMC Firmware Version:\s*([^\n\r]+)", output, re.IGNORECASE)
    if fw_ver:
        data["firmware_version"] = fw_ver.group(1).strip()

    return data


def run_extcsd(adb: AdbRunner, args) -> dict:
    """执行 extcsd 读取并返回结构化数据。"""
    adb.root()

    arch = detect_arch(adb)
    logger.info("设备架构: %s", arch)

    mmc_node = detect_mmc_node(adb, args.mmc_node)
    logger.info("eMMC 节点: %s", mmc_node)

    search_roots = [Path(__file__).resolve().parent.parent, TOOLS_ROOT]
    mmc_path = get_tool_path("mmc_utils", arch, search_roots)
    remote_dir = "/data/local/tmp/emmc"
    remote_mmc = f"{remote_dir}/mmc_utils"

    adb.shell(f"mkdir -p {remote_dir}", check=False)
    if not adb.push(mmc_path, remote_mmc):
        raise RuntimeError("推送 mmc_utils 失败")

    adb.shell(f"chmod +x {remote_mmc}", check=False)

    logger.info("读取 extcsd...")
    res = adb.shell(f"{remote_mmc} extcsd read {mmc_node}", timeout=30, check=False)
    if res is None or res.returncode != 0:
        err = res.stderr if res else "命令超时"
        raise RuntimeError(f"extcsd 读取失败: {err}")

    data = parse_extcsd(res.stdout, mmc_node)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def main():
    parser = argparse.ArgumentParser(description="EMMC EXT_CSD 读取运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--mmc-node", type=str, default=None, help="手动指定 eMMC 节点")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)
    run_extcsd(adb, args)


if __name__ == "__main__":
    main()
