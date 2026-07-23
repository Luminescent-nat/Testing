#!/usr/bin/env python3
"""
通用 ADB 命令执行器。

供 test-tools 下各模块复用，统一处理：
- 带 serial 前缀的 adb 命令
- adb shell / push / pull / root
- 超时和错误兜底
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("adb_runner")


class AdbRunner:
    """PC 端 ADB 命令执行器。"""

    def __init__(self, serial: Optional[str] = None):
        self.serial = serial
        self._check_adb()

    def _check_adb(self):
        """确认 adb 命令可用。"""
        try:
            self.run("version")
            logger.info("ADB 命令行工具已就绪")
        except FileNotFoundError:
            logger.error("未找到 adb 命令，请确保 adb 已添加到系统环境变量")
            raise

    def _prefix(self) -> str:
        return f"adb -s {self.serial} " if self.serial else "adb "

    def run(self, cmd: str, timeout: Optional[int] = None, check: bool = False):
        """执行本地 adb 命令。"""
        full_cmd = f"{self._prefix()}{cmd}"
        try:
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            if check and result.returncode != 0:
                logger.debug("命令失败: %s\n%s", full_cmd, result.stderr.strip())
            return result
        except subprocess.TimeoutExpired:
            logger.error("命令执行超时: %s", full_cmd)
            return None

    def shell(self, cmd: str, timeout: Optional[int] = None, check: bool = False):
        """执行 adb shell 命令。"""
        return self.run(f'shell "{cmd}"', timeout=timeout, check=check)

    def push(self, src: str | Path, dest: str) -> bool:
        """推送文件到设备。"""
        res = self.run(f'push "{src}" "{dest}"', check=False)
        if res and res.returncode == 0:
            logger.info("推送成功: %s -> %s", src, dest)
            return True
        logger.error("推送失败: %s", res.stderr if res else "未知异常")
        return False

    def pull(self, src: str, dest: str | Path) -> bool:
        """从设备拉取文件。"""
        res = self.run(f'pull "{src}" "{dest}"', check=False)
        if res and res.returncode == 0:
            logger.info("拉取成功: %s -> %s", src, dest)
            return True
        logger.error("拉取失败: %s", res.stderr if res else "未知异常")
        return False

    def root(self, wait: bool = True) -> bool:
        """尝试 adb root 并等待设备重新上线。"""
        logger.info("尝试 adb root...")
        res = self.run("root", check=False)
        if not res or res.returncode != 0:
            logger.warning("adb root 失败或设备不支持 root，继续执行")
            return False

        if not wait:
            return True

        time.sleep(2)
        for _ in range(10):
            chk = self.run("shell echo ok", check=False)
            if chk and chk.returncode == 0 and "ok" in chk.stdout:
                logger.info("adb root 成功，设备已重新连接")
                return True
            time.sleep(1)

        logger.warning("adb root 后等待设备重新连接超时，继续执行")
        return False
