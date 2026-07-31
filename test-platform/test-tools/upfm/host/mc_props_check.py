#!/usr/bin/env python3
"""
UPFM T1-08 系统配置 ro.mc.* 七字段比对运行器（PC 端，板型画像驱动）。

逐个读取设备 ro.mc.* 属性并与期望值精确比对，输出逐字段比对表：
全部一致打印 RESULT: PASS，任一不一致打印 RESULT: FAIL。

期望值来源（按优先级）：
1. 命令行显式传入的非空值（任务参数覆盖）；
2. 参数为空串 -> 取板型 profile（board_detect 识别，换板无需改参）；
3. 参数传 "*" -> 该字段只读取不比对（采集模式）。

字段映射（期望参数 -> 设备属性）：
    expected_android_version  -> ro.mc.android_version
    expected_cpu              -> ro.mc.cpu
    expected_custom_version   -> ro.mc.custom_api_version（固件无 ro.mc.custom.version，以此代替）
    expected_oem_img_version  -> ro.mc.oem.version
    expected_product          -> ro.mc.product
    expected_version          -> ro.mc.version
    expected_version_code     -> ro.mc.version_code

用法示例:
    python upfm/host/mc_props_check.py --serial FE7G28V8TEST
    python upfm/host/mc_props_check.py --serial FE7G28V8TEST --expected-product "FE7G28/Standard"
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

from board_detect import BoardContext
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


def get_prop(ctx: BoardContext, prop: str) -> str:
    """读取单个属性值（去除首尾空白）。"""
    res = ctx.adb.shell(f"getprop {prop}", timeout=15, check=False)
    if res is None or res.returncode != 0:
        return ""
    return res.stdout.strip()


def resolve_expected(ctx: BoardContext, arg_value: str, prop: str) -> str:
    """确定单字段期望值：显式覆盖 > profile 默认；"*" 保留采集模式。"""
    if arg_value == "*":
        return "*"
    if arg_value:
        return arg_value
    return ctx.profile["mc_props"].get(prop, "")


def run_check(ctx: BoardContext, args) -> dict:
    """逐字段读取并比对，返回结构化结果。"""
    rows = []
    all_ok = True
    for arg_name, prop in FIELD_MAP:
        expected = resolve_expected(ctx, getattr(args, arg_name), prop)
        actual = get_prop(ctx, prop)
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
    parser = argparse.ArgumentParser(description="UPFM ro.mc.* 七字段比对运行器（板型画像驱动）")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    for arg_name, prop in FIELD_MAP:
        parser.add_argument("--" + arg_name.replace("_", "-"), type=str, default="",
                            help=f"{prop} 期望值；空串取板型 profile，* 只读不比对")
    args = parser.parse_args()

    ctx = BoardContext(args.serial)
    print(f"板型识别: {ctx.board_key or '(未知)'} (ro.mc.cpu={ctx.mc_cpu!r}, ro.product.device={ctx.product_device!r})")
    if not ctx.known:
        ctx.fail_unknown_board()
    run_check(ctx, args)


if __name__ == "__main__":
    main()
