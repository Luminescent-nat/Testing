#!/usr/bin/env python3
"""
EMMC 稳定性/曲线测试运行器（PC 端）。

与 emmc_tools.py 的 stability 模式保持一致：
- 4 个场景（Seq_Read / Seq_Write / Rand_Read / Rand_Write）
- 默认 runtime=300s，rounds=1
- fio 参数在 perf 基础上增加 --write_bw_log / --write_iops_log --log_avg_msec=1000
- 生成 BW 趋势图与 IOPS 抖动散点图

用法示例:
    python emmc/host/emmc_stability_runner.py --serial 2492d300b0ae006c --mode seq_read --runtime 300 --rounds 1
"""

import argparse
import base64
import csv
import io
import json
import os
import re
import statistics
import sys
import time
import tempfile
from pathlib import Path

# Windows 默认终端可能是 GBK，强制 UTF-8 并替换不可编码字符
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

TOOLS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(TOOLS_ROOT))

from common.adb_runner import AdbRunner
from common.device_info import detect_arch, get_tool_path
from common.logger import setup_logger

logger = setup_logger("emmc_stability")


SCENARIO_CONFIG = {
    "seq_read": {"rw": "read", "bs": "128k", "name": "Seq_Read"},
    "seq_write": {"rw": "write", "bs": "128k", "name": "Seq_Write"},
    "rand_read": {"rw": "randread", "bs": "4k", "name": "Rand_Read"},
    "rand_write": {"rw": "randwrite", "bs": "4k", "name": "Rand_Write"},
}


def series_stats(values: list) -> dict:
    """计算序列统计指标。"""
    if not values:
        return {"mean": 0, "min": 0, "max": 0, "std": 0, "cv": 0}
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    cv = (std / mean * 100) if mean else 0.0
    return {
        "mean": round(mean, 2),
        "min": min(values),
        "max": max(values),
        "std": round(std, 2),
        "cv": round(cv, 2),
    }


def _find_log_file(output_dir: Path, mode: str, case: str, rnd: int, log_type: str) -> Path:
    """查找 fio 生成的 bw/iops 日志文件。"""
    # 标准命名：{mode}_{case}_{rnd}_{log_type}.log
    std = output_dir / f"{mode}_{case}_{rnd}_{log_type}.log"
    if std.exists():
        return std

    # fio 原始命名：{case_lower}_bw.log_{log_type}.{rnd}.log
    case_lower = case.lower().replace("_", "")
    pat = re.compile(
        rf"^{re.escape(case_lower)}_(?:bw|iops)\.log_{re.escape(log_type)}\.{rnd}\.log$",
        re.IGNORECASE,
    )
    for fp in output_dir.iterdir():
        if pat.match(fp.name):
            return fp
    return None


