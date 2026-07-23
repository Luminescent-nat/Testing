import subprocess
import asyncio
import inspect
import re
import logging
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models import Device, User
from app.schemas import DeviceCreate, DeviceUpdate
from app.services.device_profile import DeviceProfileService

logger = logging.getLogger(__name__)


async def stream_process_output(process, timeout: float, on_output: Callable[[str], Any]) -> tuple:
    """逐行读取进程 stdout/stderr，每行实时回调（同步/异步回调均可）并累积完整输出。

    由 execute_shell / HostExecEngine 在需要实时输出时共用；超时/取消由调用方
    的 asyncio.wait_for 与异常处理负责（此函数内 wait_for 超时抛 TimeoutError，
    取消抛 CancelledError，均向上传播）。
    """
    stdout_parts: List[str] = []
    stderr_parts: List[str] = []

    async def _read_lines(stream, parts: List[str]):
        while True:
            raw = await stream.readline()
            if not raw:
                break
            line = raw.decode('utf-8', errors='ignore')
            parts.append(line)
            result = on_output(line)
            if inspect.isawaitable(result):
                await result

    await asyncio.wait_for(
        asyncio.gather(
            _read_lines(process.stdout, stdout_parts),
            _read_lines(process.stderr, stderr_parts),
        ),
        timeout=timeout
    )
    await process.wait()
    return "".join(stdout_parts), "".join(stderr_parts)


