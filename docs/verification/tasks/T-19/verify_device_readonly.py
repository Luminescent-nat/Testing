#!/usr/bin/env python3
"""T-19 真机只读验证：AdbRunner 全参数化调用当前连接的 ADB 设备。

只读命令（不 push / 不 pull / 不 root / 不改设备状态）：
1. adb -s <serial> version
2. adb -s <serial> shell getprop ro.product.cpu.abi
3. adb -s <serial> shell echo ok
4. device_info.detect_arch(...)（经 AdbRunner 参数数组调用）

同时做兼容性冒烟：编译 test-tools 全部 Python 文件，并以独立子进程（与真实用法
一致）导入 6 个高频调用方模块，确认重写未破坏既有 import。
"""
from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

SERIAL = "5c000c2834414751c9d"
REPO_ROOT = Path(__file__).resolve().parents[4]
TEST_TOOLS = REPO_ROOT / "test-platform" / "test-tools"
sys.path.insert(0, str(TEST_TOOLS))

from common.adb_runner import AdbRunner  # noqa: E402
from common import device_info  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def main() -> int:
    print(f"test-tools root = {TEST_TOOLS}")
    adb = AdbRunner(serial=SERIAL)
    print(f"AdbRunner 初始化自检通过, last_command={adb.last_command}")

    # 1) adb -s <serial> version
    res = adb.run(["version"])
    print(f"[raw] argv={adb.last_command}")
    print(f"[raw] returncode={res.returncode}")
    print(f"[raw] stdout:\n{res.stdout.strip()}")
    print(f"[raw] stderr:\n{res.stderr.strip()}")
    check(
        "adb -s SERIAL version",
        res.returncode == 0 and adb.last_command == adb._adb_prefix + ["-s", SERIAL, "version"],
        adb.last_error or "",
    )
    check("last_command 是参数数组(list)", isinstance(adb.last_command, list), str(type(adb.last_command)))

    # 2) adb -s <serial> shell getprop ro.product.cpu.abi（远端单参数）
    res = adb.shell("getprop ro.product.cpu.abi")
    print(f"[raw] argv={adb.last_command}")
    print(f"[raw] returncode={res.returncode}")
    print(f"[raw] stdout:\n{res.stdout.strip()}")
    check(
        "adb -s SERIAL shell getprop ro.product.cpu.abi",
        res.returncode == 0 and adb.last_command == adb._adb_prefix + ["-s", SERIAL, "shell", "getprop ro.product.cpu.abi"],
        adb.last_error or "",
    )
    abi = res.stdout.strip()

    # 3) adb -s <serial> shell echo ok
    res = adb.shell("echo ok")
    print(f"[raw] argv={adb.last_command}")
    print(f"[raw] returncode={res.returncode}")
    print(f"[raw] stdout:\n{res.stdout.strip()}")
    check("adb -s SERIAL shell echo ok", res.returncode == 0 and "ok" in res.stdout, adb.last_error or "")

    # 4) device_info.detect_arch 经 AdbRunner（远端只读 getprop）
    arch = device_info.detect_arch(adb)
    print(f"[raw] detect_arch -> {arch} (getprop 输出 {abi!r})")
    check("device_info.detect_arch 参数数组调用", bool(arch), arch)

    # 兼容性冒烟：编译 + 按调用方真实方式导入
    py_files = sorted(TEST_TOOLS.rglob("*.py"))
    compile_failed = []
    for path in py_files:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            compile_failed.append(f"{path.name}: {exc}")
    check(f"py_compile test-tools 全部 {len(py_files)} 个 .py", not compile_failed, "; ".join(compile_failed))

    host_modules = [
        "upfm/host/board_detect.py",
        "upfm/host/touch_points.py",
        "upfm/host/apk_install_check.py",
        "emmc/host/emmc_tester.py",
        "emmc/host/emmc_fio_runner.py",
        "emmc/host/emmc_stability_runner.py",
    ]
    # 逐模块独立子进程导入：与真实用法一致（每个脚本都是独立进程）。
    # 注意：这些脚本在 Windows 上于导入时重包装 sys.stdout；同一进程连导多个模块
    # 会触发旧包装被 GC 时关闭底层 buffer 的既有怪癖，与 T-19 重写无关。
    import_failed = []
    for rel in host_modules:
        path = TEST_TOOLS / rel
        code = (
            "import importlib.util, sys; "
            "spec = importlib.util.spec_from_file_location('smoke_mod', sys.argv[1]); "
            "mod = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(mod); print('IMPORT_OK')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(TEST_TOOLS),
        )
        print(f"[smoke] {rel}: exit={proc.returncode} stdout={proc.stdout.strip()!r}")
        if proc.returncode != 0 or "IMPORT_OK" not in proc.stdout:
            import_failed.append(f"{rel}: rc={proc.returncode} {(proc.stderr or '').strip()[-200:]}")
    check(f"独立子进程导入 {len(host_modules)} 个高频调用方模块", not import_failed, "; ".join(import_failed))

    print("\n================ 汇总 ================")
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\nRESULT: {'PASS' if not failed else 'FAIL'} ({len(results) - len(failed)}/{len(results)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
