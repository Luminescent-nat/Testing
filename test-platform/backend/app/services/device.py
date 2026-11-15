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

# 执行器内部异常（含 adb 子进程无法启动）专用返回码。
# 与设备命令真实退出码以及超时 -1 区分：执行引擎据此按状态机 §2 行2
# 归类为 error（执行器无法启动/内部异常），而不是把启动失败误判为测试 fail。
INTERNAL_ERROR_RC = -2


class ADBDiscoveryError(RuntimeError):
    """ADB 发现失败（adb 不可执行/超时/非零退出）。

    发现动作遇到此异常必须向调用方返回 503，且不得把空列表当作“有效空扫描”去
    批量推进设备状态（尤其是 testing/排队设备不得被误置 offline）。
    """



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
            # 行2：执行器内部异常（含子进程无法启动）→ 专用返回码，摘要仅含异常类型；
            # 完整堆栈只进服务端日志，绝不把 str(exc) 随 stdout/stderr 持久化到记录。
            await self._kill_process(process)
            logger.exception("adb 执行器内部异常")
            return "", f"执行器内部异常（{type(e).__name__}）", INTERNAL_ERROR_RC
    
    async def get_device_list(self, timeout: Optional[int] = None) -> tuple:
        """获取设备列表并显式区分「ADB 失败」与「有效空扫描」。

        返回 (devices, error)；error 为 None 表示 adb 成功返回（可能设备为空），
        否则为失败摘要（调用方据此返回 503，而不是伪造空成功）。
        """
        stdout, stderr, returncode = await self._run_adb_command(["devices", "-l"], timeout=timeout)
        if returncode != 0:
            detail = (stderr or stdout or "").strip()[:200]
            return [], f"adb devices 返回码 {returncode}（{detail or '无输出'}）"

        devices = []
        lines = stdout.strip().split('\n')
        for line in lines[1:]:  # 跳过标题行
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                device_info = {"serial": parts[0], "state": parts[1]}
                for part in parts[2:]:
                    if ':' in part:
                        key, value = part.split(':', 1)
                        device_info[key] = value
                devices.append(device_info)
        return devices, None

    async def get_devices(self, timeout: Optional[int] = None) -> List[Dict[str, str]]:
        """获取设备列表（兼容旧语义：失败时返回空列表）。timeout 缺省使用 self.timeout。"""
        devices, _error = await self.get_device_list(timeout=timeout)
        return devices
    
    async def get_device_info(self, serial: str) -> Dict[str, Any]:
        """获取设备详细信息（各 adb 命令相互独立，并行执行缩短采集耗时）"""
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

        results = await asyncio.gather(
            self._run_adb_command(["-s", serial, "shell", "getprop", "ro.product.model"]),
            self._run_adb_command(["-s", serial, "shell", "getprop", "ro.product.brand"]),
            self._run_adb_command(["-s", serial, "shell", "getprop", "ro.build.version.release"]),
            self._run_adb_command(["-s", serial, "shell", "getprop", "ro.build.version.sdk"]),
            self._run_adb_command(["-s", serial, "shell", "getprop", "ro.product.cpu.abi"]),
            self._run_adb_command(["-s", serial, "shell", "wm", "size"]),
            self._run_adb_command(["-s", serial, "shell", "dumpsys", "battery"]),
        )
        # 每项结果为 (stdout, stderr, returncode)，这里只取 stdout 逐项解析
        model_out, brand_out, android_out, sdk_out, abi_out, size_out, battery_out = [
            r[0] for r in results
        ]

        # 型号
        if model_out:
            info["model"] = model_out.strip()

        # 品牌
        if brand_out:
            info["brand"] = brand_out.strip()

        # Android版本
        if android_out:
            info["android_version"] = android_out.strip()

        # SDK版本
        if sdk_out:
            info["sdk_version"] = sdk_out.strip()

        # CPU架构
        if abi_out:
            info["cpu_abi"] = abi_out.strip()

        # 分辨率
        if size_out:
            match = re.search(r'(\d+x\d+)', size_out)
            if match:
                info["resolution"] = match.group(1)

        # 电量
        if battery_out:
            match = re.search(r'level:\s*(\d+)', battery_out)
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

        探测失败语义（契约 scheduler-and-data §4）：
        - ADB 可执行失败、超时、非零退出属于「探测失败」，不是空设备列表：
          保持所有设备现状并记录安全错误，绝不批量 offline；
        - 只有成功且可信的 adb 扫描才可推进状态。

        状态推进规则：
        - 库里有但 adb 列表没有、且非 maintenance/testing 的设备 → offline；
          testing 的离开由设备锁持有者收尾处理，心跳不得覆盖；
        - 库里 offline 但 adb 列表里有 → online；
        - adb 列表里新出现的设备自动登记入库：status="online"、pc_identifier=""
          表示未分配（普通用户不可见，由 admin 分配），并顺带采集一次基本信息。
        返回 {"offline": n, "online": n, "registered": n} 状态变更计数。
        """
        try:
            result = await self.get_device_list(timeout=10)
        except Exception as exc:
            logger.error(
                "设备心跳：adb 探测异常（%s），保持全部设备现状", type(exc).__name__
            )
            return {"offline": 0, "online": 0, "registered": 0}
        if isinstance(result, tuple) and len(result) == 2:
            adb_devices, error = result
        else:
            # 兼容旧 Mock/注入对象未按 (devices, error) 契约返回的场景
            adb_devices, error = result if isinstance(result, list) else [], None
        if error is not None:
            logger.error(
                "设备心跳：adb 探测失败（%s），保持全部设备现状，不批量 offline",
                error,
            )
            return {"offline": 0, "online": 0, "registered": 0}

        online_serials = {d["serial"] for d in adb_devices if d.get("state") == "device"}

        result = await db.execute(select(Device))
        devices = result.scalars().all()
        known_serials = {device.serial_number for device in devices}
        changed = {"offline": 0, "online": 0, "registered": 0}
        now = datetime.now(timezone.utc)
        for device in devices:
            if device.status in ("maintenance", "testing"):
                # maintenance 由人工维护；testing 由设备锁持有者收尾推进，
                # 心跳均不得覆盖（契约 §4）
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

        # adb 在线但库中不存在的设备自动登记为未分配设备
        for serial in sorted(online_serials - known_serials):
            device_info: Dict[str, Any] = {}
            try:
                device_info = await self.get_device_info(serial)
            except Exception as exc:
                logger.warning("心跳登记：采集新设备 %s 基本信息失败: %s", serial, exc)
            db.add(Device(
                serial_number=serial,
                model=device_info.get("model"),
                brand=device_info.get("brand"),
                android_version=device_info.get("android_version"),
                sdk_version=device_info.get("sdk_version"),
                cpu_abi=device_info.get("cpu_abi"),
                resolution=device_info.get("resolution"),
                battery_level=device_info.get("battery_level"),
                status="online",
                pc_identifier="",
                last_seen_at=now,
            ))
            changed["registered"] += 1
            logger.info("心跳登记：新设备 %s 已自动入库（未分配）", serial)

        if changed["offline"] or changed["online"] or changed["registered"]:
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
            # 行2：执行器内部异常（含 adb 子进程无法启动）→ 专用返回码 + 安全摘要；
            # 完整堆栈仅进服务端日志，原始异常文本不进入返回值/记录。
            await self._kill_process(process)
            logger.exception("adb shell 执行器内部异常")
            return "", f"执行器内部异常（{type(e).__name__}）", INTERNAL_ERROR_RC
    
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
        """发现并同步设备（契约 §5）：只读同步，不改既有 owner/PC/version。

        - ADB 发现失败 → 抛 ADBDiscoveryError（调用方 503），且完全不触碰数据库，
          避免把 testing/排队设备批量误置 offline；
        - 既有设备：仅在非 testing/maintenance 时按探活推进 online/offline，
          owner_id / pc_identifier / version 一律不改；
        - 新设备：owner_id=None（待管理员分配）、pc_identifier=""，普通用户不认领。
        """
        adb_devices, error = await self._list_adb_devices()
        if error is not None:
            raise ADBDiscoveryError(error)

        updated_devices: List[Device] = []
        now = datetime.now(timezone.utc)
        for adb_device in adb_devices:
            serial = adb_device["serial"]
            state = adb_device.get("state", "offline")
            is_online = state == "device"

            device_info = await self.adb.get_device_info(serial)

            profile = {}
            if is_online:
                try:
                    profile = await self.profile_service.build_profile(serial)
                except Exception as exc:
                    logger.warning("采集设备 %s 画像失败: %s", serial, exc)

            result = await db.execute(select(Device).where(Device.serial_number == serial))
            existing_device = result.scalar_one_or_none()

            if existing_device:
                # 状态推进：testing/maintenance 不得被发现覆盖；owner/pc/version 不改
                if existing_device.status not in ("testing", "maintenance"):
                    desired = "online" if is_online else "offline"
                    if existing_device.status != desired:
                        existing_device.status = desired
                existing_device.model = device_info.get("model") or existing_device.model
                existing_device.brand = device_info.get("brand") or existing_device.brand
                existing_device.android_version = device_info.get("android_version") or existing_device.android_version
                existing_device.sdk_version = device_info.get("sdk_version") or existing_device.sdk_version
                existing_device.cpu_abi = device_info.get("cpu_abi") or existing_device.cpu_abi
                existing_device.resolution = device_info.get("resolution") or existing_device.resolution
                existing_device.battery_level = device_info.get("battery_level") or existing_device.battery_level
                existing_device.last_seen_at = now
                if profile:
                    existing_device.board = profile.get("board") or existing_device.board
                    existing_device.hardware = profile.get("hardware") or existing_device.hardware
                    existing_device.ddr_info = profile.get("ddr_info") or existing_device.ddr_info
                    existing_device.emmc_info = profile.get("emmc_info") or existing_device.emmc_info
                    existing_device.wifi_chip = profile.get("wifi_chip") or existing_device.wifi_chip
                    existing_device.bt_chip = profile.get("bt_chip") or existing_device.bt_chip
                    existing_device.eth_interfaces = profile.get("eth_interfaces") or existing_device.eth_interfaces
                    existing_device.features = profile.get("features") or existing_device.features
                updated_devices.append(existing_device)
            else:
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
                    owner_id=None,          # 新设备待管理员分配，普通用户不认领
                    pc_identifier="",
                    last_seen_at=now,
                    board=profile.get("board"),
                    hardware=profile.get("hardware"),
                    ddr_info=profile.get("ddr_info"),
                    emmc_info=profile.get("emmc_info"),
                    wifi_chip=profile.get("wifi_chip"),
                    bt_chip=profile.get("bt_chip"),
                    eth_interfaces=profile.get("eth_interfaces"),
                    features=profile.get("features"),
                )
                db.add(new_device)
                updated_devices.append(new_device)

        await db.flush()
        # 新设备补齐服务端默认值（id/created_at/version）
        for device in updated_devices:
            if device.id is None:
                await db.refresh(device)
        await db.commit()
        return updated_devices

    async def _list_adb_devices(self) -> tuple:
        """取 adb 设备列表并显式区分失败；兼容旧调用方/测试按 get_devices 注入的 Mock。

        真实 ADBService.get_device_list 返回 (devices, error) 元组；若注入对象未按新
        契约返回元组（例如既有测试只 mock 了 get_devices），回退到 get_devices()，
        视为无错误。这样既保证真实 ADB 失败可 503，又不破坏既有 Mock 用例。
        """
        try:
            result = await self.adb.get_device_list()
        except Exception:
            result = None
        if isinstance(result, tuple) and len(result) == 2:
            return result
        return await self.adb.get_devices(), None
    
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
