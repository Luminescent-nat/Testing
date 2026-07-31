#!/usr/bin/env python3
"""
UPFM T1-13 屏幕旋转设置验证运行器（PC 端）。

任务 #9 实测：Android 10（A133P）上原 adb_shell 组合命令报
`Invalid value: null for setting: user_rotation` —— 自动旋转开启时
user_rotation 未初始化（settings get 返回 "null"），把 null 写回即触发
SettingsProvider 异常。本 runner 改为 host_exec，处理该场景：

流程：记录原 accelerometer_rotation / user_rotation
      -> 若 accelerometer_rotation 非 0 则先置 0（锁定方向，避免传感器立即改回）
      -> user_rotation 写一个与原值不同的值（0/1 互换；原值 null 时写 1）
      -> 读回断言 -> finally 恢复原 user_rotation 与 accelerometer_rotation。

判定：读回值 == 写入值 -> RESULT: PASS；否则 -> RESULT: FAIL。

用法示例:
    python upfm/host/rotation_check.py --serial 9c000c8a230487920dd
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
TOOLS_ROOT = HOST_DIR.parent.parent
sys.path.insert(0, str(TOOLS_ROOT))

from common.adb_runner import AdbRunner
from common.logger import setup_logger

logger = setup_logger("rotation_check")


def shell_out(adb: AdbRunner, cmd: str, timeout: int = 15) -> str:
    """执行设备端命令并返回 stdout（失败返回空串）。"""
    res = adb.shell(cmd, timeout=timeout, check=False)
    return res.stdout.strip() if res and res.stdout else ""


def get_setting(adb: AdbRunner, ns: str, key: str) -> str:
    """读 settings 值，未设置（null）归一为空串。"""
    out = shell_out(adb, f"settings get {ns} {key}")
    return "" if out == "null" else out


def put_setting(adb: AdbRunner, ns: str, key: str, value: str) -> tuple:
    """写 settings 值，返回 (是否成功, stderr)。"""
    res = adb.shell(f"settings put {ns} {key} {value}", timeout=15, check=False)
    err = (res.stderr or "").strip() if res else "命令执行失败"
    ok = bool(res) and res.returncode == 0 and "Exception" not in (res.stdout or "") and not err
    return ok, err or (res.stdout or "").strip()


def main():
    parser = argparse.ArgumentParser(description="UPFM 屏幕旋转设置验证运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)

    orig_rotation = get_setting(adb, "system", "user_rotation")
    orig_accel = get_setting(adb, "system", "accelerometer_rotation")
    print(f"原 user_rotation: {orig_rotation or '(未设置/null)'}，原 accelerometer_rotation: {orig_accel or '(未设置/null)'}")

    # 目标值与原值不同；原值未知时写 1
    target = "1" if orig_rotation == "0" else "0"

    ok = False
    observed = ""
    error = ""
    try:
        # 锁定方向，避免自动旋转立即改回
        if orig_accel != "0":
            put_setting(adb, "system", "accelerometer_rotation", "0")

        success, error = put_setting(adb, "system", "user_rotation", target)
        if not success:
            print(f"写入 user_rotation={target} 失败: {error}")
        observed = get_setting(adb, "system", "user_rotation")
        print(f"写入 user_rotation={target}，读回: {observed or '(未设置/null)'}")
        ok = success and observed == target
    finally:
        # 恢复原值：原值存在则写回，不存在（原为 null）则写 0 兜底，再恢复自动旋转开关
        restore_to = orig_rotation if orig_rotation else "0"
        put_setting(adb, "system", "user_rotation", restore_to)
        if orig_accel:
            put_setting(adb, "system", "accelerometer_rotation", orig_accel)
        restored = get_setting(adb, "system", "user_rotation")
        restored_accel = get_setting(adb, "system", "accelerometer_rotation")
        print(f"已恢复 user_rotation: {restored}，accelerometer_rotation: {restored_accel}")

    detail = f"旋转设置读回一致（{target}）" if ok else f"旋转设置读回不一致（写入 {target}，读回 {observed or 'null'}）"
    print(f"RESULT: {'PASS' if ok else 'FAIL'} ({detail})")
    print(json.dumps({
        "result": "pass" if ok else "fail",
        "original_rotation": orig_rotation,
        "original_accelerometer": orig_accel,
        "target": target,
        "readback": observed,
        "write_error": error,
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
