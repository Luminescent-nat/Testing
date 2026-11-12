#!/usr/bin/env python3
"""
设备信息检测工具。

- CPU 架构识别
- eMMC / 存储节点自动发现
- 工具路径按架构解析
"""

import logging
import re
from pathlib import Path
from typing import Optional

from common.adb_runner import AdbRunner

logger = logging.getLogger("device_info")


def detect_arch(adb: AdbRunner) -> str:
    """检测设备 CPU 架构，返回统一标识。"""
    # T-19：无元字符的简单命令用参数数组（远端仍作为单条 adb shell 命令传递）
    res = adb.shell(["getprop", "ro.product.cpu.abi"])
    if res and res.returncode == 0:
        arch = res.stdout.strip().lower()
        if "arm64" in arch or "aarch64" in arch:
            return "arm64-v8a"
        if "armeabi" in arch:
            return "armeabi-v7a"
        if "x86_64" in arch:
            return "x86_64"
        if "x86" in arch:
            return "x86"
        return arch
    logger.warning("无法识别架构，默认 arm64-v8a")
    return "arm64-v8a"


def detect_mmc_node(adb: AdbRunner, preferred: Optional[str] = None) -> str:
    """自动检测 eMMC 主节点。"""
    if preferred:
        return preferred

    # T-19：含远端管道的命令必须保持字符串形态（整条作为远端 adb shell
    # 单个参数传递，本地不解释 `|`；参数化 list 会被 shlex.join 引号化而失效）
    res = adb.shell("ls /sys/block/ | grep mmcblk")
    if res and res.returncode == 0:
        blocks = res.stdout.strip().split()
        main_blocks = [b for b in blocks if not re.search(r"p\d+|boot\d+|rpmb", b)]
        if main_blocks:
            return f"/dev/block/{main_blocks[0]}"

    logger.warning("未自动识别 eMMC 节点，回退到 /dev/block/mmcblk0")
    return "/dev/block/mmcblk0"


def get_tool_path(tool_name: str, arch: str, search_roots: Optional[list[Path]] = None) -> Path:
    """
    按架构查找本地工具二进制路径。

    搜索顺序：
    1. <search_root>/binaries/<arch>/<tool_name>
    2. <search_root>/<tool_name>
    """
    if search_roots is None:
        search_roots = [Path.cwd()]

    for base in search_roots:
        candidates = [
            base / "binaries" / arch / tool_name,
            base / tool_name,
        ]
        for cand in candidates:
            if cand.exists():
                return cand.resolve()

    raise FileNotFoundError(f"找不到工具: {tool_name} (架构 {arch})")
