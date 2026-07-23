"""SQLite 数据库在线备份脚本。

使用 sqlite3 标准库的 backup API，在数据库被占用（服务运行中）时也能
安全备份，无需停服。备份文件写入目标目录，按时间戳命名，并自动清理
旧备份，只保留最近 N 份（默认 30）。

用法：
    python scripts/backup_db.py
    python scripts/backup_db.py --source /path/to/test_platform.db \
        --dest-dir /path/to/backups --keep 30

默认参数（相对于本脚本所在位置）：
    --source    <test-platform>/backend/test_platform.db
    --dest-dir  <test-platform>/backups
    --keep      30

定时挂载示例：

Linux crontab（每天凌晨 3 点备份）：
    0 3 * * * cd /opt/test-platform && /usr/bin/python3 scripts/backup_db.py >> backups/backup_cron.log 2>&1

Docker 部署时备份容器卷里的库（宿主机直接执行，source 指向挂载目录）：
    0 3 * * * cd /opt/test-platform && /usr/bin/python3 scripts/backup_db.py --source data/test_platform.db >> backups/backup_cron.log 2>&1

Windows 计划任务（每天凌晨 3 点，在任务计划程序中新建任务，或用 schtasks）：
    schtasks /create /tn "TestPlatformBackup" /tr "D:\\MCTEST\\test-platform\\.venv\\Scripts\\python.exe D:\\MCTEST\\test-platform\\scripts\\backup_db.py" /sc daily /st 03:00

Windows / Linux 通用，仅依赖标准库。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_KEEP = 30

# 默认路径基于本脚本位置推导：<test-platform>/scripts/backup_db.py
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = _ROOT / "backend" / "test_platform.db"
DEFAULT_DEST_DIR = _ROOT / "backups"


def backup_database(source: Path, dest_dir: Path, keep: int = DEFAULT_KEEP) -> Path:
    """将 source 在线备份到 dest_dir，并清理超出保留数量的旧备份。

    返回备份文件路径。源文件不存在时抛出 FileNotFoundError。
    """
    source = Path(source)
    dest_dir = Path(dest_dir)

    if not source.exists():
        raise FileNotFoundError(f"源数据库不存在: {source}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{source.stem}_{timestamp}.db"
    # 同一秒内重复执行时避免覆盖
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{source.stem}_{timestamp}_{counter}.db"
        counter += 1

    # 以只读方式打开源库，通过 backup API 在线拷贝（服务运行中也可安全执行）
    src_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    _cleanup_old_backups(dest_dir, source.stem, keep)
    return dest


def _cleanup_old_backups(dest_dir: Path, stem: str, keep: int) -> list[Path]:
    """删除超出 keep 数量的最旧备份，返回被删除的文件列表。

    备份文件名以时间戳命名（stem_YYYYMMDD_HHMMSS*.db），按文件名排序
    即按时间排序。
    """
    backups = sorted(dest_dir.glob(f"{stem}_*.db"))
    removed = []
    for old in backups[:-keep] if keep > 0 else backups:
        old.unlink()
        removed.append(old)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQLite 数据库在线备份（保留最近 N 份）")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help=f"源数据库路径（默认: {DEFAULT_SOURCE}）")
    parser.add_argument("--dest-dir", type=Path, default=DEFAULT_DEST_DIR,
                        help=f"备份输出目录（默认: {DEFAULT_DEST_DIR}）")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                        help=f"保留最近备份份数（默认: {DEFAULT_KEEP}）")
    args = parser.parse_args(argv)

    try:
        dest = backup_database(args.source, args.dest_dir, args.keep)
    except FileNotFoundError as exc:
        print(f"备份失败: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(f"备份失败: SQLite 错误: {exc}", file=sys.stderr)
        return 1

    print(f"备份完成: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
