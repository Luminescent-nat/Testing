#!/usr/bin/env python3
"""
UPFM T1-24/T1-25 GPU 频率验证运行器（PC 端，板型画像驱动）。

期望值默认取板型 profile（board_detect 识别），--expected 可覆盖。
板型 profile 标记 gpu.supported=false（如 A133P，用例注明不支持查看频率表，
实机 /sys/class/devfreq 无 *.gpu 节点）时输出 RESULT: SKIP 并以 0 退出。

按 --mode 读取频率并与期望值比对：
- available：读 available_frequencies，与期望值按集合精确比对（顺序无关）
- max      ：读 max_freq，与期望单值精确比对

判定：一致 -> RESULT: PASS；不一致或 supported=true 但未发现 GPU 节点 -> RESULT: FAIL；
未知识别板型 -> RESULT: FAIL。

用法示例:
    python upfm/host/gpu_freq_check.py --serial FE7G28V8TEST --mode max
    python upfm/host/gpu_freq_check.py --serial FE7G28V8TEST --mode max --expected 800000000
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

logger = setup_logger("gpu_freq_check")


def discover_gpu_node(ctx: BoardContext) -> str:
    """发现 devfreq 下的 GPU 节点名（如 fde60000.gpu），找不到返回空串。"""
    out = shell_out(ctx.adb, "ls /sys/class/devfreq/")
    for name in out.split():
        if name.endswith(".gpu"):
            return name
    return ""


def main():
    parser = argparse.ArgumentParser(description="UPFM GPU 频率验证运行器（板型画像驱动）")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--mode", type=str, required=True, choices=["available", "max"], help="校验模式")
    parser.add_argument("--expected", type=str, default=None,
                        help="期望值覆盖：available 为空格分隔频率列表，max 为单值；缺省取板型 profile")
    args = parser.parse_args()

    ctx = BoardContext(args.serial)
    print(f"板型识别: {ctx.board_key or '(未知)'} (ro.mc.cpu={ctx.mc_cpu!r}, ro.product.device={ctx.product_device!r})")
    if not ctx.known:
        ctx.fail_unknown_board()

    gpu = ctx.profile["gpu"]
    if not gpu.get("supported", False):
        reason = "板型 profile 标记不支持查看 GPU 频率表（gpu.supported=false）"
        print(f"SKIP 原因: {reason}")
        print(f"RESULT: SKIP ({reason})")
        print(json.dumps({"result": "skip", "board": ctx.board_key, "reason": reason},
                         ensure_ascii=False, indent=2))
        sys.exit(0)

    node = discover_gpu_node(ctx)
    print(f"GPU devfreq 节点: {node or '(未发现)'} (发现方式: {gpu.get('discovery', 'devfreq *.gpu')})")
    if not node:
        print("RESULT: FAIL (profile 标记支持 GPU 频率表，但未发现 *.gpu devfreq 节点)")
        print(json.dumps({"result": "fail", "board": ctx.board_key, "reason": "gpu_node_not_found"},
                         ensure_ascii=False, indent=2))
        sys.exit(1)

    if args.mode == "available":
        expected_raw = args.expected if args.expected else gpu["available_freqs"]
        actual_raw = shell_out(ctx.adb, f"cat /sys/class/devfreq/{node}/available_frequencies")
        expected_list = expected_raw.split()
        actual_list = actual_raw.split()
        print(f"期望频率表: {' '.join(expected_list)}")
        print(f"实际频率表: {actual_raw}")
        ok = bool(actual_list) and sorted(expected_list) == sorted(actual_list)
        detail = f"available_frequencies {'一致' if ok else '不一致'}"
        extra = {"mode": "available", "gpu_node": node,
                 "expected": expected_list, "actual": actual_list}
    else:
        expected = (args.expected if args.expected else gpu["max_freq"]).strip()
        actual = shell_out(ctx.adb, f"cat /sys/class/devfreq/{node}/max_freq")
        print(f"期望 max_freq: {expected}")
        print(f"实际 max_freq: {actual}")
        ok = bool(actual) and actual == expected
        detail = f"max_freq {'一致' if ok else '不一致'}"
        extra = {"mode": "max", "gpu_node": node, "expected": expected, "actual": actual}

    print(f"RESULT: {'PASS' if ok else 'FAIL'} ({detail})")
    print(json.dumps({"result": "pass" if ok else "fail", "board": ctx.board_key, **extra},
                     ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
