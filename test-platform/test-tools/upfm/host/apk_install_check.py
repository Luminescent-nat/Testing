#!/usr/bin/env python3
"""
UPFM T1-11/T1-12 APK 安装/卸载验证运行器（PC 端）。

判定逻辑：
- install：adb install 安装测试 APK -> pm list packages 断言包名存在 -> RESULT: PASS；
  安装被拒且 --expect blocked（白名单定制机型预期行为）时同样 PASS。
- uninstall：pm uninstall -> pm list packages 断言包名消失 -> RESULT: PASS。
- 测试 APK 文件不存在（install）或包未安装（uninstall）时打印 RESULT: SKIP 并以 0 退出，
  表示"跳过"语义——平台 assertion 判定无法产出 skip 状态，该记录会显示为 error，
  输出中保留明确的 SKIP 说明，待放入测试 APK 后重跑。

用法示例:
    python upfm/host/apk_install_check.py --serial FE7G28V8TEST --action install \
        --apk "test-tools/upfm/assets/test_app.apk" --package com.example.testapp
"""

import argparse
import io
import json
import sys
from pathlib import Path

# Windows 默认终端可能是 GBK，强制 UTF-8 并替换不可编码字符
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

TOOLS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(TOOLS_ROOT))

from common.adb_runner import AdbRunner
from common.logger import setup_logger

logger = setup_logger("apk_install_check")


def is_package_installed(adb: AdbRunner, package: str) -> bool:
    """通过 pm list packages 判断包是否已安装。"""
    res = adb.shell(f"pm list packages {package}", timeout=30, check=False)
    if res is None:
        return False
    return f"package:{package}" in res.stdout


def emit_skip(reason: str, action: str, package: str):
    """输出明确的 SKIP 说明并以 0 退出（跳过语义，详见模块 docstring）。"""
    print(f"SKIP 原因: {reason}")
    print("请将测试 APK 放入 test-tools/upfm/assets/test_app.apk 后重跑本项")
    print("RESULT: SKIP")
    print(json.dumps({"result": "skip", "reason": reason, "action": action, "package": package},
                     ensure_ascii=False, indent=2))
    sys.exit(0)


def emit_result(ok: bool, detail: str, extra: dict):
    """输出最终判定标记与结构化 JSON。"""
    print(detail)
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print(json.dumps({"result": "pass" if ok else "fail", **extra}, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


def do_install(adb: AdbRunner, args):
    """安装测试 APK 并断言包名出现。"""
    apk_path = Path(args.apk)
    if not apk_path.is_file():
        emit_skip(f"测试 APK 不存在: {apk_path}", args.action, args.package)

    logger.info("安装 APK: %s", apk_path)
    res = adb.run(f'install -r "{apk_path}"', timeout=120, check=False)
    install_out = ((res.stdout or "") + (res.stderr or "")) if res else "adb install 超时"
    print(install_out.strip())

    installed = is_package_installed(adb, args.package)
    success = "Success" in install_out and installed

    if args.expect == "blocked":
        # 白名单定制机型：预期安装被拒，断言方向反转
        ok = not installed
        emit_result(ok,
                    f"expect=blocked：安装{'被拒(符合预期)' if ok else '成功(不符合预期)'}，包名{'存在' if installed else '不存在'}",
                    {"action": "install", "package": args.package, "installed": installed, "expect": "blocked"})
    else:
        emit_result(success,
                    f"安装{'成功' if success else '失败'}，pm list packages {'已找到' if installed else '未找到'} {args.package}",
                    {"action": "install", "package": args.package, "installed": installed})


def do_uninstall(adb: AdbRunner, args):
    """卸载测试 APK 并断言包名消失。"""
    apk_path = Path(args.apk)
    if not apk_path.is_file() and not is_package_installed(adb, args.package):
        emit_skip(f"测试 APK 不存在且包未安装: {apk_path}", args.action, args.package)

    if not is_package_installed(adb, args.package):
        # APK 资产存在但设备上无此包：无可卸载对象，按跳过处理
        emit_skip(f"包未安装，无可卸载对象: {args.package}", args.action, args.package)

    logger.info("卸载包: %s", args.package)
    res = adb.shell(f"pm uninstall {args.package}", timeout=60, check=False)
    uninstall_out = (res.stdout or "") if res else "pm uninstall 超时"
    print(uninstall_out.strip())

    installed = is_package_installed(adb, args.package)
    ok = "Success" in uninstall_out and not installed
    emit_result(ok,
                f"卸载{'成功' if ok else '失败'}，pm list packages {'仍存在' if installed else '已消失'}: {args.package}",
                {"action": "uninstall", "package": args.package, "installed": installed})


def main():
    parser = argparse.ArgumentParser(description="UPFM APK 安装/卸载验证运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--action", type=str, required=True, choices=["install", "uninstall"], help="动作")
    parser.add_argument("--apk", type=str, default="", help="测试 APK 本地路径")
    parser.add_argument("--package", type=str, required=True, help="测试 APK 包名")
    parser.add_argument("--expect", type=str, default="ok", choices=["ok", "blocked"],
                        help="install 断言方向：ok=预期安装成功；blocked=白名单机型预期安装被拒")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)
    if args.action == "install":
        do_install(adb, args)
    else:
        do_uninstall(adb, args)


if __name__ == "__main__":
    main()
