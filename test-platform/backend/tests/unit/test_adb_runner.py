"""T-19 AdbRunner 契约单元测试（先于实现编写的红测）。

覆盖：
- 正常：真实 subprocess（临时 fake adb 脚本）捕获 argv，断言参数数组、serial 前缀、
  shell=False、last_command/last_error 记录；
- 边界：空命令/空参数/特殊字符/Windows 反斜杠路径；
- 异常：超时、非零退出码、adb 不存在；
- 元字符只作为数据传递，绝不触发本地 shell 解释；
- common.device_info 的调用同步为参数化形式。

实现前：adb_runner.py 使用 shell=True + 字符串拼接，本文件中关于
AdbRunner(adb=[...]) / last_command / last_error 的断言会失败。
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TEST_TOOLS_ROOT = Path(__file__).resolve().parents[3] / "test-tools"
if str(TEST_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_TOOLS_ROOT))

from common import device_info  # noqa: E402
from common.adb_runner import AdbRunner  # noqa: E402

FAKE_ADB_SOURCE = """\
import json
import os
import sys
import time

argv = sys.argv[1:]
print(json.dumps({"argv": argv}, ensure_ascii=False))
sleep_s = os.environ.get("FAKE_ADB_SLEEP")
if sleep_s:
    time.sleep(float(sleep_s))
code = os.environ.get("FAKE_ADB_EXIT")
if code:
    sys.exit(int(code))
extra = os.environ.get("FAKE_ADB_STDOUT")
if extra:
    print(extra)
