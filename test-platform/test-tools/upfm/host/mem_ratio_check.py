#!/usr/bin/env python3
"""
UPFM T1-27 剩余内存比例验证运行器（PC 端）。

解析 `dumpsys meminfo` 汇总段的 Total RAM / Free RAM（单位 K，含千分位逗号），
计算剩余内存百分比 = Free / Total * 100，断言落在 [--min-percent, --max-percent] 区间。

判定：区间内 -> RESULT: PASS；区间外或解析失败 -> RESULT: FAIL。实测百分比始终打印。
注意：该比例与设备运行时长强相关，用例基线通常要求"烧录重启后首次"前置。

用法示例:
    python upfm/host/mem_ratio_check.py --serial FE7G28V8TEST --min-percent 50 --max-percent 80
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Windows 默认终端可能是 GBK，强制 UTF-8 并替换不可编码字符
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

TOOLS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(TOOLS_ROOT))

from common.adb_runner import AdbRunner
from common.logger import setup_logger

logger = setup_logger("mem_ratio_check")


def parse_ram_kb(output: str, label: str):
    """从 dumpsys meminfo 输出解析 '<label>: 2,006,888K' 形式的数值（K）。"""
    m = re.search(rf"{label}:\s*([\d,]+)K", output)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def main():
    parser = argparse.ArgumentParser(description="UPFM 剩余内存比例验证运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--min-percent", type=float, default=50, help="剩余内存百分比下限（默认 50）")
    parser.add_argument("--max-percent", type=float, default=80, help="剩余内存百分比上限（默认 80）")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)
    res = adb.shell("dumpsys meminfo", timeout=60, check=False)
    output = res.stdout if res and res.stdout else ""

    total_kb = parse_ram_kb(output, "Total RAM")
    free_kb = parse_ram_kb(output, "Free RAM")
    print(f"Total RAM: {total_kb}K, Free RAM: {free_kb}K")

    if not total_kb or free_kb is None:
        print("RESULT: FAIL (dumpsys meminfo 解析失败)")
        print(json.dumps({"result": "fail", "reason": "parse_error"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    percent = round(free_kb / total_kb * 100, 1)
    ok = args.min_percent <= percent <= args.max_percent
    print(f"实测剩余内存比例: {percent}%（断言区间 {args.min_percent}%~{args.max_percent}%）")
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print(json.dumps({
        "result": "pass" if ok else "fail",
        "total_ram_kb": total_kb,
        "free_ram_kb": free_kb,
        "free_percent": percent,
        "min_percent": args.min_percent,
        "max_percent": args.max_percent,
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
