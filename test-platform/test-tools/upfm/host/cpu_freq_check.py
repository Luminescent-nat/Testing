#!/usr/bin/env python3
"""
UPFM T1-22/T1-23 CPU 频率验证运行器（PC 端，板型画像驱动）。

期望值默认取板型 profile（board_detect 识别），--expected 可覆盖：
- available：读 scaling_available_frequencies，与期望值按集合精确比对（顺序无关）
- max      ：读 cpuinfo_max_freq，与期望单值精确比对

判定：一致 -> RESULT: PASS；不一致 -> RESULT: FAIL；未知识别板型 -> RESULT: FAIL。

用法示例:
    python upfm/host/cpu_freq_check.py --serial FE7G28V8TEST --mode available
    python upfm/host/cpu_freq_check.py --serial FE7G28V8TEST --mode max --expected 1992000
"""

import argparse
import io
import json
import sys
from pathlib import Path

# Windows 默认终端可能是 GBK，强制 UTF-8 并替换不可编码字符
if (sys.platform == "win32" and hasattr(sys.stdout, "buffer")
        and (sys.stdout.encoding or "").lower() not in ("utf-8", "utf8")):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HOST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOST_DIR))

from board_detect import BoardContext, shell_out
from common.logger import setup_logger

logger = setup_logger("cpu_freq_check")

CPU_BASE = "/sys/devices/system/cpu/cpu0/cpufreq"


def main():
    parser = argparse.ArgumentParser(description="UPFM CPU 频率验证运行器（板型画像驱动）")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--mode", type=str, required=True, choices=["available", "max"], help="校验模式")
    parser.add_argument("--expected", type=str, default=None,
                        help="期望值覆盖：available 为空格分隔频率列表，max 为单值；缺省取板型 profile")
    args = parser.parse_args()

    ctx = BoardContext(args.serial)
    print(f"板型识别: {ctx.board_key or '(未知)'} (ro.mc.cpu={ctx.mc_cpu!r}, ro.product.device={ctx.product_device!r})")
    if not ctx.known:
        ctx.fail_unknown_board()

    cpu = ctx.profile["cpu"]
    if args.mode == "available":
        expected_raw = args.expected if args.expected else cpu["available_freqs"]
        actual_raw = shell_out(ctx.adb, f"cat {CPU_BASE}/scaling_available_frequencies")
        expected_list = expected_raw.split()
        actual_list = actual_raw.split()
        print(f"期望频率表: {' '.join(expected_list)}")
        print(f"实际频率表: {actual_raw}")
        ok = bool(actual_list) and sorted(expected_list) == sorted(actual_list)
        detail = "available_frequencies 一致" if ok else "available_frequencies 不一致"
        extra = {"mode": "available", "expected": expected_list, "actual": actual_list}
    else:
        expected = (args.expected if args.expected else cpu["max_freq"]).strip()
        actual = shell_out(ctx.adb, f"cat {CPU_BASE}/cpuinfo_max_freq")
        print(f"期望 max_freq: {expected}")
        print(f"实际 max_freq: {actual}")
        ok = bool(actual) and actual == expected
        detail = "max_freq 一致" if ok else "max_freq 不一致"
        extra = {"mode": "max", "expected": expected, "actual": actual}

    print(f"RESULT: {'PASS' if ok else 'FAIL'} ({detail})")
    print(json.dumps({"result": "pass" if ok else "fail", "board": ctx.board_key, **extra},
                     ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