def generate_stability_chart(output_dir: Path, mode: str, case: str, rounds: int) -> Path:
    """生成稳定性曲线图，与 emmc_tools.py 风格一致。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("未安装 matplotlib，跳过生成曲线图")
        return None

    matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False

    plt.figure(figsize=(14, 6))

    # 左图：BW 趋势
    plt.subplot(1, 2, 1)
    plt.title(f"{case} BW 带宽表现")
    plt.xlabel("测试时间 (秒)")
    plt.ylabel("带宽 BW (MB/s)")

    for i in range(1, rounds + 1):
        bw_log = _find_log_file(output_dir, mode, case, i, "bw")
        if bw_log:
            try:
                times, bws = [], []
                with open(bw_log, "r", encoding="utf-8", errors="ignore") as csvf:
                    reader = csv.reader(csvf)
                    for row in reader:
                        if len(row) >= 2:
                            times.append(float(row[0].strip()) / 1000.0)
                            bws.append(float(row[1].strip()) / 1024.0)
                if times:
                    plt.plot(times, bws, label=f"Round {i}")
            except Exception as e:
                logger.error("带宽绘图异常 %s: %s", bw_log, e)

    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.6)

    # 右图：IOPS 抖动散点
    plt.subplot(1, 2, 2)
    plt.title(f"{case} IOPS 抖动分布")
    plt.xlabel("测试时间 (秒)")
    plt.ylabel("IOPS (次/秒)")

    for i in range(1, rounds + 1):
        iops_log = _find_log_file(output_dir, mode, case, i, "iops")
        if iops_log:
            try:
                times, iopss = [], []
                with open(iops_log, "r", encoding="utf-8", errors="ignore") as csvf:
                    reader = csv.reader(csvf)
                    for row in reader:
                        if len(row) >= 2:
                            times.append(float(row[0].strip()) / 1000.0)
                            iopss.append(float(row[1].strip()))
                if times:
                    plt.scatter(times, iopss, alpha=0.5, s=15, label=f"Round {i}")
            except Exception as e:
                logger.error("IOPS 绘图异常 %s: %s", iops_log, e)

    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    out_png = output_dir / f"{mode}_{case}_performance_drifts.png"
    plt.savefig(out_png, dpi=150)
    plt.close()
    logger.info("已生成: %s", out_png.name)
    return out_png


def file_to_base64(path: Path) -> str:
    """将图片转为 base64 data URL。"""
    if not path or not path.exists():
        return ""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def run_stability(adb: AdbRunner, args) -> dict:
    """执行 fio 稳定性测试并返回曲线数据与图表。"""
    adb.root()

    arch = detect_arch(adb)
    logger.info("设备架构: %s", arch)

    search_roots = [Path(__file__).resolve().parent.parent, TOOLS_ROOT]
    fio_path = get_tool_path("fio", arch, search_roots)
    remote_dir = "/data"
    remote_fio = f"{remote_dir}/fio"

    adb.shell(f"mkdir -p {remote_dir}", check=False)
    if not adb.push(fio_path, remote_fio):
        raise RuntimeError("推送 fio 失败")
    adb.shell(f"chmod +x {remote_fio}", check=False)

    cfg = SCENARIO_CONFIG.get(args.mode)
    if not cfg:
        raise ValueError(f"不支持的测试模式: {args.mode}")

    filename = args.filename or "/data/test"
    rounds = args.rounds
    runtime = args.runtime

    output_dir = Path(tempfile.gettempdir()) / f"emmc_stability_{adb.serial or 'unknown'}_{int(time.time())}"
    output_dir.mkdir(parents=True, exist_ok=True)

    round_summaries = []
    for i in range(1, rounds + 1):
        logger.info("执行 %s 稳定性测试 第 %d/%d 轮 (runtime=%ds)...", cfg["name"], i, rounds, runtime)
        log_prefix = f"/data/{args.mode}_{cfg['name']}_{i}"

        cmd_parts = [
            remote_fio,
            f"--filename={filename}",
            "--direct=1",
            "--ioengine=libaio",
            f"--runtime={runtime}",
            "--time_based=1",
            "--group_reporting=1",
            "--size=1G",
            f"--name={cfg['name']}",
            f"--rw={cfg['rw']}",
            "--iodepth=64",
            f"--bs={cfg['bs']}",
            "--thread",
            f"--write_bw_log={log_prefix}",
            f"--write_iops_log={log_prefix}",
            "--log_avg_msec=1000",
        ]

        start = time.time()
        res = adb.shell(" ".join(cmd_parts), timeout=runtime + 60, check=False)
        cost = time.time() - start

        if res is None or res.returncode != 0:
            err = res.stderr if res else "命令超时或未知异常"
            logger.error("稳定性测试失败: %s", err)
            raise RuntimeError(f"稳定性测试失败: {err}")

        # 拉取日志（fio 生成 {prefix}_bw.1.log / {prefix}_iops.1.log）
        remote_bw_log = f"{log_prefix}_bw.1.log"
        remote_iops_log = f"{log_prefix}_iops.1.log"
        local_bw = output_dir / f"{args.mode}_{cfg['name']}_{i}_bw.log"
        local_iops = output_dir / f"{args.mode}_{cfg['name']}_{i}_iops.log"

        adb.pull(remote_bw_log, local_bw)
        adb.pull(remote_iops_log, local_iops)
        adb.shell(f"rm {log_prefix}_*", check=False)

        # 解析曲线
        bw_points = []
        iops_points = []
        try:
            with open(local_bw, "r", encoding="utf-8", errors="ignore") as f:
                for row in csv.reader(f):
                    if len(row) >= 2:
                        bw_points.append({"t_ms": int(row[0]), "bw_kbps": int(row[1]), "bw_mbps": round(int(row[1]) / 1024, 2)})
        except Exception as e:
            logger.warning("解析 BW 日志异常: %s", e)

        try:
            with open(local_iops, "r", encoding="utf-8", errors="ignore") as f:
                for row in csv.reader(f):
                    if len(row) >= 2:
                        iops_points.append({"t_ms": int(row[0]), "iops": int(row[1])})
        except Exception as e:
            logger.warning("解析 IOPS 日志异常: %s", e)

        bw_values = [p["bw_kbps"] for p in bw_points]
        iops_values = [p["iops"] for p in iops_points]

        round_summaries.append({
            "round": i,
            "bw_stats_kbps": series_stats(bw_values),
            "bw_stats_mbps": series_stats([v / 1024 for v in bw_values]),
            "iops_stats": series_stats(iops_values),
            "curve": {
                "bw": bw_points,
                "iops": iops_points,
            },
            "cost_seconds": round(cost, 2),
        })

    # 生成图表
    chart_path = generate_stability_chart(output_dir, args.mode, cfg["name"], rounds)
    chart_base64 = file_to_base64(chart_path) if chart_path else ""

    result = {
        "status": "ok",
        "scenario": cfg["name"],
        "mode": args.mode,
        "runtime": runtime,
        "rounds": rounds,
        "rounds_data": round_summaries,
        "chart_path": str(chart_path) if chart_path else "",
        "chart_base64": chart_base64,
        "output_dir": str(output_dir),
    }

    logger.info("%s 稳定性测试完成，图表: %s", cfg["name"], chart_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="EMMC 稳定性/曲线测试运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--mode", type=str, required=True,
                        choices=list(SCENARIO_CONFIG.keys()),
                        help="稳定性测试模式")
    parser.add_argument("--runtime", type=int, default=300, help="每轮 fio 运行时长（秒），默认 300")
    parser.add_argument("--rounds", type=int, default=1, help="执行轮数，默认 1")
    parser.add_argument("--filename", type=str, default=None, help="fio 测试文件路径，默认 /data/test")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)
    run_stability(adb, args)


if __name__ == "__main__":
    main()
