#!/usr/bin/env python3
"""
EMMC FIO 报告生成器（PC 端）。

读取多个 fio 测试的 JSON/日志结果，生成聚合 Markdown/JSON 报告。

用法示例:
    python emmc_report.py --output-dir ./report --seq-read-log seq_read.log --seq-write-log seq_write.log
"""

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("emmc_report")


def parse_fio_log(content: str) -> Dict[str, Any]:
    """从 fio 原始日志中解析关键指标。"""
    result = {
        "bw_mbps": 0.0,
        "iops": 0.0,
        "max_iops": 0,
        "lat_p999_us": 0.0,
        "cpu_sys": 0.0,
        "cpu_usr": 0.0,
        "emmc_util": 0.0,
    }

    bw_m = re.search(r"BW=.*?\((\d+(?:\.\d+)?)(k?B|m?B|g?B)/s\)", content, re.IGNORECASE)
    if bw_m:
        v = float(bw_m.group(1))
        unit = bw_m.group(2).lower()
        if "k" in unit:
            v /= 1000
        elif "g" in unit:
            v *= 1000
        result["bw_mbps"] = round(v, 2)
    else:
        bw_m = re.search(r"BW=\s*([\d.]+)([KMGTk]i?B)/", content, re.IGNORECASE)
        if bw_m:
            v = float(bw_m.group(1))
            unit = bw_m.group(2).lower()
            if "k" in unit:
                v /= 1024
            elif "g" in unit:
                v *= 1024
            result["bw_mbps"] = round(v, 2)

    iops_m = re.search(r"iops\s*:\s*min=[^,]+,\s*max=\s*(\d+)", content, re.IGNORECASE)
    if iops_m:
        result["max_iops"] = int(iops_m.group(1))

    avg_iops_m = re.search(r"IOPS=\s*([\d.]+)", content)
    if avg_iops_m:
        result["iops"] = round(float(avg_iops_m.group(1)), 2)

    lat_m = re.search(r"99\.90th=\[\s*(\d+)\s*\]", content)
    if lat_m:
        result["lat_p999_us"] = float(lat_m.group(1))

    cpu_m = re.search(r"cpu\s*:\s*usr=([\d.]+)%\s*,\s*sys=([\d.]+)%\s*", content)
    if cpu_m:
        result["cpu_usr"] = float(cpu_m.group(1))
        result["cpu_sys"] = float(cpu_m.group(2))

    util_m = re.search(r"util=([\d.]+)%", content)
    if util_m:
        result["emmc_util"] = float(util_m.group(1))

    return result


def collect_results(args) -> List[Dict[str, Any]]:
    """收集所有场景的 fio 结果。"""
    scenarios = [
        ("Seq_Read", args.seq_read_log),
        ("Seq_Write", args.seq_write_log),
        ("Rand_Read", args.rand_read_log),
        ("Rand_Write", args.rand_write_log),
    ]

    summary = []
    for name, path in scenarios:
        if not path or not os.path.exists(path):
            logger.warning("跳过未提供的日志: %s", name)
            continue

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        metrics = parse_fio_log(content)
        metrics["scenario"] = name
        summary.append(metrics)

    return summary


def generate_markdown(summary: List[Dict[str, Any]], output_path: Path):
    """生成 Markdown 报告。"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# EMMC 性能测试报告\n\n")
        f.write("## FIO 性能汇总\n\n")
        f.write("| 场景 | 带宽(MB/s) | IOPS | 最大 IOPS | P99.9 延迟(us) | CPU 使用率 | EMMC 利用率 |\n")
        f.write("|---|---|---|---|---|---|---|\n")

        for item in summary:
            cpu_total = item.get("cpu_usr", 0) + item.get("cpu_sys", 0)
            f.write(
                f"| {item['scenario']} | {item.get('bw_mbps', 0)} | "
                f"{item.get('iops', 0)} | {item.get('max_iops', 0)} | "
                f"{item.get('lat_p999_us', 0)} | {cpu_total:.2f}% | {item.get('emmc_util', 0)}% |\n"
            )

        f.write("\n## 分析结论\n\n")
        f.write(
            "> 请根据实际业务场景判断：带宽是否饱和、IOPS 是否达标、延迟是否可接受。\n"
        )

    logger.info("Markdown 报告已生成: %s", output_path)


def main():
    parser = argparse.ArgumentParser(description="EMMC FIO 报告生成器")
    parser.add_argument("--output-dir", type=str, default="./report", help="输出目录")
    parser.add_argument("--seq-read-log", type=str, help="顺序读 fio 日志路径")
    parser.add_argument("--seq-write-log", type=str, help="顺序写 fio 日志路径")
    parser.add_argument("--rand-read-log", type=str, help="随机读 fio 日志路径")
    parser.add_argument("--rand-write-log", type=str, help="随机写 fio 日志路径")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = collect_results(args)

    json_path = output_dir / "emmc_fio_summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
    logger.info("JSON 汇总已生成: %s", json_path)

    md_path = output_dir / "Test_Card_Report.md"
    generate_markdown(summary, md_path)

    # 同步到根目录
    try:
        import shutil
        shutil.copy2(md_path, Path.cwd() / "Test_Card_Report.md")
        logger.info("报告已同步至运行根目录。")
    except Exception as e:
        logger.warning("同步报告到根目录失败: %s", e)


if __name__ == "__main__":
    main()
