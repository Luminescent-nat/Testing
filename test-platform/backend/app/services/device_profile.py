import re
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class DeviceProfileService:
    """设备画像服务，采集并归一化硬件指纹。"""

    def __init__(self):
        # 延迟导入，避免与 device.py 循环依赖
        from app.services.device import ADBService
        self.adb = ADBService()

    async def build_profile(self, serial: str) -> Dict[str, Any]:
        """为指定设备构建完整画像。"""
        profile = {
            "serial_number": serial,
            "board": None,
            "hardware": None,
            "ddr_info": {},
            "emmc_info": {},
            "wifi_chip": None,
            "bt_chip": None,
            "eth_interfaces": [],
            "features": []
        }

        # 主板与硬件平台
        profile["board"] = await self._get_prop(serial, "ro.product.board") or await self._get_prop(serial, "ro.board.platform")
        profile["hardware"] = await self._get_prop(serial, "ro.hardware")

        # DDR 信息
        profile["ddr_info"] = await self._get_ddr_info(serial)

        # EMMC 信息
        profile["emmc_info"] = await self._get_emmc_info(serial)

        # 网络接口与通信模组
        net_info = await self._get_network_info(serial)
        profile["eth_interfaces"] = net_info.get("eth_interfaces", [])
        profile["wifi_chip"] = net_info.get("wifi_chip")
        profile["bt_chip"] = net_info.get("bt_chip")

        # 设备能力特征
        features = []
        if net_info.get("has_wifi"):
            features.append("wifi")
        if net_info.get("has_bluetooth"):
            features.append("bluetooth")
        if net_info.get("has_ethernet"):
            features.append("ethernet")
        profile["features"] = features

        return profile

    async def _get_prop(self, serial: str, prop: str) -> Optional[str]:
        """获取单个 getprop 属性。"""
        try:
            stdout, _, _ = await self.adb.execute_shell(serial, f"getprop {prop}")
            value = stdout.strip()
            return value if value else None
        except Exception as exc:
            logger.warning("读取 %s 失败: %s", prop, exc)
            return None

    async def _get_ddr_info(self, serial: str) -> Dict[str, Any]:
        """采集 DDR 信息。"""
        info = {"total_mb": None, "available_mb": None, "freq_mhz": None}

        # 读取 /proc/meminfo
        stdout, _, _ = await self.adb.execute_shell(serial, "cat /proc/meminfo")
        if stdout:
            match = re.search(r"MemTotal:\s+(\d+)\s+kB", stdout)
            if match:
                info["total_mb"] = round(int(match.group(1)) / 1024)
            match = re.search(r"MemAvailable:\s+(\d+)\s+kB", stdout)
            if match:
                info["available_mb"] = round(int(match.group(1)) / 1024)

        # 尝试读取 DDR 频率节点
        freq_paths = [
            "/sys/class/devfreq/dmc/cur_freq",
            "/sys/class/devfreq/clk-dmc/cur_freq",
            "/sys/class/devfreq/dram/cur_freq"
        ]
        for path in freq_paths:
            stdout, _, _ = await self.adb.execute_shell(serial, f"cat {path}")
            if stdout.strip().isdigit():
                freq_hz = int(stdout.strip())
                info["freq_mhz"] = round(freq_hz / 1_000_000) if freq_hz > 1_000_000 else round(freq_hz / 1_000)
                break

        return info

    async def _get_emmc_info(self, serial: str) -> Dict[str, Any]:
        """采集 EMMC/存储 信息。兼容 mmcblk 命名、多节点、UFS 等场景。"""
        info = {"size_gb": None, "model": None, "health": None}

        # 1. 先找出设备上的 mmcblk 主节点（非分区）
        stdout, _, _ = await self.adb.execute_shell(serial, "ls /sys/block/")
        if stdout:
            block_devices = [d.strip() for d in stdout.split() if d.strip()]
            mmc_devices = [d for d in block_devices if re.match(r"mmcblk\d+$", d)]
        else:
            mmc_devices = []

        # 默认回退到 mmcblk0
        target_device = mmc_devices[0] if mmc_devices else "mmcblk0"

        # 2. 读取容量：优先 /sys/block/<dev>/size（单位 512B）
        stdout, _, _ = await self.adb.execute_shell(serial, f"cat /sys/block/{target_device}/size")
        if stdout and stdout.strip().isdigit():
            sectors = int(stdout.strip())
            info["size_gb"] = round(sectors * 512 / (1024 ** 3), 1)
        else:
            # 备选：/proc/partitions
            stdout, _, _ = await self.adb.execute_shell(serial, "cat /proc/partitions")
            if stdout:
                pattern = rf"\d+\s+\d+\s+(\d+)\s+{target_device}$"
                match = re.search(pattern, stdout, re.MULTILINE)
                if match:
                    blocks = int(match.group(1))
                    info["size_gb"] = round(blocks * 1024 / (1024 ** 3), 1)

        # 3. 读取型号：尝试 name/cid/manfid/oemid 等
        model_candidates = []
        for dev in mmc_devices or [target_device]:
            model_candidates.extend([
                f"/sys/block/{dev}/device/name",
                f"/sys/block/{dev}/device/cid",
                f"/sys/block/{dev}/device/manfid",
                f"/sys/block/{dev}/device/oemid",
                f"/sys/class/mmc_host/{dev.replace('blk', '')}/{dev}:0001/name",
                f"/sys/class/mmc_host/{dev.replace('blk', '')}/{dev}:0001/cid",
            ])

        # 部分 RK 平台 CID 在 mmc_host 下
        model_candidates.extend([
            "/sys/class/mmc_host/mmc0/mmc0:0001/name",
            "/sys/class/mmc_host/mmc0/mmc0:0001/cid",
            "/sys/class/mmc_host/mmc0/mmc0:0001/manfid",
        ])

        for path in model_candidates:
            stdout, _, _ = await self.adb.execute_shell(serial, f"cat {path}")
            value = stdout.strip()
            if value:
                info["model"] = value
                break

        # 4. 读取健康状态
        health_candidates = []
        for dev in mmc_devices or [target_device]:
            host = dev.replace("blk", "")
            health_candidates.extend([
                f"/sys/class/mmc_host/{host}/{dev}:0001/life_time",
                f"/sys/class/mmc_host/{host}/{dev}:0001/health",
                f"/sys/class/mmc_host/{host}/{dev}:0001/pre_eol_info",
            ])
        health_candidates.extend([
            "/sys/class/mmc_host/mmc0/mmc0:0001/life_time",
            "/sys/class/mmc_host/mmc0/mmc0:0001/health",
            "/sys/class/mmc_host/mmc0/mmc0:0001/pre_eol_info",
        ])

        for path in health_candidates:
            stdout, _, _ = await self.adb.execute_shell(serial, f"cat {path}")
            value = stdout.strip()
            if value:
                info["health"] = value
                break

        # 5. 兜底：用 df 获取 /data 分区容量，至少让用户看到存储大小
        if info["size_gb"] is None:
            stdout, _, _ = await self.adb.execute_shell(serial, "df -h /data")
            if stdout:
                lines = stdout.strip().split("\n")
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        size_str = parts[1]
                        info["size_gb"] = self._parse_size_str(size_str)

        return info

    def _parse_size_str(self, size_str: str) -> Optional[float]:
        """把 df -h 返回的容量字符串解析为 GB 数值。"""
        if not size_str:
            return None
        size_str = size_str.strip().upper()
        match = re.match(r"([\d.]+)([KMGTPEZY]?)B?", size_str)
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2)
        units = {"": 1 / 1024, "K": 1 / 1024, "M": 1 / 1024 ** 2, "G": 1, "T": 1024}
        return round(value * units.get(unit, 1), 1)

    async def _get_network_info(self, serial: str) -> Dict[str, Any]:
        """采集网络与通信模组信息。"""
        info = {
            "eth_interfaces": [],
            "wifi_chip": None,
            "bt_chip": None,
            "has_wifi": False,
            "has_bluetooth": False,
            "has_ethernet": False
        }

        # 读取 /sys/class/net 接口列表
        stdout, _, _ = await self.adb.execute_shell(serial, "ls /sys/class/net/")
        if stdout:
            interfaces = [iface.strip() for iface in stdout.split() if iface.strip()]
            eth_interfaces = [iface for iface in interfaces if iface.startswith("eth")]
            info["eth_interfaces"] = eth_interfaces
            info["has_ethernet"] = len(eth_interfaces) > 0
            info["has_wifi"] = "wlan0" in interfaces

        # 从 dmesg 识别 WiFi 芯片
        stdout, _, _ = await self.adb.execute_shell(serial, "dmesg | grep -i wifi | head -20")
        if stdout:
            # 常见芯片厂商关键词
            chip_keywords = ["broadcom", "rtl", "ath", "qcom", "mtk", "esp"]
            for keyword in chip_keywords:
                if keyword in stdout.lower():
                    # 提取包含芯片型号的关键词行
                    for line in stdout.split("\n"):
                        if keyword in line.lower():
                            info["wifi_chip"] = line.strip()[:100]
                            break
                    break

        # 从 dmesg 识别蓝牙芯片
        stdout, _, _ = await self.adb.execute_shell(serial, "dmesg | grep -i bluetooth | head -20")
        if stdout:
            chip_keywords = ["broadcom", "rtl", "ath", "qcom", "mtk", "esp"]
            for keyword in chip_keywords:
                if keyword in stdout.lower():
                    for line in stdout.split("\n"):
                        if keyword in line.lower():
                            info["bt_chip"] = line.strip()[:100]
                            break
                    break

        # 蓝牙服务状态
        stdout, _, _ = await self.adb.execute_shell(serial, "dumpsys bluetooth_manager | head -5")
        if stdout and ("enabled" in stdout.lower() or "state" in stdout.lower()):
            info["has_bluetooth"] = True

        return info

    async def detect_features(self, serial: str) -> List[str]:
        """快速检测设备能力特征。"""
        profile = await self.build_profile(serial)
        return profile.get("features", [])
