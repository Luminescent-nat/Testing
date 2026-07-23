#!/usr/bin/env python3
"""
EMMC 性能与信息测试统一入口。

基于 common 模块复用 ADB、设备信息检测等能力，整合：
- extcsd 寄存器读取
- fio 性能测试（perf / stability）
- Markdown / Word 报告生成

用法示例：
    python emmc/host/emmc_tester.py --serial 2492d300b0ae006c --mode both --rounds 3
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# 把 test-tools 根目录加入路径，便于 import common
TOOLS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(TOOLS_ROOT))

from common.adb_runner import AdbRunner
from common.device_info import detect_arch, detect_mmc_node, get_tool_path
from common.logger import setup_logger

logger = setup_logger("emmc_tester")


class EMMCTester:
    """EMMC 测试执行器。"""

    SCENARIOS = [
        {"name": "Seq_Read", "rw": "read", "bs": "128k"},
        {"name": "Seq_Write", "rw": "write", "bs": "128k"},
        {"name": "Rand_Read", "rw": "randread", "bs": "4k"},
        {"name": "Rand_Write", "rw": "randwrite", "bs": "4k"},
    ]

    def __init__(
        self,
        adb: AdbRunner,
        mmc_block: Optional[str] = None,
        output_dir: Optional[Path] = None,
    ):
        self.adb = adb
        self.mmc_block = mmc_block
        self.arch = detect_arch(adb)
        self.remote_dir = "/data/local/tmp/emmc"

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = Path.cwd() / "report" / f"emmc_test_{ts}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._fio_remote: Optional[str] = None
        self._mmc_remote: Optional[str] = None
        self._extcsd_data: Optional[dict] = None

    def setup_env(self):
        """root、推送 fio / mmc_utils 并赋权。"""
        logger.info("准备 EMMC 测试环境...")
        self.adb.root()

        self.adb.shell(f"mkdir -p {self.remote_dir}", check=False)

        # 按架构推送工具
        search_roots = [Path(__file__).resolve().parent.parent, TOOLS_ROOT]
        fio_local = get_tool_path("fio", self.arch, search_roots)
        mmc_local = get_tool_path("mmc_utils", self.arch, search_roots)

        self._fio_remote = f"{self.remote_dir}/fio"
        self._mmc_remote = f"{self.remote_dir}/mmc_utils"

        if not self.adb.push(fio_local, self._fio_remote):
            raise RuntimeError(f"推送 fio 失败: {fio_local}")
        if not self.adb.push(mmc_local, self._mmc_remote):
            raise RuntimeError(f"推送 mmc_utils 失败: {mmc_local}")

        self.adb.shell(f"chmod +x {self._fio_remote} {self._mmc_remote}", check=False)
        logger.info("环境准备完成，架构=%s", self.arch)

    def detect_mmc_node(self) -> str:
        """自动或手动确定 eMMC 节点。"""
        self.mmc_block = detect_mmc_node(self.adb, self.mmc_block)
        logger.info("使用 eMMC 节点: %s", self.mmc_block)
        return self.mmc_block

    @staticmethod
    def _parse_hex_val(content: str, pattern: str, default: str = "Unknown") -> str:
        match = re.search(pattern, content, re.IGNORECASE)
        return match.group(1).strip() if match else default

    def read_extcsd(self) -> dict:
        """读取并解析 extcsd。"""
        logger.info("读取 eMMC extcsd...")
        res = self.adb.shell(
            f"{self._mmc_remote} extcsd read {self.mmc_block}",
            timeout=30,
            check=False,
        )
        if res is None or res.returncode != 0:
            raise RuntimeError(f"extcsd 读取失败: {res.stderr if res else '超时'}")

        out = res.stdout
        data = {
            "mmc_node": self.mmc_block,
            "life_time_type_a": self._parse_hex_val(out, r"DEVICE_LIFE_TIME_EST_TYP_A.*?:\s*(0x[0-9a-f]+)"),
            "life_time_type_b": self._parse_hex_val(out, r"DEVICE_LIFE_TIME_EST_TYP_B.*?:\s*(0x[0-9a-f]+)"),
            "pre_eol_info": self._parse_hex_val(out, r"PRE_EOL_INFO.*?:\s*(0x[0-9a-f]+)"),
            "sector_count": self._parse_hex_val(out, r"SEC_COUNT.*?:\s*(0x[0-9a-f]+)"),
            "max_packed_reads": self._parse_hex_val(out, r"MAX_PACKED_READS.*?:\s*(0x[0-9a-f]+)"),
            "max_packed_writes": self._parse_hex_val(out, r"MAX_PACKED_WRITES.*?:\s*(0x[0-9a-f]+)"),
            "trim_multiplier": self._parse_hex_val(out, r"TRIM_MULT.*?:\s*(0x[0-9a-f]+)"),
            "hc_erase_group_size": self._parse_hex_val(out, r"HC_ERASE_GRP_SIZE.*?:\s*(0x[0-9a-f]+)"),
            "hc_wp_group_size": self._parse_hex_val(out, r"HC_WP_GRP_SIZE.*?:\s*(0x[0-9a-f]+)"),
            "sleep_current_vcc": self._parse_hex_val(out, r"S_C_VCC.*?:\s*(0x[0-9a-f]+)"),
            "sleep_current_vccq": self._parse_hex_val(out, r"S_C_VCCQ.*?:\s*(0x[0-9a-f]+)"),
            "sleep_awake_timeout": self._parse_hex_val(out, r"S_A_TIMEOUT.*?:\s*(0x[0-9a-f]+)"),
            "init_timeout": self._parse_hex_val(out, r"INI_TIMEOUT_AP.*?:\s*(0x[0-9a-f]+)"),
            "cmdq_depth": self._parse_hex_val(out, r"CMDQ_DEPTH.*?:\s*(0x[0-9a-f]+)"),
            "cmdq_enabled": self._parse_hex_val(out, r"CMDQ_MODE_EN.*?:\s*(0x[0-9a-f]+)"),
            "card_type": "Unknown",
            "firmware_version": "Unknown",
        }

        # Cache Size 兼容两种格式
        ch_sz = re.search(r"CACHE_SIZE\]\s*is\s*([^\n\r]+)", out, re.IGNORECASE)
        data["cache_size"] = ch_sz.group(1).strip() if ch_sz else self._parse_hex_val(out, r"CACHE_SIZE.*?:\s*(0x[0-9a-f]+)")

        # 容量换算
        if data["sector_count"].startswith("0x"):
            sec_cnt = int(data["sector_count"], 16)
            data["capacity_gib"] = round((sec_cnt * 512) / (1024 ** 3), 2)

        # Card Type
        card_m = re.search(
            r"Card Type \[CARD_TYPE: (0x[0-9a-f]+)\](.*?)(?=\r?\n[^\s\-]|\r?\n\r?\n)",
            out,
            re.DOTALL | re.IGNORECASE,
        )
        if card_m:
            data["card_type_raw"] = card_m.group(1).strip()
            desc = card_m.group(2).strip()
            data["card_type"] = desc if desc else data["card_type_raw"]

        # Firmware Version
        fw_ver = re.search(r"eMMC Firmware Version:\s*([^\n\r]+)", out, re.IGNORECASE)
        if fw_ver:
            data["firmware_version"] = fw_ver.group(1).strip()

        self._extcsd_data = data
        snapshot_path = self.output_dir / "emmc_snapshot.json"
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info("extcsd 已保存: %s", snapshot_path)
        return data

    @staticmethod
    def _parse_fio_output(output: str) -> dict:
        """从 fio 终端输出解析关键指标。"""
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

    def run_fio_tests(self, mode: str = "perf", runtime: int = 60, rounds: int = 3, filename: str = "/data/local/tmp/emmc_fio_test"):
        """执行 fio 测试。"""
        logger.info("开始 FIO %s 测试 (runtime=%ds, rounds=%d)", mode, runtime, rounds)
        summary = []

        for case in self.SCENARIOS:
            for i in range(1, rounds + 1):
                case_id = f"{mode}_{case['name']}_{i}"
                logger.info("执行 %s (第 %d/%d 轮)...", case["name"], i, rounds)

                log_prefix = f"/data/{case_id}"
                cmd_parts = [
                    f"{self._fio_remote} --filename={filename} --direct=1",
                    "--ioengine=libaio",
                    f"--runtime={runtime} --time_based=1",
                    "--group_reporting=1 --size=1G",
                    f"--name={case['name']}",
                    f"--rw={case['rw']} --iodepth=64 --bs={case['bs']} --thread",
                ]
                if mode == "stability":
                    cmd_parts.extend([
                        f"--write_bw_log={log_prefix}",
                        f"--write_iops_log={log_prefix}",
                        "--log_avg_msec=1000",
                    ])

                cmd = " ".join(cmd_parts)
                start = time.time()
                res = self.adb.shell(cmd, timeout=runtime + 30, check=False)
                cost = time.time() - start

                if res is None or res.returncode != 0:
                    err = res.stderr if res else "超时或未知异常"
                    logger.error("%s 测试失败: %s", case_id, err)
                    continue

                local_log = self.output_dir / f"{case_id}.log"
                with open(local_log, "w", encoding="utf-8") as f:
                    f.write(res.stdout)

                metrics = self._parse_fio_output(res.stdout)
                metrics.update({
                    "scenario": case["name"],
                    "round": i,
                    "mode": mode,
                    "runtime": runtime,
                    "cost_seconds": round(cost, 2),
                })
                summary.append(metrics)
                logger.info("%s 完成: BW=%.2f MB/s, IOPS=%.2f", case_id, metrics["bw_mbps"], metrics["iops"])

                if mode == "stability":
                    self.adb.shell(f"mv {log_prefix}_bw.1.log {log_prefix}_bw.log", check=False)
                    self.adb.shell(f"mv {log_prefix}_iops.1.log {log_prefix}_iops.log", check=False)
                    self.adb.pull(f"{log_prefix}_bw.log", self.output_dir / f"{case_id}_bw.log")
                    self.adb.pull(f"{log_prefix}_iops.log", self.output_dir / f"{case_id}_iops.log")
                    self.adb.shell(f"rm {log_prefix}_*", check=False)

        if summary:
            summary_path = self.output_dir / f"{mode}_fio_summary.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=4, ensure_ascii=False)
            logger.info("FIO %s 汇总已保存: %s", mode, summary_path)
        return summary

    def generate_markdown_report(self, mode: str = "perf"):
        """生成 Markdown 测试卡片。"""
        card_file = self.output_dir / "Test_Card_Report.md"
        snapshot = self._extcsd_data or {}

        with open(card_file, "w", encoding="utf-8") as f:
            f.write("# EMMC 性能测试与验证报告\n\n")

            f.write("## 1. 主要性能参数\n\n")
            f.write("| 主要参数 | 解析结果 | 影响 |\n|---|---|---|\n")
            f.write(f"| 缓存 Cache Size | {snapshot.get('cache_size', 'N/A')} | 文件读写性能 |\n")
            f.write(f"| 最大数据包(读取) | {snapshot.get('max_packed_reads', 'N/A')} | 并发读取能力 |\n")
            f.write(f"| 最大数据包(写入) | {snapshot.get('max_packed_writes', 'N/A')} | 并发写入能力 |\n")
            f.write(f"| TRIM Multiplier | {snapshot.get('trim_multiplier', 'N/A')} | 操作效率及寿命 |\n")
            f.write(f"| 容量 | {snapshot.get('capacity_gib', 'N/A')} GiB | 实际容量 |\n")
            f.write(f"| 睡眠电流(VCC/VCCQ) | {snapshot.get('sleep_current_vcc', '-')}/{snapshot.get('sleep_current_vccq', '-')} | 休眠功耗 |\n")
            f.write(f"| HC WP Group Size | {snapshot.get('hc_wp_group_size', 'N/A')} | 写保护分组尺寸 |\n")
            f.write(f"| 休眠唤醒超时 | {snapshot.get('sleep_awake_timeout', 'N/A')} | 唤醒响应时长 |\n")
            f.write(f"| CMDQ 深度 | {snapshot.get('cmdq_depth', 'N/A')} | 随机并发提速 |\n")
            card_type = str(snapshot.get('card_type', 'N/A')).replace('\n', '<br>')
            f.write(f"| 驱动强度 Card Type | {card_type} | 支持下行频率 |\n")
            f.write("\n")

            f.write("## 2. FIO 性能测试\n\n")
            summary_path = self.output_dir / f"{mode}_fio_summary.json"
            if summary_path.exists():
                with open(summary_path, "r", encoding="utf-8") as sm:
                    perf_list = json.load(sm)

                scenarios_map = {
                    "Seq_Read": "顺序读取",
                    "Seq_Write": "顺序写入",
                    "Rand_Read": "随机读取",
                    "Rand_Write": "随机写入",
                }
                for code_name, zh_name in scenarios_map.items():
                    rounds_data = [x for x in perf_list if x["scenario"] == code_name]
                    if not rounds_data:
                        continue

                    f.write(f"### {zh_name}\n")
                    headers = ["参数"] + [f"轮次 {r['round']}" for r in rounds_data]
                    f.write("| " + " | ".join(headers) + " |\n")
                    f.write("|" + "|".join(["---"] * len(headers)) + "|\n")

                    rows = [
                        ("带宽(MB/s)", lambda x: str(x.get("bw_mbps", 0))),
                        ("IOPS", lambda x: str(x.get("iops", 0))),
                        ("最大 IOPS", lambda x: str(x.get("max_iops", 0))),
                        ("P99.9 延迟(us)", lambda x: str(x.get("lat_p999_us", 0))),
                        ("CPU 使用率(%)", lambda x: f"{x.get('cpu_usr', 0) + x.get('cpu_sys', 0):.2f}"),
                        ("EMMC 利用率(%)", lambda x: str(x.get("emmc_util", 0))),
                    ]
                    for title, fn in rows:
                        f.write("| " + title + " | " + " | ".join([fn(d) for d in rounds_data]) + " |\n")
                    f.write("\n")

            f.write("## 3. 可靠性寿命估算\n\n")
            f.write(f"- Life Time A: `{snapshot.get('life_time_type_a', 'N/A')}`\n")
            f.write(f"- Life Time B: `{snapshot.get('life_time_type_b', 'N/A')}`\n")
            f.write(f"- PRE EOL Info: `{snapshot.get('pre_eol_info', 'N/A')}`\n")

        logger.info("Markdown 报告已生成: %s", card_file)

        # 同步到运行根目录
        try:
            shutil.copy2(card_file, Path.cwd() / "Test_Card_Report.md")
            logger.info("Markdown 报告已同步至根目录")
        except Exception as e:
            logger.warning("同步报告失败: %s", e)

        return card_file


def main():
    parser = argparse.ArgumentParser(description="EMMC 性能自动化测试入口")
    parser.add_argument("--serial", type=str, default=None, help="ADB 设备序列号")
    parser.add_argument("--mmc-block", type=str, default=None, help="手动指定 eMMC 节点")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["perf", "stability", "both"],
        default="both",
        help="测试模式",
    )
    parser.add_argument("--runtime", type=int, default=None, help="fio 运行时长（秒）")
    parser.add_argument("--rounds", type=int, default=None, help="fio 执行轮数")
    parser.add_argument("--output-dir", type=str, default=None, help="报告输出目录")
    args = parser.parse_args()

    adb = AdbRunner(args.serial)
    tester = EMMCTester(adb, args.mmc_block, output_dir=Path(args.output_dir) if args.output_dir else None)

    tester.setup_env()
    tester.detect_mmc_node()
    tester.read_extcsd()

    if args.mode in ("perf", "both"):
        runtime = args.runtime if args.runtime else 60
        rounds = args.rounds if args.rounds else 3
        tester.run_fio_tests("perf", runtime=runtime, rounds=rounds)
        tester.generate_markdown_report("perf")

    if args.mode in ("stability", "both"):
        runtime = args.runtime if args.runtime else 300
        rounds = args.rounds if args.rounds else 1
        tester.run_fio_tests("stability", runtime=runtime, rounds=rounds)
        tester.generate_markdown_report("stability")

    print(json.dumps({"status": "ok", "output_dir": str(tester.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
