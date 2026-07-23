#!/usr/bin/env python3
"""
EMMC FIO 性能测试运行器（PC 端）。

与 emmc_tools.py 的 perf 模式保持一致：
- 4 个场景（Seq_Read / Seq_Write / Rand_Read / Rand_Write）
- 默认 runtime=60s，rounds=3
- fio 参数：direct=1 ioengine=libaio time_based group_reporting size=1G iodepth=64 thread

用法示例:
    python emmc/host/emmc_fio_runner.py --serial 2492d300b0ae006c --mode seq_read --runtime 60 --rounds 3
"""

import argparse
import io
import json
import re
import sys
import time
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

logger = setup_logger("emmc_fio")


SCENARIO_CONFIG = {
    "seq_read": {"rw": "read", "bs": "128k", "name": "Seq_Read"},
    "seq_write": {"rw": "write", "bs": "128k", "name": "Seq_Write"},
    "rand_read": {"rw": "randread", "bs": "4k", "name": "Rand_Read"},
    "rand_write": {"rw": "randwrite", "bs": "4k", "name": "Rand_Write"},
}


def parse_fio_output(output: str) -> dict:
    """从 fio 终端输出解析关键指标，与 emmc_tools.py 保持一致。"""
    result = {
        "bw_mbps": 0.0,
        "iops": 0.0,
        "max_iops": 0,
        "lat_p999_us": 0.0,
        "cpu_sys": 0.0,
        "cpu_usr": 0.0,
        "emmc_util": 0.0,
    }

    bw_m = re.search(r"BW=.*?\((\d+(?:\.\d+)?)(k?B|m?B|g?B)/s\)", output, re.IGNORECASE)
    if bw_m:
        v = float(bw_m.group(1))
        unit = bw_m.group(2).lower()
        if "k" in unit:
            v /= 1000
        elif "g" in unit:
            v *= 1000
        result["bw_mbps"] = round(v, 2)
    else:
        bw_m = re.search(r"BW=\s*([\d.]+)([KMGTk]i?B)/", output, re.IGNORECASE)
        if bw_m:
            v = float(bw_m.group(1))
            unit = bw_m.group(2).lower()
            if "k" in unit:
                v /= 1024
            elif "g" in unit:
                v *= 1024
            result["bw_mbps"] = round(v, 2)

    iops_m = re.search(r"iops\s*:\s*min=[^,]+,\s*max=\s*(\d+)", output, re.IGNORECASE)
    if iops_m:
        result["max_iops"] = int(iops_m.group(1))

    avg_iops_m = re.search(r"IOPS=\s*([\d.]+)", output)
    if avg_iops_m:
        result["iops"] = round(float(avg_iops_m.group(1)), 2)

    lat_m = re.search(r"99\.90th=\[\s*(\d+)\s*\]", output)
    if lat_m:
        result["lat_p999_us"] = float(lat_m.group(1))

    cpu_m = re.search(r"cpu\s*:\s*usr=([\d.]+)%\s*,\s*sys=([\d.]+)%\s*", output)
    if cpu_m:
        result["cpu_usr"] = float(cpu_m.group(1))
        result["cpu_sys"] = float(cpu_m.group(2))

    util_m = re.search(r"util=([\d.]+)%", output)
    if util_m:
        result["emmc_util"] = float(util_m.group(1))

    return result


def aggregate_rounds(rounds: list) -> dict:
    """聚合多轮结果为平均值，与 emmc_tools.py 报告维度一致。"""
    if not rounds:
        return {}

    keys = ["bw_mbps", "iops", "max_iops", "lat_p999_us", "cpu_sys", "cpu_usr", "emmc_util"]
    agg = {}
    for k in keys:
        values = [r[k] for r in rounds if k in r]
        agg[k] = round(sum(values) / len(values), 2) if values else 0.0

    agg["rounds"] = len(rounds)
    agg["round_details"] = rounds
    return agg


def run_fio(adb: AdbRunner, args) -> dict:
    """执行 fio 性能测试并返回结构化结果。"""
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

    round_results = []
    for i in range(1, rounds + 1):
        logger.info("执行 %s 第 %d/%d 轮 (runtime=%ds)...", cfg["name"], i, rounds, runtime)

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
        ]

        start = time.time()
        res = adb.shell(" ".join(cmd_parts), timeout=runtime + 30, check=False)
        cost = time.time() - start

        if res is None or res.returncode != 0:
            err = res.stderr if res else "命令超时或未知异常"
            logger.error("fio 测试失败: %s", err)
            raise RuntimeError(f"fio 测试失败: {err}")

        metrics = parse_fio_output(res.stdout)
        metrics.update({
            "scenario": cfg["name"],
            "round": i,
            "runtime": runtime,
            "cost_seconds": round(cost, 2),
        })
        round_results.append(metrics)
        logger.info("  第 %d 轮: BW=%.2f MB/s, IOPS=%.2f", i, metrics["bw_mbps"], metrics["iops"])

    aggregated = aggregate_rounds(round_results)
    result = {
        "status": "ok",
        "scenario": cfg["name"],
        "mode": args.mode,
        "runtime": runtime,
        "rounds": rounds,
        **aggregated,
    }

    logger.info("%s 聚合完成: BW=%.2f MB/s, IOPS=%.2f, util=%.2f%%",
                cfg["name"], result.get("bw_mbps", 0), result.get("iops", 0), result.get("emmc_util", 0))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="EMMC FIO 性能测试运行器")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--mode", type=str, required=True,
                        choices=list(SCENARIO_CONFIG.keys()),
                        help="测试模式")
    parser.add_argument("--runtime", type=int, default=60, help="每轮 fio 运行时长（秒），默认 60")
    parser.add_argument("--rounds", type=int, default=3, help="执行轮数，默认 3")
    parser.add_argument("--filename", type=str, default=None, help="fio 测试文件路径，默认 /data/test")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)
    run_fio(adb, args)


if __name__ == "__main__":
    main()