class ADBService:
    """ADB设备管理服务"""
    
    def __init__(self):
        self.timeout = 30
    
    @staticmethod
    async def _kill_process(process):
        """终止子进程：先 terminate，超时后 kill。

        Windows 上 terminate 即 TerminateProcess（等同于 kill），两者都保留
        是为了 POSIX 平台先给进程优雅退出的机会。
        """
        if process is None or process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("子进程 %s 无法终止", process.pid)

    async def _run_adb_command(self, command: List[str], timeout: Optional[int] = None) -> tuple:
        """执行ADB命令，timeout 缺省使用 self.timeout"""
        effective_timeout = timeout if timeout is not None else self.timeout
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                "adb", *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=effective_timeout
            )
            return stdout.decode('utf-8', errors='ignore'), stderr.decode('utf-8', errors='ignore'), process.returncode
        except asyncio.TimeoutError:
            # 超时必须杀掉底层 adb 子进程，否则进程残留
            await self._kill_process(process)
            return "", "Command timeout", -1
        except asyncio.CancelledError:
            # 外层任务取消时同样杀掉子进程再向上传播
            await self._kill_process(process)
            raise
        except Exception as e:
            await self._kill_process(process)
            return "", str(e), -1
    
    async def get_devices(self, timeout: Optional[int] = None) -> List[Dict[str, str]]:
        """获取设备列表，timeout 缺省使用 self.timeout"""
        stdout, stderr, returncode = await self._run_adb_command(["devices", "-l"], timeout=timeout)
        
        devices = []
        if returncode != 0:
            return devices
        
        lines = stdout.strip().split('\n')
        for line in lines[1:]:  # 跳过标题行
            if not line.strip():
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]
                
                # 解析其他信息
                device_info = {"serial": serial, "state": state}
                
                for part in parts[2:]:
                    if ':' in part:
                        key, value = part.split(':', 1)
                        device_info[key] = value
                
                devices.append(device_info)
        
        return devices
    
    async def get_device_info(self, serial: str) -> Dict[str, Any]:
        """获取设备详细信息"""
        info = {
            "serial_number": serial,
            "model": None,
            "brand": None,
            "android_version": None,
            "sdk_version": None,
            "cpu_abi": None,
            "resolution": None,
            "battery_level": None
        }
        
        # 获取型号
        stdout, _, _ = await self._run_adb_command(["-s", serial, "shell", "getprop", "ro.product.model"])
        if stdout:
            info["model"] = stdout.strip()
        
        # 获取品牌
        stdout, _, _ = await self._run_adb_command(["-s", serial, "shell", "getprop", "ro.product.brand"])
        if stdout:
            info["brand"] = stdout.strip()
        
        # 获取Android版本
        stdout, _, _ = await self._run_adb_command(["-s", serial, "shell", "getprop", "ro.build.version.release"])
        if stdout:
            info["android_version"] = stdout.strip()
        
        # 获取SDK版本
        stdout, _, _ = await self._run_adb_command(["-s", serial, "shell", "getprop", "ro.build.version.sdk"])
        if stdout:
            info["sdk_version"] = stdout.strip()
        
        # 获取CPU架构
        stdout, _, _ = await self._run_adb_command(["-s", serial, "shell", "getprop", "ro.product.cpu.abi"])
        if stdout:
            info["cpu_abi"] = stdout.strip()
        
        # 获取分辨率
        stdout, _, _ = await self._run_adb_command(["-s", serial, "shell", "wm", "size"])
        if stdout:
            match = re.search(r'(\d+x\d+)', stdout)
            if match:
                info["resolution"] = match.group(1)
        
        # 获取电量
        stdout, _, _ = await self._run_adb_command(["-s", serial, "shell", "dumpsys", "battery"])
        if stdout:
            match = re.search(r'level:\s*(\d+)', stdout)
            if match:
                info["battery_level"] = int(match.group(1))
        
        return info
    
    async def is_device_online(self, serial: str, timeout: Optional[int] = None) -> bool:
        """检查设备是否在线，timeout 缺省使用 self.timeout"""
        devices = await self.get_devices(timeout=timeout)
        for device in devices:
            if device["serial"] == serial and device["state"] == "device":
                return True
        return False

    async def heartbeat_check(self, db: AsyncSession) -> Dict[str, int]:
        """设备心跳：对比 adb 在线设备与数据库 Device 表，同步 online/offline 状态。

        - 库里有但 adb 列表没有、且非 maintenance 的设备 → offline（含 testing，
          只改设备状态，不动其正在运行的任务）；
        - 库里 offline 但 adb 列表里有 → online；
        - adb 列表里新出现的设备不自动入库（入库仍由手动 refresh 完成）。
        返回 {"offline": n, "online": n} 状态变更计数。
        """
        adb_devices = await self.get_devices(timeout=10)
        online_serials = {d["serial"] for d in adb_devices if d.get("state") == "device"}

        result = await db.execute(select(Device))
        changed = {"offline": 0, "online": 0}
        now = datetime.now(timezone.utc)
        for device in result.scalars().all():
            if device.status == "maintenance":
                continue
            if device.serial_number in online_serials:
                if device.status == "offline":
                    device.status = "online"
                    device.last_seen_at = now
                    changed["online"] += 1
            elif device.status != "offline":
                logger.warning(
                    "心跳检测：设备 %s 不在 adb 在线列表中，状态 %s -> offline",
                    device.serial_number, device.status,
                )
                device.status = "offline"
                changed["offline"] += 1

        if changed["offline"] or changed["online"]:
            await db.commit()
        return changed
    
    async def execute_shell(
        self,
        serial: str,
        command: str,
        timeout: int = 300,
        on_output: Optional[Callable[[str], Any]] = None
    ) -> tuple:
        """在设备上执行shell命令。

        on_output 为 None 时行为与原来完全一致（communicate 一次性读取）；
        不为 None 时逐行读取 stdout/stderr，每读到一行立即回调，同时累积完整
        输出，返回值结构不变。超时/取消杀进程语义两种路径一致。
        """
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                "adb", "-s", serial, "shell", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            if on_output is None:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                return stdout.decode('utf-8', errors='ignore'), stderr.decode('utf-8', errors='ignore'), process.returncode
            stdout_text, stderr_text = await stream_process_output(process, timeout, on_output)
            return stdout_text, stderr_text, process.returncode
        except asyncio.TimeoutError:
            # 超时必须杀掉底层 adb 子进程，否则进程残留
            await self._kill_process(process)
            return "", f"Timeout after {timeout} seconds", -1
        except asyncio.CancelledError:
            # 外层任务取消时同样杀掉子进程再向上传播
            await self._kill_process(process)
            raise
        except Exception as e:
            await self._kill_process(process)
            return "", str(e), -1
    
    async def push_file(self, serial: str, local_path: str, remote_path: str) -> tuple:
        """推送文件到设备"""
        stdout, stderr, returncode = await self._run_adb_command(
            ["-s", serial, "push", local_path, remote_path]
        )
        return stdout, stderr, returncode
    
    async def pull_file(self, serial: str, remote_path: str, local_path: str) -> tuple:
        """从设备拉取文件"""
        stdout, stderr, returncode = await self._run_adb_command(
            ["-s", serial, "pull", remote_path, local_path]
        )
        return stdout, stderr, returncode


