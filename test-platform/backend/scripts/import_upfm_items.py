#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UPFM 测试项执行配置导入脚本（幂等，按 T1 编号 upsert）。

用途：板型自动判别改造后，刷新 UPFM 模块（module_id=7）测试项的执行配置
（exec_type / exec_command / parameters / parameters_schema / result_parse /
timeout / retry_count）。期望值不再写死在测试项参数里，改由
test-tools/upfm/host/board_profiles.py 按板型自动取值；parameters 中保留的
键仅作为人工覆盖入口（空串 = 按板型画像取值）。

说明：
- 只更新本脚本列出的执行配置字段，测试项的四要素
  （objective/precondition/steps/expected_result）等描述性字段保持库内原值；
- 按测试项名称中的 T1 编号（如 "T1-22"）匹配，重复执行结果一致；
- 找不到对应测试项时告警跳过，不创建残缺测试项。

用法:
    cd test-platform/backend && python scripts/import_upfm_items.py
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND_DIR / "test_platform.db"
MODULE_ID = 7

RESULT_PARSE_HOST = {"pass_pattern": "RESULT: PASS", "fail_pattern": "RESULT: FAIL"}

HOST_CMD = 'python "{{host_tool_dir}}/upfm/host/{script}" --serial {{serial}}{extra}'

# T1 编号 -> 需要更新的执行配置（未列出的项保持库内原值不动）
UPDATES = {
    # --- 开关类：adb_shell 组合命令 -> 统一 host_exec toggle runner ---
    "T1-03": {
        "exec_type": "host_exec",
        "exec_command": HOST_CMD.format(script="toggle_check.py", extra=" --type wifi"),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "result_parse": RESULT_PARSE_HOST,
        "timeout": 90,
        "retry_count": 2,
    },
    "T1-04": {
        "exec_type": "host_exec",
        "exec_command": HOST_CMD.format(script="toggle_check.py", extra=" --type bluetooth"),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "result_parse": RESULT_PARSE_HOST,
        "timeout": 90,
        # 蓝牙协议栈异常（如 A133P 固件崩溃循环）时重试无意义，避免反复冲击
        "retry_count": 0,
    },
    "T1-05": {
        "exec_type": "host_exec",
        "exec_command": HOST_CMD.format(script="toggle_check.py", extra=" --type airplane"),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "result_parse": RESULT_PARSE_HOST,
        "timeout": 90,
        "retry_count": 2,
    },
    # --- T1-07 固件版本：字段加标签，ro.mc.custom_api_version 允许为空 ---
    "T1-07": {
        "exec_command": 'echo "display_id=$(getprop ro.build.display.id)" && echo "mc_version=$(getprop ro.mc.version)" && echo "custom_api_version=$(getprop ro.mc.custom_api_version)"',
        # display_id / mc_version 必须非空，custom_api_version 字段存在即可（A133P 固件为空）
        "result_parse": {"pass_pattern": r"display_id=\S[\s\S]*mc_version=\S[\s\S]*custom_api_version="},
    },
    # --- T1-08 ro.mc.*：期望值改由板型画像提供，参数留作人工覆盖（空=画像） ---
    "T1-08": {
        "parameters": {
            "expected_android_version": "",
            "expected_cpu": "",
            "expected_custom_version": "",
            "expected_oem_img_version": "",
            "expected_product": "",
            "expected_version": "",
            "expected_version_code": "",
        },
        "parameters_schema": {
            "type": "object",
            "properties": {k: {
                "type": "string", "default": "",
                "description": f"{p} 期望值；空 = 按板型画像自动取值，* = 只读不比对",
            } for k, p in [
                ("expected_android_version", "ro.mc.android_version"),
                ("expected_cpu", "ro.mc.cpu"),
                ("expected_custom_version", "ro.mc.custom_api_version"),
                ("expected_oem_img_version", "ro.mc.oem.version"),
                ("expected_product", "ro.mc.product"),
                ("expected_version", "ro.mc.version"),
                ("expected_version_code", "ro.mc.version_code"),
            ]},
        },
    },
    # --- T1-13 屏幕旋转：adb_shell（A10 上 user_rotation 为 null 时报异常）-> host_exec ---
    "T1-13": {
        "exec_type": "host_exec",
        "exec_command": HOST_CMD.format(script="rotation_check.py", extra=""),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "result_parse": RESULT_PARSE_HOST,
        "timeout": 60,
        "retry_count": 0,
    },
    # --- T1-16 触摸点数：期望点数改由板型画像提供 ---
    "T1-16": {
        # 参数加引号：空串（按画像取值）时 argparse 也能拿到空参数而非报错
        "exec_command": HOST_CMD.format(script="touch_points.py", extra=' --expected-points "{expected_points}"'),
        "parameters": {"expected_points": ""},
        "parameters_schema": {
            "type": "object",
            "properties": {
                "expected_points": {
                    "type": "string", "default": "",
                    "description": "期望触摸点数；空 = 按板型画像自动取值",
                },
            },
        },
    },
    # --- T1-22/23 CPU 频率：adb_shell 写死期望值 -> host_exec 画像驱动 ---
    "T1-22": {
        "exec_type": "host_exec",
        "exec_command": HOST_CMD.format(script="cpu_freq_check.py", extra=" --mode available"),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "result_parse": RESULT_PARSE_HOST,
        "timeout": 60,
        "retry_count": 0,
    },
    "T1-23": {
        "exec_type": "host_exec",
        "exec_command": HOST_CMD.format(script="cpu_freq_check.py", extra=" --mode max"),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "result_parse": RESULT_PARSE_HOST,
        "timeout": 60,
        "retry_count": 0,
    },
    # --- T1-24/25 GPU 频率：期望值改由板型画像提供；supported=false 板型 runner 输出 SKIP ---
    "T1-24": {
        "exec_command": HOST_CMD.format(script="gpu_freq_check.py", extra=" --mode available"),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "timeout": 60,
    },
    "T1-25": {
        "exec_command": HOST_CMD.format(script="gpu_freq_check.py", extra=" --mode max"),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "timeout": 60,
    },
    # --- T1-26 DDR 频率：adb_shell 写死期望值 -> host_exec 画像驱动（runner 自动 adb root） ---
    "T1-26": {
        "exec_type": "host_exec",
        "exec_command": HOST_CMD.format(script="ddr_freq_check.py", extra=""),
        "parameters": {},
        "parameters_schema": {"type": "object", "properties": {}},
        "result_parse": RESULT_PARSE_HOST,
        "timeout": 60,
        "retry_count": 0,
    },
}

