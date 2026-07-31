#!/usr/bin/env python3
"""
UPFM T1-03/04/05 无线开关统一验证运行器（PC 端，板型画像驱动）。

--type 支持三种开关：
- wifi     ：svc wifi disable/enable + settings get global wifi_on 轮询读回
- bluetooth：先按板型 profile 判断 bluetooth.supported，False 直接 RESULT: SKIP；
             True 则 svc bluetooth disable/enable + bluetooth_on 轮询读回，
             读回不上时附带 dumpsys bluetooth_manager 状态便于归因
- airplane ：settings put global airplane_mode_on + am broadcast 读回，
             结束后恢复关闭态并重新打开 WiFi/蓝牙（蓝牙按 supported 决定）

判定：关/开两方向读回均符合 -> RESULT: PASS；否则 -> RESULT: FAIL；
蓝牙不支持 -> RESULT: SKIP（退出码 0）；未知识别板型 -> RESULT: FAIL。

用法示例:
    python upfm/host/toggle_check.py --serial FE7G28V8TEST --type wifi
"""

import argparse
import io
import json
import sys
import time
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

logger = setup_logger("toggle_check")


def poll_setting(ctx: BoardContext, ns: str, key: str, want: str, timeout_s: int = 15) -> str:
    """轮询 settings 值直到等于 want 或超时，返回最后一次读到的值。"""
    deadline = time.time() + timeout_s
    value = ""
    while True:
        value = shell_out(ctx.adb, f"settings get {ns} {key}")
        if value == want or time.time() >= deadline:
            return value
        time.sleep(1)


def check_wifi(ctx: BoardContext) -> dict:
    ctx.adb.shell("svc wifi disable", timeout=20, check=False)
    off = poll_setting(ctx, "global", "wifi_on", "0", timeout_s=10)
    print(f"wifi 关闭读回: wifi_on={off}")
    ctx.adb.shell("svc wifi enable", timeout=20, check=False)
    on = poll_setting(ctx, "global", "wifi_on", "1", timeout_s=20)
    print(f"wifi 开启读回: wifi_on={on}")
    ok = off == "0" and on == "1"
    return {"ok": ok, "detail": f"wifi_off={off} wifi_on={on}", "extra": {"wifi_off": off, "wifi_on": on}}


def check_bluetooth(ctx: BoardContext) -> dict:
    if not ctx.profile["bluetooth"].get("supported", False):
        reason = "板型 profile 标记蓝牙不支持（bluetooth.supported=false）"
        print(f"SKIP 原因: {reason}")
        return {"ok": None, "detail": reason, "skip": True, "extra": {"reason": reason}}

    ctx.adb.shell("svc bluetooth disable", timeout=20, check=False)
    off = poll_setting(ctx, "global", "bluetooth_on", "0", timeout_s=10)
    print(f"蓝牙关闭读回: bluetooth_on={off}")
    ctx.adb.shell("svc bluetooth enable", timeout=20, check=False)
    on = poll_setting(ctx, "global", "bluetooth_on", "1", timeout_s=20)
    print(f"蓝牙开启读回: bluetooth_on={on}")
    ok = off == "0" and on == "1"
    detail = f"bt_off={off} bt_on={on}"
    extra = {"bt_off": off, "bt_on": on}
    if not ok:
        # 附带协议栈状态便于归因（如固件缺陷导致的 CRASH/RESTART 循环）
        state = shell_out(ctx.adb, "dumpsys bluetooth_manager | head -8", timeout=20)
        print("dumpsys bluetooth_manager 摘要:")
        for line in state.splitlines():
            print(f"  {line}")
        extra["bluetooth_manager"] = state
    return {"ok": ok, "detail": detail, "extra": extra}


def check_airplane(ctx: BoardContext) -> dict:
    ctx.adb.shell("settings put global airplane_mode_on 1", timeout=15, check=False)
    ctx.adb.shell("am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true", timeout=15, check=False)
    on = poll_setting(ctx, "global", "airplane_mode_on", "1", timeout_s=10)
    print(f"飞行模式开启读回: airplane_mode_on={on}")

    # 恢复关闭态并重新打开无线，避免影响后续网络项
    ctx.adb.shell("settings put global airplane_mode_on 0", timeout=15, check=False)
    ctx.adb.shell("am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false", timeout=15, check=False)
    off = poll_setting(ctx, "global", "airplane_mode_on", "0", timeout_s=10)
    ctx.adb.shell("svc wifi enable", timeout=20, check=False)
    if ctx.profile["bluetooth"].get("supported", False):
        ctx.adb.shell("svc bluetooth enable", timeout=20, check=False)
    print(f"飞行模式关闭读回: airplane_mode_on={off}（已恢复 WiFi/蓝牙）")

    ok = on == "1" and off == "0"
    return {"ok": ok, "detail": f"airplane_on={on} airplane_off={off}",
            "extra": {"airplane_on": on, "airplane_off": off}}


CHECKS = {"wifi": check_wifi, "bluetooth": check_bluetooth, "airplane": check_airplane}


def main():
    parser = argparse.ArgumentParser(description="UPFM 无线开关统一验证运行器（板型画像驱动）")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--type", type=str, required=True, choices=list(CHECKS), help="开关类型")
    args = parser.parse_args()

    ctx = BoardContext(args.serial)
    print(f"板型识别: {ctx.board_key or '(未知)'} (ro.mc.cpu={ctx.mc_cpu!r}, ro.product.device={ctx.product_device!r})")
    if not ctx.known:
        ctx.fail_unknown_board()

    outcome = CHECKS[args.type](ctx)

    if outcome.get("skip"):
        print(f"RESULT: SKIP ({outcome['detail']})")
        print(json.dumps({"result": "skip", "board": ctx.board_key, "type": args.type,
                          **outcome["extra"]}, ensure_ascii=False, indent=2))
        sys.exit(0)

    ok = outcome["ok"]
    print(f"RESULT: {'PASS' if ok else 'FAIL'} ({args.type} 开关读回: {outcome['detail']})")
    print(json.dumps({"result": "pass" if ok else "fail", "board": ctx.board_key,
                      "type": args.type, **outcome["extra"]}, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