class DeviceService:
    """设备业务服务"""

    def __init__(self):
        self.adb = ADBService()
        self.profile_service = DeviceProfileService()

    async def discover_devices(self, db: AsyncSession, user: User, pc_identifier: str) -> List[Device]:
        """发现并同步设备，同时更新硬件画像。"""
        # 获取ADB设备列表
        adb_devices = await self.adb.get_devices()

        updated_devices = []
        for adb_device in adb_devices:
            serial = adb_device["serial"]
            state = adb_device.get("state", "offline")
            is_online = state == "device"

            # 获取基础信息
            device_info = await self.adb.get_device_info(serial)

            # 设备在线时采集完整硬件画像
            profile = {}
            if is_online:
                try:
                    profile = await self.profile_service.build_profile(serial)
                except Exception as exc:
                    logger.warning("采集设备 %s 画像失败: %s", serial, exc)

            # 查询现有记录
            result = await db.execute(select(Device).where(Device.serial_number == serial))
            existing_device = result.scalar_one_or_none()

            if existing_device:
                # 更新现有记录
                existing_device.status = "online" if is_online else "offline"
                existing_device.model = device_info.get("model") or existing_device.model
                existing_device.brand = device_info.get("brand") or existing_device.brand
                existing_device.android_version = device_info.get("android_version") or existing_device.android_version
                existing_device.sdk_version = device_info.get("sdk_version") or existing_device.sdk_version
                existing_device.cpu_abi = device_info.get("cpu_abi") or existing_device.cpu_abi
                existing_device.resolution = device_info.get("resolution") or existing_device.resolution
                existing_device.battery_level = device_info.get("battery_level") or existing_device.battery_level
                existing_device.last_seen_at = datetime.now(timezone.utc)

                # 更新硬件画像
                if profile:
                    existing_device.board = profile.get("board") or existing_device.board
                    existing_device.hardware = profile.get("hardware") or existing_device.hardware
                    existing_device.ddr_info = profile.get("ddr_info") or existing_device.ddr_info
                    existing_device.emmc_info = profile.get("emmc_info") or existing_device.emmc_info
                    existing_device.wifi_chip = profile.get("wifi_chip") or existing_device.wifi_chip
                    existing_device.bt_chip = profile.get("bt_chip") or existing_device.bt_chip
                    existing_device.eth_interfaces = profile.get("eth_interfaces") or existing_device.eth_interfaces
                    existing_device.features = profile.get("features") or existing_device.features

                # 如果设备没有所有者，绑定当前用户
                if existing_device.owner_id is None:
                    existing_device.owner_id = user.id
                    existing_device.pc_identifier = pc_identifier

                updated_devices.append(existing_device)
            else:
                # 创建新记录
                new_device = Device(
                    serial_number=serial,
                    model=device_info.get("model"),
                    brand=device_info.get("brand"),
                    android_version=device_info.get("android_version"),
                    sdk_version=device_info.get("sdk_version"),
                    cpu_abi=device_info.get("cpu_abi"),
                    resolution=device_info.get("resolution"),
                    battery_level=device_info.get("battery_level"),
                    status="online" if is_online else "offline",
                    owner_id=user.id,
                    pc_identifier=pc_identifier,
                    last_seen_at=datetime.now(timezone.utc),
                    board=profile.get("board"),
                    hardware=profile.get("hardware"),
                    ddr_info=profile.get("ddr_info"),
                    emmc_info=profile.get("emmc_info"),
                    wifi_chip=profile.get("wifi_chip"),
                    bt_chip=profile.get("bt_chip"),
                    eth_interfaces=profile.get("eth_interfaces"),
                    features=profile.get("features")
                )
                db.add(new_device)
                updated_devices.append(new_device)

        await db.commit()
        return updated_devices
    
    async def get_devices_for_user(self, db: AsyncSession, user: User, pc_identifier: str) -> List[Device]:
        """获取用户可见的设备列表"""
        if user.role == "admin":
            # 管理员可以看到所有设备
            result = await db.execute(select(Device))
        else:
            # 普通用户只能看到本机设备
            result = await db.execute(
                select(Device).where(Device.pc_identifier == pc_identifier)
            )
        
        return result.scalars().all()
    
    async def get_device_by_serial(self, db: AsyncSession, serial: str) -> Optional[Device]:
        """通过序列号获取设备"""
        result = await db.execute(select(Device).where(Device.serial_number == serial))
        return result.scalar_one_or_none()
    
    async def update_device_status(self, db: AsyncSession, device_id: int, status: str):
        """更新设备状态"""
        result = await db.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if device:
            device.status = status
            await db.commit()
    
    async def check_device_access(self, db: AsyncSession, user: User, device: Device, pc_identifier: str) -> bool:
        """检查用户是否有权限访问设备"""
        if user.role == "admin":
            return True
        return device.pc_identifier == pc_identifier