"""


@pytest.fixture
def fake_adb(tmp_path):
    """真实可执行的假 adb：把收到的 argv 原样以 JSON 打印到 stdout。"""
    script = tmp_path / "fake adb.py"  # 路径带空格，验证参数数组不被拆裂
    script.write_text(FAKE_ADB_SOURCE, encoding="utf-8")
    return [sys.executable, str(script)]


def _captured_argv(result):
    assert result is not None
    return json.loads(result.stdout.splitlines()[0])["argv"]


def test_run_uses_real_subprocess_with_argv_list_and_serial_prefix(fake_adb):
    runner = AdbRunner(serial="SER-1", adb=fake_adb)
    result = runner.run(["version"])
    assert result.returncode == 0
    assert _captured_argv(result) == ["-s", "SER-1", "version"]
    assert isinstance(runner.last_command, list)
    assert runner.last_command == fake_adb + ["-s", "SER-1", "version"]
    assert runner.last_error is None


def test_subprocess_is_never_called_with_shell_true(monkeypatch, fake_adb):
    seen = {}
    real_run = subprocess.run

    def spy(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    runner = AdbRunner(adb=fake_adb)
    runner.run(["version"])
    runner.shell("echo ok")

    assert isinstance(seen["args"], list)
    assert all(isinstance(part, str) for part in seen["args"])
    assert seen["kwargs"].get("shell", False) is False


def test_run_str_is_shlex_parsed_and_windows_paths_are_preserved(fake_adb):
    runner = AdbRunner(adb=fake_adb)
    result = runner.run('install -r "C:\\tools\\my app.apk"')
    assert _captured_argv(result) == [
        "install",
        "-r",
        "C:\\tools\\my app.apk",
    ]


def test_shell_str_is_one_remote_argument_and_metacharacters_are_data(tmp_path, fake_adb):
    runner = AdbRunner(serial="SER-1", adb=fake_adb)
    marker = tmp_path / "INJECTED.txt"
    payload = f"echo ok; echo hacked > {marker.as_posix()} && echo $(id)"
    result = runner.shell(payload)

    assert _captured_argv(result) == ["-s", "SER-1", "shell", payload]
    # 本地 shell 若解释了该字符串，marker 会真实落盘
    assert not marker.exists()
    assert runner.last_error is None


def test_shell_list_is_joined_into_single_remote_command(fake_adb):
    runner = AdbRunner(adb=fake_adb)
    result = runner.shell(["getprop", "ro.product.cpu.abi"])
    assert _captured_argv(result) == ["shell", "getprop ro.product.cpu.abi"]


def test_run_special_characters_are_not_interpreted_locally(tmp_path, fake_adb):
    runner = AdbRunner(adb=fake_adb)
    marker = tmp_path / "side-effect.txt"
    tokens = ["echo", "a & b", f"; echo hacked > {marker.as_posix()}", "$(id)", "| cat", "`id`"]
    result = runner.run(tokens)
    assert _captured_argv(result) == tokens
    assert not marker.exists()


def test_push_pull_root_are_parameterized(fake_adb, tmp_path):
    runner = AdbRunner(serial="SER-1", adb=fake_adb)
    src = tmp_path / "a & b.bin"
    dest = "/sdcard/a; rm -rf /"

    assert runner.push(src, dest) is True
    assert runner.last_command == fake_adb + ["-s", "SER-1", "push", str(src), dest]
    assert runner.pull(dest, tmp_path / "out.bin") is True
    assert runner.last_command == fake_adb + [
        "-s", "SER-1", "pull", dest, str(tmp_path / "out.bin")
    ]
    assert runner.root(wait=False) is True
    assert runner.last_command == fake_adb + ["-s", "SER-1", "root"]


@pytest.mark.parametrize("cmd", ["", "   ", [], (), ["", "version"], ["version", "  "]])
def test_run_rejects_empty_commands(fake_adb, cmd):
    runner = AdbRunner(adb=fake_adb)
    with pytest.raises(ValueError):
        runner.run(cmd)


@pytest.mark.parametrize("cmd", ["", "   ", [], (), [""], ["echo", "  "]])
def test_shell_rejects_empty_commands(fake_adb, cmd):
    runner = AdbRunner(adb=fake_adb)
    with pytest.raises(ValueError):
        runner.shell(cmd)


def test_push_pull_reject_empty_arguments_and_record_error(fake_adb):
    runner = AdbRunner(adb=fake_adb)
    assert runner.push("", "/sdcard/x") is False
    assert runner.last_error
    assert runner.push("a", "") is False
    assert runner.pull("", "b") is False
    assert runner.pull("a", "") is False


def test_timeout_returns_none_and_is_tracked(monkeypatch, fake_adb):
    runner = AdbRunner(adb=fake_adb)
    monkeypatch.setenv("FAKE_ADB_SLEEP", "5")
    result = runner.run(["version"], timeout=1)
    assert result is None  # 保留调用方兼容的 None 语义
    assert "timeout" in runner.last_error
    assert runner.last_command[-1] == "version"


def test_nonzero_exit_code_is_tracked(monkeypatch, fake_adb):
    runner = AdbRunner(adb=fake_adb)
    monkeypatch.setenv("FAKE_ADB_EXIT", "3")
    result = runner.run(["version"], check=True)
    assert result.returncode == 3
    assert "3" in runner.last_error
    assert runner.last_command[-1] == "version"


def test_missing_adb_binary_raises_and_is_tracked():
    missing = "no-such-adb-binary-infra-tools-xyz"
    runner = AdbRunner(adb=missing, check_adb=False)
    with pytest.raises(FileNotFoundError):
        runner.run(["version"])
    assert "file-not-found" in runner.last_error
    with pytest.raises(FileNotFoundError):
        AdbRunner(adb=missing)


class _RecordingAdb:
    """记录 device_info 传给 AdbRunner.shell 的命令形态。"""

    def __init__(self, stdout):
        self.stdout = stdout
        self.commands = []

    def shell(self, cmd, **kwargs):
        self.commands.append(cmd)
        return SimpleNamespace(returncode=0, stdout=self.stdout, stderr="")


def test_device_info_detect_arch_uses_argument_list():
    adb = _RecordingAdb("armeabi-v7a\n")
    assert device_info.detect_arch(adb) == "armeabi-v7a"
    assert adb.commands == [["getprop", "ro.product.cpu.abi"]]


def test_device_info_remote_pipe_remains_single_command():
    adb = _RecordingAdb("mmcblk0\nmmcblk0p1\n")
    assert device_info.detect_mmc_node(adb) == "/dev/block/mmcblk0"
    assert adb.commands == ["ls /sys/block/ | grep mmcblk"]
