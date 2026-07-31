#!/usr/bin/env python3
"""
UPFM T1-15 休眠时间验证运行器（PC 端）。

流程：记录原 screen_off_timeout -> 唤醒设备 -> 设为 15000ms -> 等待（默认 20s）->
dumpsys power 断言 mWakefulness 为休眠态 -> KEYCODE_WAKEUP 唤醒 -> finally 恢复原值。

判定：等待后 mWakefulness 为休眠态 -> RESULT: PASS；仍为 Awake -> RESULT: FAIL。
休眠态 = Asleep 或 Dozing：部分固件（A133P / Android 10 实测）息屏后进入
Dozing（屏幕已灭的浅休眠）而非 Asleep，两者都视为"已休眠"。
（常见干扰：stay_on_while_plugged_in 充电保持唤醒，runner 会前置读取并提示）。

任何异常路径都在 finally 中恢复原 screen_off_timeout 并尝试唤醒，保证设备状态复原。

用法示例:
    python upfm/host/sleep_check.py --serial FE7G28V8TEST --timeout-ms 15000 --wait-seconds 20
"""

import argparse
import io
import json
import sys
import time
from pathlib import Path

# Windows 默认终端可能是 GBK，强制 UTF-8 并替换不可编码字符
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

TOOLS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(TOOLS_ROOT))

from common.adb_runner import AdbRunner
from common.logger import setup_logger

logger = setup_logger("sleep_check")


def shell_out(adb: AdbRunner, cmd: str, timeout: int = 30) -> str:
    """执行设备端命令并返回 stdout（失败返回空串）。"""
    res = adb.shell(cmd, timeout=timeout, check=False)
    return res.stdout.strip() if res and res.stdout else ""


def get_wakefulness(adb: AdbRunner) -> str:
    """读取 dumpsys power 中的 mWakefulness 值。"""
    out = shell_out(adb, "dumpsys power | grep mWakefulness=")
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("mWakefulness="):
            return line.split("=", 1)[1].strip()
    return ""


def main():
    parser = argparse.ArgumentParser(description="UPFM 休眠时间验证运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--timeout-ms", type=int, default=15000, help="测试用 screen_off_timeout（毫秒）")
    parser.add_argument("--wait-seconds", type=int, default=20, help="设置后等待休眠的秒数（需大于 timeout-ms）")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)

    stay_awake = shell_out(adb, "settings get global stay_on_while_plugged_in")
    # 充电保持唤醒（userdebug 默认 7）会让设备永不休眠：测试期间临时置 0，结束恢复
    stay_awake_changed = stay_awake not in ("", "0", "null")
    if stay_awake_changed:
        print(f"stay_on_while_plugged_in={stay_awake}，测试期间临时置 0（结束后恢复）")

    original = shell_out(adb, "settings get system screen_off_timeout")
    print(f"原 screen_off_timeout: {original}")

    observed = ""
    ok = False
    try:
        if stay_awake_changed:
            adb.shell("settings put global stay_on_while_plugged_in 0", timeout=15, check=False)

        # 确保起始为唤醒态
        adb.shell("input keyevent KEYCODE_WAKEUP", timeout=15, check=False)
        time.sleep(1)

        adb.shell(f"settings put system screen_off_timeout {args.timeout_ms}", timeout=15, check=False)
        current = shell_out(adb, "settings get system screen_off_timeout")
        print(f"已设置 screen_off_timeout: {current}")

        logger.info("等待 %d 秒待设备休眠...", args.wait_seconds)
        time.sleep(args.wait_seconds)

        # 实测 A133P 在 timeout=15000 时约 15s 才进入 Dozing，时点临界易抖动：
        # 仍为 Awake 时每 5s 轮询一次，最多再给 15s 宽限
        observed = get_wakefulness(adb)
        grace_left = 15
        while observed == "Awake" and grace_left > 0:
            time.sleep(5)
            grace_left -= 5
            observed = get_wakefulness(adb)
        print(f"等待后 mWakefulness: {observed}")
        # Asleep 或 Dozing（A133P 息屏浅休眠）均视为已休眠
        ok = observed in ("Asleep", "Dozing")
    finally:
        # 唤醒并恢复原值，任何路径都保证设备状态复原
        adb.shell("input keyevent KEYCODE_WAKEUP", timeout=15, check=False)
        time.sleep(1)
        if original:
            adb.shell(f"settings put system screen_off_timeout {original}", timeout=15, check=False)
        if stay_awake_changed:
            adb.shell(f"settings put global stay_on_while_plugged_in {stay_awake}", timeout=15, check=False)
        restored = shell_out(adb, "settings get system screen_off_timeout")
        after_wake = get_wakefulness(adb)
        print(f"已恢复 screen_off_timeout: {restored}，唤醒后 mWakefulness: {after_wake}")

    print(f"RESULT: {'PASS' if ok else 'FAIL'} (休眠断言 mWakefulness 为 Asleep/Dozing，实测 {observed or '未知'})")
    print(json.dumps({
        "result": "pass" if ok else "fail",
        "original_timeout": original,
        "test_timeout_ms": args.timeout_ms,
        "wait_seconds": args.wait_seconds,
        "wakefulness_after_wait": observed,
        "wakefulness_after_wakeup": after_wake,
        "stay_on_while_plugged_in": stay_awake,
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
