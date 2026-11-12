#!/usr/bin/env python3
"""
通用 ADB 命令执行器（T-19 重写：全参数化，本地永不使用 shell）。

供 test-tools 下各模块复用，统一处理：
- 带 serial 前缀的 adb 命令
- adb shell / push / pull / root
- 超时和错误兜底

T-19 契约（消除 shell 拼接）：
- 所有 subprocess.run 均使用参数数组 + ``shell=False``：本地 shell 永不解释
  ``; | & $ ` >`` 等元字符，它们只作为普通数据传给 adb 进程；
- ``run(cmd)`` 接受 ``list[str]``（显式参数数组，推荐）或 ``str``（内部用
  shlex 安全解析，拒绝空命令；Windows 反斜杠路径在解析前做转义保护）；
  现有调用方的字符串/引号/``" ".join(...)`` 写法全部保持兼容；
- ``shell(cmd)`` 接受 ``str`` 或 ``list[str]``：整条命令作为远端
  ``adb shell`` 的单个参数传递，本地不解释元字符；远端管道/分号等由设备端
  shell 解释，语义与重构前一致；
- ``push`` / ``pull`` / ``root`` 全部参数化；
- 超时返回 ``None``（保留调用方兼容语义）、``FileNotFoundError`` 原样抛出、
  非零退出码返回 ``CompletedProcess``；每次调用都记录到 ``last_command``
  （完整 argv 列表）与 ``last_error``（超时/文件缺失/非零码/非法命令），可追踪。
"""

import logging
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional, Sequence, Union

logger = logging.getLogger("adb_runner")

CmdType = Union[str, Sequence[Union[str, Path]]]


def normalise_tokens(cmd: CmdType) -> list[str]:
    """把调用方命令规范化为参数数组（list[str]）。

    - ``str``：shlex 解析。Windows 上先把反斜杠统一转义，避免
      ``shlex.split``（POSIX 规则）把 ``C:\\tools\\app.apk`` 吃成
      ``C:toolsapp.apk``；解析结果与原字符串逐字符等价。
    - ``list/tuple``：逐项转成字符串。
    - 拒绝空命令、空参数、非字符串项与 NUL 字节。
    """
    if isinstance(cmd, str):
        if not cmd.strip():
            raise ValueError("拒绝空命令")
        prepared = cmd.replace("\\", "\\\\") if os.name == "nt" else cmd
        try:
            tokens = shlex.split(prepared)
        except ValueError as exc:
            raise ValueError(f"无法解析命令: {exc}") from exc
    elif isinstance(cmd, (list, tuple)):
        tokens = [os.fspath(item) if isinstance(item, Path) else item for item in cmd]
    elif isinstance(cmd, os.PathLike):
        return normalise_tokens(os.fspath(cmd))
    else:
        raise ValueError(f"不支持的命令类型: {type(cmd).__name__}")

    if not tokens:
        raise ValueError("拒绝空命令")
    for token in tokens:
        if not isinstance(token, str):
            raise ValueError(f"命令参数必须是字符串: {token!r}")
        if not token.strip():
            raise ValueError(f"拒绝空参数: {token!r}")
        if "\x00" in token:
            raise ValueError("命令参数包含 NUL 字节")
    return tokens