JSON_FIELDS = {"parameters", "parameters_schema", "result_parse", "compatibility"}


def main():
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT id, name FROM test_items WHERE module_id = ?", (MODULE_ID,)
    ).fetchall()

    # 按 T1 编号索引现有测试项
    by_code = {}
    for row in rows:
        code = row["name"].split(" ", 1)[0].strip()
        by_code[code] = row["id"]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated, skipped = 0, []
    for code, fields in UPDATES.items():
        item_id = by_code.get(code)
        if item_id is None:
            skipped.append(code)
            continue
        sets, values = [], []
        for col, val in fields.items():
            sets.append(f"{col} = ?")
            values.append(json.dumps(val, ensure_ascii=False) if col in JSON_FIELDS else val)
        sets.append("updated_at = ?")
        values.append(now)
        values.append(item_id)
        db.execute(f"UPDATE test_items SET {', '.join(sets)} WHERE id = ?", values)
        updated += 1
        print(f"[updated] {code} (id={item_id}): {', '.join(fields.keys())}")

    db.commit()

    # 复核：打印改动后的执行配置摘要
    print("\n=== 复核 ===")
    for code in UPDATES:
        item_id = by_code.get(code)
        if item_id is None:
            continue
        row = db.execute(
            "SELECT name, exec_type, exec_command FROM test_items WHERE id = ?", (item_id,)
        ).fetchone()
        print(f"{row['name']} | {row['exec_type']} | {row['exec_command'][:100]}")

    db.close()
    print(f"\n完成: 更新 {updated} 项，跳过 {len(skipped)} 项 {skipped or ''}")


if __name__ == "__main__":
    main()
