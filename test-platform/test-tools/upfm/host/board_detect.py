#!/usr/bin/env python3
"""
UPFM 板型识别公共模块（PC 端）。

封装：adb 调用 -> 读取判别键（ro.mc.cpu 优先，ro.product.device 兜底）->
匹配 board_profiles.PROFILES，供各 runner import 使用。

用法:
    from board_detect import BoardContext
    ctx = BoardContext(serial)          # 识别板型并加载 profile
    if not ctx.known:
        ctx.fail_unknown_board()        # 打印全部实测值 + RESULT: FAIL 并退出
    print(ctx.board_key, ctx.profile["cpu"]["max_freq"])
"""

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
sys.path.insert(0, str(HOST_DIR))
sys.path.insert(0, str(TOOLS_ROOT))

from common.adb_runner import AdbRunner  # noqa: E402

import board_profiles  # noqa: E402

PROFILES = board_profiles.PROFILES


def shell_out(adb: AdbRunner, cmd: str, timeout: int = 15) -> str:
    """执行设备端命令并返回 stdout（失败返回空串）。"""
    res = adb.shell(cmd, timeout=timeout, check=False)
    return res.stdout.strip() if res and res.stdout else ""


def get_prop(adb: AdbRunner, prop: str) -> str:
    """读取单个系统属性（去除首尾空白，失败/为空返回空串）。"""
    out = shell_out(adb, f"getprop {prop}")
    return "" if out == "null" else out


class BoardContext:
    """板型识别上下文：持有 adb 句柄、判别键实测值与匹配到的 profile。"""

    def __init__(self, serial: str = None):
        self.adb = AdbRunner(serial)
        self.serial = serial
        self.mc_cpu = get_prop(self.adb, "ro.mc.cpu")
        self.product_device = get_prop(self.adb, "ro.product.device")
        self.board_key, self.profile = self._match()

    def _match(self):
        """ro.mc.cpu 优先匹配，ro.product.device 兜底。"""
        for key, profile in PROFILES.items():
            if self.mc_cpu and self.mc_cpu in profile["identify"].get("ro.mc.cpu", []):
                return key, profile
        for key, profile in PROFILES.items():
            if self.product_device and self.product_device in profile["identify"].get("ro.product.device", []):
                return key, profile
        return None, None

    @property
    def known(self) -> bool:
        return self.profile is not None

    def probe_all(self) -> dict:
        """采集未知识别时用于补 profile 的全部实测值。"""
        cpu_base = "/sys/devices/system/cpu/cpu0/cpufreq"
        touch_hint = shell_out(
            self.adb,
            "getevent -pl | grep -B2 -A8 'ABS_MT_SLOT\\|ABS_MT_TRACKING_ID' | "
            "grep -E 'add device|name:|ABS_MT_SLOT|ABS_MT_TRACKING_ID'",
            timeout=60,
        )
        return {
            "ro.mc.cpu": self.mc_cpu,
            "ro.product.device": self.product_device,
            "ro.product.board": get_prop(self.adb, "ro.product.board"),
            "ro.build.display.id": get_prop(self.adb, "ro.build.display.id"),
            "cpu_available_freqs": shell_out(self.adb, f"cat {cpu_base}/scaling_available_frequencies"),
            "cpu_max_freq": shell_out(self.adb, f"cat {cpu_base}/cpuinfo_max_freq"),
            "devfreq_nodes": shell_out(self.adb, "ls /sys/class/devfreq/"),
            "ddr_clk_lines": shell_out(self.adb, "cat /sys/kernel/debug/clk/clk_summary | grep -i ddr"),
            "touch_abs_mt": touch_hint,
            "bluetooth_features": shell_out(self.adb, "pm list features | grep -i bluetooth"),
            "mc_props": {p: get_prop(self.adb, p) for p in [
                "ro.mc.android_version", "ro.mc.cpu", "ro.mc.custom_api_version",
                "ro.mc.oem.version", "ro.mc.product", "ro.mc.version", "ro.mc.version_code",
            ]},
        }

    def fail_unknown_board(self):
        """未知识别板型：输出全部实测值 + RESULT: FAIL 并退出（绝不静默通过）。"""
        probed = self.probe_all()
        print("=" * 60)
        print("未知识别板型，请把以下实测值补入 board_profiles.py")
        print("=" * 60)
        print(json.dumps(probed, ensure_ascii=False, indent=2))
        print("RESULT: FAIL (未知识别板型，请把以上实测值补入 board_profiles)")
        print(json.dumps({
            "result": "fail",
            "reason": "unknown_board",
            "ro.mc.cpu": self.mc_cpu,
            "ro.product.device": self.product_device,
            "probed": probed,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
