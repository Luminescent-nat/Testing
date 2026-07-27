#!/usr/bin/env python3
"""
UPFM T1-24/T1-25 GPU 频率验证运行器（PC 端）。

自动发现 /sys/class/devfreq/ 下的 *.gpu 节点（实机 rk3568 为 fde60000.gpu），
按 --mode 读取频率并与期望值比对：
- available：读 available_frequencies，与 --expected 的空格分隔频率列表按集合精确比对
  （顺序无关，逐项打印期望值与实际值）
- max      ：读 max_freq，与 --expected 单值精确比对

判定：一致 -> RESULT: PASS；不一致或未发现 GPU 节点 -> RESULT: FAIL。

用法示例:
    python upfm/host/gpu_freq_check.py --serial FE7G28V8TEST --mode max --expected 800000000
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

logger = setup_logger("gpu_freq_check")


def shell_out(adb: AdbRunner, cmd: str, timeout: int = 15) -> str:
    """执行设备端命令并返回 stdout（失败返回空串）。"""
    res = adb.shell(cmd, timeout=timeout, check=False)
    return res.stdout.strip() if res and res.stdout else ""


def discover_gpu_node(adb: AdbRunner) -> str:
    """发现 devfreq 下的 GPU 节点名（如 fde60000.gpu），找不到返回空串。"""
    out = shell_out(adb, "ls /sys/class/devfreq/")
    for name in out.split():
        if name.endswith(".gpu"):
            return name
    return ""


def main():
    parser = argparse.ArgumentParser(description="UPFM GPU 频率验证运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--mode", type=str, required=True, choices=["available", "max"], help="校验模式")
    parser.add_argument("--expected", type=str, required=True,
                        help="期望值：available 模式为空格分隔频率列表，max 模式为单值")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)
    node = discover_gpu_node(adb)
    print(f"GPU devfreq 节点: {node or '(未发现)'}")
    if not node:
        print("RESULT: FAIL (未发现 *.gpu devfreq 节点)")
        print(json.dumps({"result": "fail", "reason": "gpu_node_not_found"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    if args.mode == "available":
        actual_raw = shell_out(adb, f"cat /sys/class/devfreq/{node}/available_frequencies")
        expected_list = args.expected.split()
        actual_list = actual_raw.split()
        print(f"期望频率表: {' '.join(expected_list)}")
        print(f"实际频率表: {actual_raw}")
        ok = sorted(expected_list) == sorted(actual_list)
        detail = f"available_frequencies {'一致' if ok else '不一致'}"
        extra = {"mode": "available", "gpu_node": node,
                 "expected": expected_list, "actual": actual_list}
    else:
        actual = shell_out(adb, f"cat /sys/class/devfreq/{node}/max_freq")
        expected = args.expected.strip()
        print(f"期望 max_freq: {expected}")
        print(f"实际 max_freq: {actual}")
        ok = actual == expected
        detail = f"max_freq {'一致' if ok else '不一致'}"
        extra = {"mode": "max", "gpu_node": node, "expected": expected, "actual": actual}

    print(f"RESULT: {'PASS' if ok else 'FAIL'} ({detail})")
    print(json.dumps({"result": "pass" if ok else "fail", **extra}, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
