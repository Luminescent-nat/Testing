#!/usr/bin/env python3
"""
UPFM T1-26 DDR 频率（静止态）验证运行器（PC 端，板型画像驱动）。

按板型 profile 的 clk_pattern 在 `cat /sys/kernel/debug/clk/clk_summary` 中匹配
DDR 时钟行，取速率列与 expected_freq 精确比对。
debug 节点需要 root 权限：读不到时自动尝试 adb root 后重读。

判定：任一匹配行速率 == 期望值 -> RESULT: PASS；否则 -> RESULT: FAIL；
未知识别板型 -> RESULT: FAIL。

用法示例:
    python upfm/host/ddr_freq_check.py --serial FE7G28V8TEST
    python upfm/host/ddr_freq_check.py --serial FE7G28V8TEST --expected 1056000000
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

from board_detect import BoardContext, shell_out
from common.logger import setup_logger

logger = setup_logger("ddr_freq_check")

CLK_SUMMARY = "cat /sys/kernel/debug/clk/clk_summary"


def read_clk_lines(ctx: BoardContext, pattern: str) -> list:
    """读取 clk_summary 中匹配 pattern 的行；读不到时尝试 adb root 后重读一次。"""
    out = shell_out(ctx.adb, f"{CLK_SUMMARY} | grep -i ddr", timeout=30)
    lines = [l.strip() for l in out.splitlines() if re.search(pattern, l, re.IGNORECASE)]
    if not lines:
        logger.info("未读到 DDR 时钟行，尝试 adb root 后重读")
        ctx.adb.root()
        out = shell_out(ctx.adb, f"{CLK_SUMMARY} | grep -i ddr", timeout=30)
        lines = [l.strip() for l in out.splitlines() if re.search(pattern, l, re.IGNORECASE)]
    return lines


def extract_rates(line: str) -> list:
    """从 clk_summary 行中提取速率列（时钟名后的第 3 个数值字段）。"""
    tokens = line.split()
    return tokens[3:4] if len(tokens) >= 4 else []


def main():
    parser = argparse.ArgumentParser(description="UPFM DDR 频率验证运行器（板型画像驱动）")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--expected", type=str, default=None, help="期望 DDR 频率覆盖值；缺省取板型 profile")
    args = parser.parse_args()

    ctx = BoardContext(args.serial)
    print(f"板型识别: {ctx.board_key or '(未知)'} (ro.mc.cpu={ctx.mc_cpu!r}, ro.product.device={ctx.product_device!r})")
    if not ctx.known:
        ctx.fail_unknown_board()

    ddr = ctx.profile["ddr"]
    expected = (args.expected if args.expected else ddr["expected_freq"]).strip()
    print(f"期望 DDR 频率: {expected} (clk 匹配模式: {ddr['clk_pattern']!r}, 参考时钟名 {ddr['clk_name']})")

    lines = read_clk_lines(ctx, ddr["clk_pattern"])
    print("匹配到的时钟行:")
    matched = []
    for line in lines:
        rates = extract_rates(line)
        print(f"  {line}")
        for rate in rates:
            matched.append({"line": line, "rate": rate, "ok": rate == expected})
    if not lines:
        print("  (无)")

    ok = any(m["ok"] for m in matched)
    if ok:
        detail = f"DDR 频率 {expected} 一致"
    elif not matched:
        detail = "未匹配到 DDR 时钟行或无法读取 clk_summary"
    else:
        detail = f"DDR 频率不一致（实测 {', '.join(m['rate'] for m in matched)}）"

    print(f"RESULT: {'PASS' if ok else 'FAIL'} ({detail})")
    print(json.dumps({
        "result": "pass" if ok else "fail",
        "board": ctx.board_key,
        "expected": expected,
        "matched": matched,
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
