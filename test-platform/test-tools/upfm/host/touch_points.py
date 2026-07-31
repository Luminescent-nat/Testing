#!/usr/bin/env python3
"""
UPFM T1-16 触摸点数验证运行器（PC 端，板型画像驱动）。

不依赖设备名：解析 `getevent -pl` 全量输出，对所有含 ABS_MT 事件的输入设备，
优先取 ABS_MT_SLOT 的 max，无 SLOT 则取 ABS_MT_TRACKING_ID 的 max，触摸点数 = max + 1。
多设备时取最大点数作为实测值。

期望点数默认取板型 profile（board_detect 识别，换板无需改参），
--expected-points 可显式覆盖。

判定：实测点数 == 期望点数 -> RESULT: PASS；否则 RESULT: FAIL；
未发现触摸设备 -> RESULT: FAIL；未知识别板型 -> RESULT: FAIL。

用法示例:
    python upfm/host/touch_points.py --serial FE7G28V8TEST
    python upfm/host/touch_points.py --serial FE7G28V8TEST --expected-points 10
"""

import argparse
import io
import json
import re
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

logger = setup_logger("touch_points")


def parse_touch_devices(output: str):
    """解析 getevent -pl 输出，返回 [{name, points, source}, ...]。"""
    devices = []
    current = None
    for line in output.splitlines():
        m = re.match(r"add device \d+: (\S+)", line)
        if m:
            if current and (current.get("slot_max") is not None or current.get("tracking_max") is not None):
                devices.append(current)
            current = {"node": m.group(1), "name": "", "slot_max": None, "tracking_max": None}
            continue
        if current is None:
            continue
        m = re.match(r'\s+name:\s+"(.*)"', line)
        if m:
            current["name"] = m.group(1)
            continue
        m = re.search(r"ABS_MT_SLOT\s*:.*max (\d+)", line)
        if m:
            current["slot_max"] = int(m.group(1))
            continue
        m = re.search(r"ABS_MT_TRACKING_ID\s*:.*max (\d+)", line)
        if m:
            current["tracking_max"] = int(m.group(1))
    if current and (current.get("slot_max") is not None or current.get("tracking_max") is not None):
        devices.append(current)

    result = []
    for d in devices:
        if d.get("slot_max") is not None:
            result.append({"node": d["node"], "name": d["name"],
                           "points": d["slot_max"] + 1, "source": "ABS_MT_SLOT"})
        elif d.get("tracking_max") is not None:
            result.append({"node": d["node"], "name": d["name"],
                           "points": d["tracking_max"] + 1, "source": "ABS_MT_TRACKING_ID"})
    return result


def main():
    parser = argparse.ArgumentParser(description="UPFM 触摸点数验证运行器（板型画像驱动）")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--expected-points", type=str, default="",
                        help="期望触摸点数覆盖值；空串取板型 profile")
    args = parser.parse_args()

    ctx = BoardContext(args.serial)
    print(f"板型识别: {ctx.board_key or '(未知)'} (ro.mc.cpu={ctx.mc_cpu!r}, ro.product.device={ctx.product_device!r})")
    if not ctx.known:
        ctx.fail_unknown_board()

    expected = int(args.expected_points) if str(args.expected_points).strip() else int(ctx.profile["touch"]["expected_points"])

    res = ctx.adb.shell("getevent -pl", timeout=30, check=False)
    output = res.stdout if res and res.stdout else ""

    devices = parse_touch_devices(output)
    print("解析到的触摸设备:")
    for d in devices:
        print(f"  {d['node']} \"{d['name']}\" 点数={d['points']} (来源 {d['source']})")
    if not devices:
        print("  (未发现含 ABS_MT 的输入设备)")

    measured = max((d["points"] for d in devices), default=0)
    ok = measured == expected
    print(f"实测触摸点数: {measured}，期望: {expected}")
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print(json.dumps({
        "result": "pass" if ok else "fail",
        "board": ctx.board_key,
        "measured_points": measured,
        "expected_points": expected,
        "devices": devices,
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