class AdbRunner:
    """PC 端 ADB 命令执行器（本地 shell=False，远端 adb shell 语义保持）。"""

    def __init__(
        self,
        serial: Optional[str] = None,
        adb: Union[str, Sequence[str], None] = None,
        default_timeout: Optional[int] = None,
        check_adb: bool = True,
    ):
        """
        :param serial: 设备 serial；为空时不加 ``-s`` 前缀（与旧行为一致）。
        :param adb: adb 可执行文件；``str`` 或参数序列（如
            ``[sys.executable, "fake_adb.py"]``，便于测试）。默认 ``"adb"``。
        :param default_timeout: 未显式传 timeout 时的默认超时秒数。
        :param check_adb: 构造时是否执行 ``adb version`` 自检（原行为为是）。
        """
        self.serial = serial
        self._adb_prefix: list[str] = (
            [adb] if isinstance(adb, str) else list(adb) if adb is not None else ["adb"]
        )
        if not self._adb_prefix or any(not str(part).strip() for part in self._adb_prefix):
            raise ValueError("adb 可执行文件不能为空")
        self.default_timeout = default_timeout
        self.last_command: Optional[list[str]] = None
        self.last_error: Optional[str] = None
        if check_adb:
            self._check_adb()

    def _check_adb(self):
        """确认 adb 命令可用。"""
        try:
            self.run(["version"])
            logger.info("ADB 命令行工具已就绪")
        except FileNotFoundError:
            logger.error("未找到 adb 命令，请确保 adb 已添加到系统环境变量")
            raise

    def _prefix(self) -> str:
        """可读前缀（仅供日志/展示；执行一律走参数数组）。"""
        return " ".join(self._adb_prefix + (["-s", self.serial] if self.serial else []))

    def _full_argv(self, tokens: list[str]) -> list[str]:
        argv = list(self._adb_prefix)
        if self.serial:
            argv += ["-s", self.serial]
        return argv + tokens

    def run(
        self,
        cmd: CmdType,
        timeout: Optional[int] = None,
        check: bool = False,
    ):
        """执行本地 adb 命令。

        ``cmd`` 为 ``list[str]``（参数数组）或 ``str``（shlex 安全解析）。
        返回 ``CompletedProcess``；超时/其他 OSError 返回 ``None``（兼容旧语义）；
        adb 可执行文件缺失时抛出 ``FileNotFoundError``。
        ``check=True`` 仍只记录日志、不抛异常（保持旧行为），错误见 ``last_error``。
        """
        try:
            tokens = normalise_tokens(cmd)
        except ValueError as exc:
            self.last_command = None
            self.last_error = f"invalid-command: {exc}"
            logger.error("非法 ADB 命令: %s", exc)
            raise

        argv = self._full_argv(tokens)
        self.last_command = list(argv)
        self.last_error = None
        effective_timeout = timeout if timeout is not None else self.default_timeout
        try:
            result = subprocess.run(
                argv,
                shell=False,  # 本地永不经过 shell，元字符只作为数据
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            self.last_error = f"timeout: {getattr(exc, 'timeout', effective_timeout)}s"
            logger.error("命令执行超时: %s", self._prefix() + " " + " ".join(tokens))
            return None
        except FileNotFoundError as exc:
            self.last_error = f"file-not-found: {argv[0]}"
            logger.error("未找到 adb 命令: %s", argv[0])
            raise
        except OSError as exc:
            self.last_error = f"os-error: {exc}"
            logger.error("命令执行失败: %s (%s)", self._prefix(), exc)
            return None

        if result.returncode != 0:
            self.last_error = (
                f"exit-code: {result.returncode}: "
                f"{(result.stderr or '').strip()[:200]}"
            )
            if check:
                logger.debug("命令失败: %s\n%s", argv, result.stderr.strip())
        return result

    def shell(self, cmd: CmdType, timeout: Optional[int] = None, check: bool = False):
        """执行远端 adb shell 命令。

        ``cmd``（str 或 list[str]）整条作为 ``adb shell`` 的单个参数传递：
        本地不解释元字符（``shell=False``），远端 adb shell 语义保持
        （管道、分号、引号由设备端 shell 解释）。
        """
        if isinstance(cmd, str):
            if not cmd.strip():
                self.last_error = "invalid-command: 拒绝空命令"
                raise ValueError("拒绝空命令")
            remote = cmd
        elif isinstance(cmd, (list, tuple)):
            remote = shlex.join(normalise_tokens(cmd))
        else:
            self.last_error = f"invalid-command: 不支持的命令类型: {type(cmd).__name__}"
            raise ValueError(f"不支持的命令类型: {type(cmd).__name__}")
        return self.run(["shell", remote], timeout=timeout, check=check)

    def push(self, src: Union[str, Path], dest: Union[str, Path]) -> bool:
        """推送文件到设备（参数化，空参数拒绝并记录 last_error）。"""
        try:
            src_s, dest_s = self._required_path(src, "src"), self._required_path(dest, "dest")
            res = self.run(["push", src_s, dest_s], check=False)
        except ValueError as exc:
            self.last_error = f"invalid-command: {exc}"
            logger.error("推送参数非法: %s", exc)
            return False
        if res and res.returncode == 0:
            logger.info("推送成功: %s -> %s", src_s, dest_s)
            return True
        logger.error("推送失败: %s", res.stderr if res else self.last_error or "未知异常")
        return False

    def pull(self, src: Union[str, Path], dest: Union[str, Path]) -> bool:
        """从设备拉取文件（参数化，空参数拒绝并记录 last_error）。"""
        try:
            src_s, dest_s = self._required_path(src, "src"), self._required_path(dest, "dest")
            res = self.run(["pull", src_s, dest_s], check=False)
        except ValueError as exc:
            self.last_error = f"invalid-command: {exc}"
            logger.error("拉取参数非法: %s", exc)
            return False
        if res and res.returncode == 0:
            logger.info("拉取成功: %s -> %s", src_s, dest_s)
            return True
        logger.error("拉取失败: %s", res.stderr if res else self.last_error or "未知异常")
        return False

    @staticmethod
    def _required_path(value: Union[str, Path], name: str) -> str:
        text = os.fspath(value) if isinstance(value, Path) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"拒绝空参数: {name}")
        return text

    def root(self, wait: bool = True) -> bool:
        """尝试 adb root 并等待设备重新上线（参数化，不拼接字符串）。"""
        logger.info("尝试 adb root...")
        res = self.run(["root"], check=False)
        if not res or res.returncode != 0:
            logger.warning("adb root 失败或设备不支持 root，继续执行")
            return False

        if not wait:
            return True

        time.sleep(2)
        for _ in range(10):
            chk = self.shell("echo ok", check=False)
            if chk and chk.returncode == 0 and "ok" in chk.stdout:
                logger.info("adb root 成功，设备已重新连接")
                return True
            time.sleep(1)

        logger.warning("adb root 后等待设备重新连接超时，继续执行")
        return False
