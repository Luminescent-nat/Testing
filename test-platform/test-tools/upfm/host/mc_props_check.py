#!/usr/bin/env python3
"""
UPFM T1-08 系统配置 ro.mc.* 七字段比对运行器（PC 端）。

逐个读取设备 ro.mc.* 属性并与参数化期望值精确比对，输出逐字段比对表：
全部一致打印 RESULT: PASS，任一不一致打印 RESULT: FAIL。

字段映射（期望参数 -> 设备属性）：
    expected_android_version  -> ro.mc.android_version
    expected_cpu              -> ro.mc.cpu
    expected_custom_version   -> ro.mc.custom_api_version（固件无 ro.mc.custom.version，以此代替）
    expected_oem_img_version  -> ro.mc.oem.version
    expected_product          -> ro.mc.product
    expected_version          -> ro.mc.version
    expected_version_code     -> ro.mc.version_code

期望值传 "*" 表示该字段只读取不比对（采集模式）。

用法示例:
    python upfm/host/mc_props_check.py --serial FE7G28V8TEST --expected-product "FE7G28/Standard"
"""

import argparse
import io
import json
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

logger = setup_logger("mc_props_check")

# (参数名, 设备属性名)
FIELD_MAP = [
    ("expected_android_version", "ro.mc.android_version"),
    ("expected_cpu", "ro.mc.cpu"),
    ("expected_custom_version", "ro.mc.custom_api_version"),
    ("expected_oem_img_version", "ro.mc.oem.version"),
    ("expected_product", "ro.mc.product"),
    ("expected_version", "ro.mc.version"),
    ("expected_version_code", "ro.mc.version_code"),
]


def get_prop(adb: AdbRunner, prop: str) -> str:
    """读取单个属性值（去除首尾空白）。"""
    res = adb.shell(f"getprop {prop}", timeout=15, check=False)
    if res is None or res.returncode != 0:
        return ""
    return res.stdout.strip()


def run_check(adb: AdbRunner, args) -> dict:
    """逐字段读取并比对，返回结构化结果。"""
    rows = []
    all_ok = True
    for arg_name, prop in FIELD_MAP:
        expected = getattr(args, arg_name)
        actual = get_prop(adb, prop)
        if expected == "*":
            status = "SKIP_COMPARE"
        elif actual == expected:
            status = "OK"
        else:
            status = "DIFF"
            all_ok = False
        rows.append({"prop": prop, "expected": expected, "actual": actual, "status": status})
        logger.info("%-28s expected=[%s] actual=[%s] -> %s", prop, expected, actual, status)

    # 逐字段比对表（stdout，供平台记录）
    print(f"{'PROP':<28} {'EXPECTED':<24} {'ACTUAL':<24} STATUS")
    for r in rows:
        print(f"{r['prop']:<28} {r['expected']:<24} {r['actual']:<24} {r['status']}")

    result = {
        "result": "pass" if all_ok else "fail",
        "fields": rows,
        "diff_count": sum(1 for r in rows if r["status"] == "DIFF"),
    }
    print(f"RESULT: {'PASS' if all_ok else 'FAIL'} (ro.mc.* 七字段比对，差异 {result['diff_count']} 处)")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="UPFM ro.mc.* 七字段比对运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--expected-android-version", type=str, default="*", help="ro.mc.android_version 期望值")
    parser.add_argument("--expected-cpu", type=str, default="*", help="ro.mc.cpu 期望值")
    parser.add_argument("--expected-custom-version", type=str, default="*", help="ro.mc.custom_api_version 期望值")
    parser.add_argument("--expected-oem-img-version", type=str, default="*", help="ro.mc.oem.version 期望值")
    parser.add_argument("--expected-product", type=str, default="*", help="ro.mc.product 期望值")
    parser.add_argument("--expected-version", type=str, default="*", help="ro.mc.version 期望值")
    parser.add_argument("--expected-version-code", type=str, default="*", help="ro.mc.version_code 期望值")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)
    run_check(adb, args)


if __name__ == "__main__":
    main()
