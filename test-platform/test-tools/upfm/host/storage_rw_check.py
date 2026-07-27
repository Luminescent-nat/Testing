#!/usr/bin/env python3
"""
UPFM T1-17~T1-21 外置存储（TF 卡 / U 盘）识别、读写与目录检查运行器（PC 端）。

通过 `sm list-volumes public` 发现已挂载的外置卷（adb root 后执行），
按 disk id 前缀区分介质：TF 卡默认 public:179,（mmcblk），U 盘默认 public:8,（sd 盘）。
`sm` 无输出时回退到 `ls /mnt/media_rw/` 枚举挂载点（介质类型不可区分，仅作兜底）。

判定逻辑（--mode）：
- identify       ：发现匹配介质的挂载点 -> RESULT: PASS；未发现 -> 打印 NOT_FOUND 标记并 RESULT: FAIL
- rw             ：向挂载点 dd 写 1MB 随机数据 -> 设备端 md5sum 读回比对 -> 删除测试文件；
                   双侧 md5 一致 -> RESULT: PASS
- no-system-dirs ：ls 挂载点根目录，出现 system/vendor/data 任一顶层目录 -> RESULT: FAIL，否则 PASS

用法示例:
    python upfm/host/storage_rw_check.py --serial FE7G28V8TEST --mode identify --type tf
    python upfm/host/storage_rw_check.py --serial FE7G28V8TEST --mode rw --type udisk
"""

import argparse
import io
import json
import re
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

logger = setup_logger("storage_rw_check")

TEST_FILE = "upfm_test.bin"
SYSTEM_DIRS = {"system", "vendor", "data"}

# 介质默认 disk id 前缀（sm list-volumes 输出首列）
DEFAULT_PREFIX = {"tf": "public:179,", "udisk": "public:8,"}


def emit_result(ok: bool, detail: str, extra: dict):
    """输出最终判定标记与结构化 JSON 并以相应退出码结束。"""
    print(detail)
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print(json.dumps({"result": "pass" if ok else "fail", **extra}, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


def discover_volumes(adb: AdbRunner):
    """发现已挂载的 public 卷，返回 [(disk_id, mount_path), ...]。

    首选 `sm list-volumes public`（含介质 disk id）；无输出时回退
    `ls /mnt/media_rw/`（disk id 置空，表示介质类型未知）。
    """
    volumes = []
    res = adb.shell("sm list-volumes public", timeout=15, check=False)
    if res and res.stdout:
        for line in res.stdout.splitlines():
            m = re.match(r"^(\S+)\s+mounted\s+(\S+)", line.strip())
            if m:
                volumes.append((m.group(1), m.group(2)))

    if not volumes:
        res = adb.shell("ls /mnt/media_rw/", timeout=15, check=False)
        if res and res.returncode == 0:
            for name in res.stdout.split():
                if name:
                    volumes.append(("", f"/mnt/media_rw/{name}"))
            if volumes:
                logger.warning("sm 无输出，回退 /mnt/media_rw 枚举，介质类型不可区分")
    return volumes


def pick_mount(adb: AdbRunner, args):
    """按介质类型挑选挂载点，找不到返回 None。"""
    prefix = args.disk_id_prefix or DEFAULT_PREFIX[args.type]
    volumes = discover_volumes(adb)
    print("已发现的外置挂载卷:")
    for disk_id, path in volumes:
        print(f"  {disk_id or '(未知介质)'} -> {path}")
    if not volumes:
        print("  (无)")

    for disk_id, path in volumes:
        if disk_id.startswith(prefix):
            return path, volumes
    # sm 无 disk id 的兜底场景：无法区分介质时，单挂载点即认为是目标
    unknown = [p for d, p in volumes if not d]
    if len(volumes) == 1 and unknown:
        logger.warning("介质类型不可区分，唯一挂载点按目标介质处理: %s", unknown[0])
        return unknown[0], volumes
    return None, volumes


def shell_must(adb: AdbRunner, cmd: str, timeout: int = 60):
    """执行设备端命令并返回输出，失败抛异常。"""
    res = adb.shell(cmd, timeout=timeout, check=False)
    if res is None:
        raise RuntimeError(f"命令超时: {cmd}")
    return (res.stdout or "") + (res.stderr or ""), res.returncode


def main():
    parser = argparse.ArgumentParser(description="UPFM 外置存储识别/读写/目录检查运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--mode", type=str, required=True,
                        choices=["identify", "rw", "no-system-dirs"], help="检查模式")
    parser.add_argument("--type", type=str, required=True, choices=["tf", "udisk"], help="介质类型")
    parser.add_argument("--disk-id-prefix", type=str, default=None,
                        help="sm disk id 前缀（默认 tf=public:179, udisk=public:8,）")
    args = parser.parse_args()

    type_name = "TF 卡" if args.type == "tf" else "U 盘"
    adb = AdbRunner(args.serial)
    adb.root()  # /mnt/media_rw 需要 root 权限访问

    mount, _volumes = pick_mount(adb, args)
    if mount is None:
        # 未插入介质属【人工前置】未满足，输出 NOT_FOUND 标记
        print(f"NOT_FOUND: 未发现{type_name}挂载点（请先插入{type_name}后重跑本项）")
        print("RESULT: FAIL")
        print(json.dumps({"result": "fail", "reason": "not_found", "mode": args.mode,
                          "type": args.type}, ensure_ascii=False, indent=2))
        sys.exit(1)

    logger.info("目标挂载点: %s", mount)
    print(f"目标挂载点: {mount}")

    if args.mode == "identify":
        emit_result(True, f"{type_name}识别成功: {mount}",
                    {"mode": "identify", "type": args.type, "mount": mount})

    if args.mode == "no-system-dirs":
        out, rc = shell_must(adb, f"ls {mount}/")
        print(out.strip())
        top_dirs = set(out.split())
        leaked = sorted(top_dirs & SYSTEM_DIRS)
        ok = rc == 0 and not leaked
        emit_result(ok,
                    f"根目录{'不存在' if ok else '存在'}系统目录" + (f": {leaked}" if leaked else ""),
                    {"mode": "no-system-dirs", "type": args.type, "mount": mount,
                     "top_dirs": sorted(top_dirs), "system_dirs_found": leaked})

    # rw 模式：写 1MB 随机数据 -> md5 双侧比对 -> finally 清理
    remote_file = f"{mount}/{TEST_FILE}"
    try:
        out, rc = shell_must(adb, f"dd if=/dev/urandom of={remote_file} bs=1048576 count=1", timeout=60)
        print(out.strip())
        if rc != 0:
            emit_result(False, f"写入测试文件失败(rc={rc})",
                        {"mode": "rw", "type": args.type, "mount": mount})

        out_w, _ = shell_must(adb, f"md5sum {remote_file}")
        md5_write = out_w.split()[0] if out_w.split() else ""
        out_r, _ = shell_must(adb, f"dd if={remote_file} of=/dev/null bs=1048576 count=1 && md5sum {remote_file}")
        md5_read = out_r.strip().split()[-1] if out_r.strip().split() else ""
        print(f"写入后 md5: {md5_write}")
        print(f"读回后 md5: {md5_read}")
        ok = bool(md5_write) and md5_write == md5_read
        emit_result(ok, f"{type_name}读写校验{'一致' if ok else '不一致'}",
                    {"mode": "rw", "type": args.type, "mount": mount,
                     "md5_write": md5_write, "md5_read": md5_read})
    finally:
        adb.shell(f"rm -f {remote_file}", timeout=15, check=False)
        logger.info("已清理测试文件: %s", remote_file)


if __name__ == "__main__":
    main()
