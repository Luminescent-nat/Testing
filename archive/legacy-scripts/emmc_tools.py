import os
import sys
import subprocess
import re
import argparse
import time
import json
import logging
from pathlib import Path

# 配置日志日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('EMMC_Test')

class AdbRunner:
    def __init__(self, serial=None):
        self.serial = serial
        self._check_adb()

    def _check_adb(self):
        try:
            self.execute("adb version")
            logger.info("ADB 命令行工具已就绪。")
        except FileNotFoundError:
            logger.error("未找到 adb 命令，请确保 adb 已添加到系统环境变量。")
            sys.exit(1)

    def execute(self, cmd, timeout=None, check=True):
        """执行本地命令"""
        if isinstance(cmd, list):
            cmd_str = " ".join(cmd)
        else:
            cmd_str = cmd
        
        try:
            result = subprocess.run(
                cmd_str, shell=True, capture_output=True, text=True, 
                encoding='utf-8', errors='replace', timeout=timeout
            )
            if check and result.returncode != 0:
                logger.debug(f"Command failed: {cmd_str}\nError: {result.stderr.strip()}")
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"命令执行超时: {cmd_str}")
            return None
            
    def adb_shell(self, cmd, timeout=None, check=True):
        """执行 ADB Shell 命令"""
        prefix = f"adb -s {self.serial} " if self.serial else "adb "
        full_cmd = f'{prefix}shell "{cmd}"'
        return self.execute(full_cmd, timeout=timeout, check=check)
        
    def adb_push(self, src, dest):
        prefix = f"adb -s {self.serial} " if self.serial else "adb "
        full_cmd = f'{prefix}push "{src}" "{dest}"'
        res = self.execute(full_cmd, check=False)
        if res and res.returncode == 0:
            logger.info(f"成功推送: {src} -> {dest}")
        else:
            logger.error(f"推送失败: {res.stderr if res else '未知异常'}")

    def adb_pull(self, src, dest):
        prefix = f"adb -s {self.serial} " if self.serial else "adb "
        full_cmd = f'{prefix}pull "{src}" "{dest}"'
        res = self.execute(full_cmd, check=False)
        if res and res.returncode == 0:
            logger.info(f"成功拉取: {src} -> {dest}")
        else:
            logger.error(f"拉取失败或源文件不存在: {src}")

class EMMCTester:
    def __init__(self, adb: AdbRunner, mmc_block=None):
        self.adb = adb
        self.mmc_block = mmc_block
        self.bin_dir = "/data"
        
        # 隔离输出文件夹
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 智能判定打包态与脚本态的输出根路径
        if getattr(sys, 'frozen', False):
            self.root_dir = Path(sys.executable).parent
        else:
            self.root_dir = Path.cwd()
            
        self.output_parent = self.root_dir / "report"
        self.output_dir = self.output_parent / f"test_run_{ts}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def setup_env(self):
        logger.info("检查并提升 Root 权限...")
        res = self.adb.execute("adb root")
        time.sleep(1) # 等待 root 重启 dbd 守护进程
        
        # 推送二进制
        logger.info("准备推送二进制文件...")
        
        # 智能检索打包资源
        if getattr(sys, 'frozen', False):
            # 优先从 PyInstaller 临时释放目录检索
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path.cwd()
            
        fio_path = base_dir / "fio"
        mmc_path = base_dir / "mmc_utils"
        
        # 鲁棒性兜底：若在打包临时目录中未检测到二进制，则在运行根目录或 EXE 同级目录下检索
        if not fio_path.exists() or not mmc_path.exists():
            fio_path = self.root_dir / "fio"
            mmc_path = self.root_dir / "mmc_utils"
            
        if not fio_path.exists() or not mmc_path.exists():
            logger.error(f"在打包环境 {base_dir} 及运行根目录 {self.root_dir} 下均未找到 fio 或 mmc_utils 二进制文件！")
            sys.exit(1)
            
        self.adb.adb_push(str(fio_path), f"{self.bin_dir}/fio")
        self.adb.adb_push(str(mmc_path), f"{self.bin_dir}/mmc_utils")
        
        # 赋予权限
        self.adb.adb_shell(f"chmod +x {self.bin_dir}/fio {self.bin_dir}/mmc_utils")
        
    def detect_mmc_node(self):
        if self.mmc_block:
            logger.info(f"使用用户指定 eMMC 节点: {self.mmc_block}")
            return self.mmc_block
            
        logger.info("开始自动识别 eMMC 节点...")
        # 常规平板主存储通常是 mmcblk0
        # 检查 sys/block 下的 mmcblk*
        res = self.adb.adb_shell("ls /sys/block/ | grep mmcblk")
        if res.returncode == 0:
            blocks = res.stdout.strip().split()
            # 找到主设备（不包含 boot0, boot1 等属性的根设备），通常取排序第一个没有 p1, p2 的
            main_blocks = [b for b in blocks if not re.search(r'p\d+|boot\d+|rpmb', b)]
            if main_blocks:
                self.mmc_block = f"/dev/block/{main_blocks[0]}"
                logger.info(f"自动检测到 eMMC 节点: {self.mmc_block}")
                return self.mmc_block
                
        # 退回默认
        logger.warning("节点自动识别未找到，回退到默认 /dev/block/mmcblk0")
        self.mmc_block = "/dev/block/mmcblk0"
        return self.mmc_block

    def parse_hex_val(self, content, pattern, default="Unknown"):
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
             return match.group(1).strip()
        return default
        
    def extcsd_read(self):
        logger.info(f"开始提取 eMMC 扩展寄存器参数...")
        res = self.adb.adb_shell(f"{self.bin_dir}/mmc_utils extcsd read {self.mmc_block}")
        if res.returncode != 0:
            logger.error("extcsd read 读取失败。")
            return None
            
        out = res.stdout
        
        # 数据集
        data = {}
        
        # 解析工具函数：适配不同版本 mmc_utils 冒号在括号内外的情况
        
        # [EXT_CSD_DEVICE_LIFE_TIME_EST_TYP_A]: 0x01 / [DEVICE_LIFE_TIME...: 0x01]
        data['Life Time Type A (MLC)'] = self.parse_hex_val(out, r'DEVICE_LIFE_TIME_EST_TYP_A.*?:\s*(0x[0-9a-f]+)')
        data['Life Time Type B (SLC)'] = self.parse_hex_val(out, r'DEVICE_LIFE_TIME_EST_TYP_B.*?:\s*(0x[0-9a-f]+)')
        data['Pre EOL Info'] = self.parse_hex_val(out, r'PRE_EOL_INFO.*?:\s*(0x[0-9a-f]+)')
        
        # 缓存与容量
        ch_sz = re.search(r'CACHE_SIZE\]\s*is\s*([^\n\r]+)', out, re.IGNORECASE)
        data['Cache Size'] = ch_sz.group(1).strip() if ch_sz else self.parse_hex_val(out, r'CACHE_SIZE.*?:\s*(0x[0-9a-f]+)')
        
        data['Sector Count'] = self.parse_hex_val(out, r'SEC_COUNT.*?:\s*(0x[0-9a-f]+)')
        
        # 换算容量: sector size 通常是 512B
        if data['Sector Count'].startswith('0x'):
            sec_cnt = int(data['Sector Count'], 16)
            gib_cap = (sec_cnt * 512) / (1024**3)
            data['Capacity (GiB)'] = f"{round(gib_cap, 2)} GiB"
        
        # 大批量读写及擦除
        data['Max Packet Read Cmd'] = self.parse_hex_val(out, r'MAX_PACKED_READS.*?:\s*(0x[0-9a-f]+)')
        data['Max Packet Write Cmd'] = self.parse_hex_val(out, r'MAX_PACKED_WRITES.*?:\s*(0x[0-9a-f]+)')
        data['TRIM Multiplier'] = self.parse_hex_val(out, r'TRIM_MULT.*?:\s*(0x[0-9a-f]+)')
        data['HC Erase Group Size'] = self.parse_hex_val(out, r'HC_ERASE_GRP_SIZE.*?:\s*(0x[0-9a-f]+)')
        data['HC WP Group Size'] = self.parse_hex_val(out, r'HC_WP_GRP_SIZE.*?:\s*(0x[0-9a-f]+)')
        
        # 功耗与响应时间
        data['Sleep Current (VCC)'] = self.parse_hex_val(out, r'S_C_VCC.*?:\s*(0x[0-9a-f]+)')
        data['Sleep Current (VCCQ)'] = self.parse_hex_val(out, r'S_C_VCCQ.*?:\s*(0x[0-9a-f]+)')
        data['Sleep / Awake Timeout'] = self.parse_hex_val(out, r'S_A_TIMEOUT.*?:\s*(0x[0-9a-f]+)')
        data['Initialisation Time'] = self.parse_hex_val(out, r'INI_TIMEOUT_AP.*?:\s*(0x[0-9a-f]+)')
        
        # 高级队列 (针对 5.1+, 若为 5.0 可安全降级为 Unknown)
        data['CMDQ Depth'] = self.parse_hex_val(out, r'CMDQ_DEPTH.*?:\s*(0x[0-9a-f]+)')
        data['CMDQ Enabled'] = self.parse_hex_val(out, r'CMDQ_MODE_EN.*?:\s*(0x[0-9a-f]+)')
        
        # 驱动强度解析：直接抓取 mmc_utils 自带的多行文本说明 (支持 HS400, HS200 等组合)
        # 抓取 Card Type [CARD_TYPE: 0xXX] 之后的所有带空格缩进的模式说明行
        card_m = re.search(r'Card Type \[CARD_TYPE: (0x[0-9a-f]+)\](.*?)(?=\r?\n[^\s\-]|\r?\n\r?\n)', out, re.DOTALL | re.IGNORECASE)
        if card_m:
            data['Card Type Raw'] = card_m.group(1).strip()
            # 清洗抓取到的多行文本，将其中的多余换行符由 \r\n/ \r 归一化为 \n 供 Report 后续分发
            desc = card_m.group(2).strip()
            # 如果抓到了长文本则使用长文本，否则回退到 HEX
            data['Card Type'] = desc if desc else data['Card Type Raw']
        else:
            data['Card Type'] = "Unknown"
        
        logger.info(f"原生 Card Type 提取结果: {data['Card Type']}")
        
        fw_ver = re.search(r'eMMC Firmware Version:\s*([^\n\r]+)', out, re.IGNORECASE)
        data['Firmware Version'] = fw_ver.group(1).strip() if fw_ver else "Unknown"
        
        # 保存下来并打印
        with open(self.output_dir / "emmc_snapshot.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        logger.info(" eMMC 寄存器参数提取完成！")
        for k, v in data.items():
            logger.info(f"  {k}: {v}")
            
        return data

    def run_fio_tests(self, mode="perf", runtime=60, filename="/data/test", rounds=3):
        logger.info(f"开始 FIO 性能回归测试 [{mode} 模式] (测试时长: {runtime}秒, 每组轮数: {rounds})")
        
        # 4 个用例配置
        scenarios = [
            {"name": "Seq_Read", "rw": "read", "bs": "128k"},
            {"name": "Seq_Write", "rw": "write", "bs": "128k"},
            {"name": "Rand_Read", "rw": "randread", "bs": "4k"},
            {"name": "Rand_Write", "rw": "randwrite", "bs": "4k"}
        ]
        
        for case in scenarios:
            for i in range(1, rounds + 1):
                case_id = f"{mode}_{case['name']}_{i}"
                logger.info(f" 执行 {case['name']} (第 {i}/{rounds} 轮) ...")
                
                log_prefix = f"/data/{case_id}"
                
                fio_cmd_list = [
                    f"{self.bin_dir}/fio --filename={filename} --direct=1",
                    f"--ioengine=libaio --runtime={runtime} --time_based=1",
                    f"--group_reporting=1 --size=1G --name={case['name']}",
                    f"--rw={case['rw']} --iodepth=64 --bs={case['bs']} --thread"
                ]
                
                # 稳定性模式专供数据采集参数
                if mode == "stability":
                    fio_cmd_list.extend([
                        f"--write_bw_log={log_prefix}",
                        f"--write_iops_log={log_prefix}",
                        f"--log_avg_msec=1000"
                    ])
                
                fio_cmd = " ".join(fio_cmd_list)
                
                start_time = time.time()
                res = self.adb.adb_shell(fio_cmd, timeout=runtime + 20, check=False)
                cost = time.time() - start_time
                
                if res is None or res.returncode != 0:
                    err_msg = res.stderr if res else "命令超时或未知异常"
                    logger.error(f"{case_id} 测试异常退出！日志: {err_msg}")
                    continue
                    
                # 抛弃不可靠的 JSON，保存终端原始 FIO 日志
                local_log = self.output_dir / f"{case_id}.log"
                with open(local_log, 'w', encoding='utf-8') as f:
                    f.write(res.stdout)
                    
                logger.info(f" {case_id} 完成，耗时: {cost:.1f}s")
                
                if mode == "stability":
                    # 拉取 log_avg 生成的 *_bw.1.log, *_iops.1.log 等
                    self.adb.adb_shell(f"mv {log_prefix}_bw.1.log {log_prefix}_bw.log", check=False)
                    self.adb.adb_shell(f"mv {log_prefix}_iops.1.log {log_prefix}_iops.log", check=False)
                    self.adb.adb_pull(f"{log_prefix}_bw.log", str(self.output_dir / f"{case_id}_bw.log"))
                    self.adb.adb_pull(f"{log_prefix}_iops.log", str(self.output_dir / f"{case_id}_iops.log"))
                    
                    # 可选安全清理远端文件，防止把机器塞满
                    self.adb.adb_shell(f"rm {log_prefix}_*", check=False)
        
        logger.info("所有 FIO 性能测试阶段结束。")

    # 场景名别名映射表（FIO 原始前缀 -> 标准场景名）
    _SCENARIO_ALIAS = {
        "seqread":   "Seq_Read",
        "seqwrite":  "Seq_Write",
        "randread":  "Rand_Read",
        "randwrite": "Rand_Write",
        "seq_read":  "Seq_Read",
        "seq_write": "Seq_Write",
        "rand_read": "Rand_Read",
        "rand_write": "Rand_Write",
    }

    def _find_bw_iops_log(self, search_dir, mode, case, rnd, log_type):
        """
        在 search_dir 中查找指定场景/轮次的 BW 或 IOPS 日志文件。
        兼容两种命名格式：
          1. 标准格式：{mode}_{case}_{rnd}_{log_type}.log
          2. FIO 原始格式：{case_lower}_bw.log_{log_type}.{rnd}.log
        """
        # 格式1：标准格式
        std = search_dir / f"{mode}_{case}_{rnd}_{log_type}.log"
        if std.exists():
            return std

        # 格式2：FIO 原始格式，反向查找别名
        case_lower = case.lower().replace("_", "")
        fio_pat = re.compile(
            rf"^{re.escape(case_lower)}_(?:bw|iops)\.log_{re.escape(log_type)}\.{rnd}\.log$",
            re.IGNORECASE
        )
        for fp in search_dir.iterdir():
            if fio_pat.match(fp.name):
                return fp
        return None

    def generate_report(self, mode="perf", rounds=3, source_dir=None):
        import matplotlib.pyplot as plt
        import matplotlib
        
        # 解决 matplotlib 中文乱码和负号显示问题
        matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS']
        matplotlib.rcParams['axes.unicode_minus'] = False
        
        logger.info("开始提取 FIO 核心性能指数...")
        
        scenarios = ["Seq_Read", "Seq_Write", "Rand_Read", "Rand_Write"]
        summary_data = []

        # 解析普通原始日志而不是 JSON
        for case in scenarios:
            for i in range(1, rounds + 1):
                case_id = f"{mode}_{case}_{i}"
                log_file = self.output_dir / f"{case_id}.log"
                
                if not log_file.exists():
                    continue
                    
                with open(log_file, 'r', encoding='utf-8') as f:
                    try:
                        content = f.read()
                        
                        # 解析带宽 BW (优先抓取括号内的 MB/s)
                        bw_m = re.search(r'BW=.*?\((\d+(?:\.\d+)?)(k?B|m?B|g?B)/s\)', content, re.IGNORECASE)
                        bw_val = 0.0
                        if bw_m:
                            v = float(bw_m.group(1))
                            unit = bw_m.group(2).lower()
                            if 'k' in unit: v /= 1000
                            elif 'g' in unit: v *= 1000
                            bw_val = round(v, 2)
                        else:
                            # 兜底匹配 MiB 格式并转换为 MB 逻辑
                            bw_m = re.search(r'BW=\s*([\d.]+)([KMGTk]i?B)/', content, re.IGNORECASE)
                            if bw_m:
                                v = float(bw_m.group(1))
                                unit = bw_m.group(2).lower()
                                if 'k' in unit: v /= 1024
                                elif 'g' in unit: v *= 1024
                                bw_val = round(v, 2)
                        
                        # 解析 IOPS
                        iops_m = re.search(r'iops\s*:\s*min=[^,]+,\s*max=\s*(\d+)', content)
                        iops_max = int(iops_m.group(1)) if iops_m else 0
                        
                        # 解析平均 IOPS
                        avg_iops_m = re.search(r'IOPS=\s*([\d.]+)', content)
                        avg_iops = round(float(avg_iops_m.group(1)), 2) if avg_iops_m else 0
                        
                        # 解析 P99.9 百分位延迟 (取消换算，直接取原始数值)
                        p999_raw = 0.0
                        val_m = re.search(r'99.90th=\[\s*(\d+)\s*\]', content)
                        if val_m:
                            p999_raw = float(val_m.group(1))
                        
                        lat_max_ms = p999_raw # 此时内容已变为 P99.9 原始数值
                            
                        # 解析 CPU 利用率
                        cpu_m = re.search(r'cpu\s*:\s*usr=([\d.]+)%\s*,\s*sys=([\d.]+)%\s*', content)
                        cpu_usr = float(cpu_m.group(1)) if cpu_m else 0.0
                        cpu_sys = float(cpu_m.group(2)) if cpu_m else 0.0
                        
                        # 解析 MMC 利用率 util=100.00%
                        util_m = re.search(r'util=([\d.]+)%[;\s\n]', content)
                        emmc_util = float(util_m.group(1)) if util_m else 0.0
                            
                        summary_data.append({
                            "Scenario": case,
                            "Round": i,
                            "Avg BW (MB/s)": bw_val,
                            "IOPS": avg_iops,
                            "Avg BW Text": f"{bw_val}MB/s",
                            "Max IOPS": iops_max,
                            "Max Latency (ms)": lat_max_ms,
                            "CPU Sys (%)": cpu_sys,
                            "CPU Usr (%)": cpu_usr,
                            "EMMC Util (%)": emmc_util
                        })
                    except Exception as e:
                        logger.error(f"解析 {case_id}.log 异常: {e}")
                        
        # 将原始清单全盘转储给最后的 Report 卡片组装机
        if summary_data:
            with open(self.output_dir / f"{mode}_fio_summary.json", 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=4, ensure_ascii=False)
            logger.info("本轮次全景数据记录点已缓存。")
            
        # [稳定性测试专属渲染逻辑]
        if mode == "stability":
            # source_dir 优先，否则退回到 output_dir
            plot_src = Path(source_dir) if source_dir else self.output_dir
            plot_out = Path(source_dir) if source_dir else self.output_dir
            logger.info(f"进入 Stability 稳定性模式绘图环境，读取目录: {plot_src}")

            import csv
            for case in scenarios:
                plt.figure(figsize=(14, 6))

                # ── 第一张图：带宽趋势 ────────────────────────────────────────
                plt.subplot(1, 2, 1)
                plt.title(f"{case} BW 带宽表现")
                plt.xlabel("测试时间 (秒)")
                plt.ylabel("带宽 BW (MB/s)")

                for i in range(1, rounds + 1):
                    bw_log = self._find_bw_iops_log(plot_src, mode, case, i, "bw")
                    if bw_log:
                        try:
                            times, bws = [], []
                            with open(bw_log, 'r') as csvf:
                                reader = csv.reader(csvf)
                                for row in reader:
                                    if len(row) >= 2:
                                        times.append(float(row[0].strip()) / 1000.0)
                                        # FIO BW 日志单位为 KB/s，转换为 MB/s
                                        bws.append(float(row[1].strip()) / 1024.0)
                            if times:
                                plt.plot(times, bws, label=f"Round {i}")
                        except Exception as e:
                            logger.error(f"带宽绘图异常 {bw_log}: {e}")
                    else:
                        logger.debug(f"未找到 BW 日志: case={case}, round={i}, dir={plot_src}")
                plt.legend()
                plt.grid(True, linestyle='--', alpha=0.6)

                # ── 第二张图：IOPS 抖动散点 ───────────────────────────────────
                plt.subplot(1, 2, 2)
                plt.title(f"{case} IOPS 抖动分布")
                plt.xlabel("测试时间 (秒)")
                plt.ylabel("IOPS (次/秒)")

                for i in range(1, rounds + 1):
                    iops_log = self._find_bw_iops_log(plot_src, mode, case, i, "iops")
                    if iops_log:
                        try:
                            times, iopss = [], []
                            with open(iops_log, 'r') as csvf:
                                reader = csv.reader(csvf)
                                for row in reader:
                                    if len(row) >= 2:
                                        times.append(float(row[0].strip()) / 1000.0)
                                        iopss.append(float(row[1].strip()))
                            if times:
                                plt.scatter(times, iopss, alpha=0.5, s=15, label=f"Round {i}")
                        except Exception as e:
                            logger.error(f"IOPS 绘图异常 {iops_log}: {e}")
                    else:
                        logger.debug(f"未找到 IOPS 日志: case={case}, round={i}, dir={plot_src}")
                plt.legend()
                plt.grid(True, linestyle='--', alpha=0.6)

                plt.tight_layout()
                out_png = plot_out / f"{mode}_{case}_performance_drifts.png"
                plt.savefig(out_png, dpi=150)
                plt.close()
                logger.info(f"  已生成: {out_png.name}")
            logger.info("散点与走势图表生成完毕，见输出目录。")
            
        logger.info(f"【{mode}模式】自动化分析与制图全部完成！")

    def generate_test_card(self):
        logger.info("正在按照标准 Word 模板生成聚合测试验证卡片 (Test Card)...")
        card_file = self.output_dir / "Test_Card_Report.md"
        
        with open(card_file, 'w', encoding='utf-8') as f:
            f.write("# EMMC 性能测试与验证报告\n\n")
            
            # 1. 核心快照 (对齐表格 0)
            f.write("## 1. 主要性能参数\n\n")
            f.write("| 主要参数/品牌 | 解析结果 | 影响 |\n|---|---|---|\n")
            snap_file = self.output_dir / "emmc_snapshot.json"
            j_data = {}
            if snap_file.exists():
                with open(snap_file, 'r', encoding='utf-8') as sj:
                    j_data = json.load(sj)
                    f.write(f"| 缓存 Cache Size | {j_data.get('Cache Size', 'N/A')} | 文件读写性能，开机读取缓存 |\n")
                    f.write(f"| 最大数据包(读取) Max Packet Read Cmd | {j_data.get('Max Packet Read Cmd', 'N/A')} | 并发读取能力 |\n")
                    f.write(f"| 最大数据包(写入) Max Packet Write Cmd | {j_data.get('Max Packet Write Cmd', 'N/A')} | 并发写入能力 |\n")
                    f.write(f"| TRIM Multiplier | {j_data.get('TRIM Multiplier', 'N/A')} | 操作效率表现及寿命表现 |\n")
                    f.write(f"| 扇区大小(容量) | {j_data.get('Capacity (GiB)', 'N/A')} | 实际容量 |\n")
                    f.write(f"| 睡眠电流 Sleep current(VCC/VCCQ) | {j_data.get('Sleep Current (VCC)', '-')} / {j_data.get('Sleep Current (VCCQ)', '-')} | 休眠功耗 |\n")
                    f.write(f"| High-capacity Wprotect | {j_data.get('HC WP Group Size', 'N/A')} | 预定义大批量分组操作尺寸 |\n")
                    f.write(f"| 休眠唤醒 Sleep/awake timeout | {j_data.get('Sleep / Awake Timeout', 'N/A')} | 休眠唤醒响应时长 |\n")
                    f.write(f"| CMDQ 状态队列深度 | 深度: {j_data.get('CMDQ Depth', 'N/A')} | 随机小文件并发提速序列 |\n")
                    
                    # 针对 MD 表格特殊处理换行符
                    card_type_display = j_data.get('Card Type', 'N/A').replace("\n", "<br>")
                    f.write(f"| 驱动强度 Card Type | {card_type_display} | EMMC 支持的驱动下行频率 |\n")
            f.write("\n")
            
            # 2. 详细跑分比对 (对齐表格 1～8)
            f.write("## 2. 基础性能测试（FIO）\n\n")
            perf_sum = self.output_dir / "perf_fio_summary.json"
            if perf_sum.exists():
                with open(perf_sum, 'r', encoding='utf-8') as sm:
                    perf_list = json.load(sm)
                
                scenarios_map = {
                    "Seq_Read": "顺序读取测试",
                    "Seq_Write": "顺序写入测试",
                    "Rand_Read": "随机读取测试",
                    "Rand_Write": "随机写入测试"
                }
                
                for code_name, zh_name in scenarios_map.items():
                    # 取出当前场景下的所有轮次数值进行并排排版
                    rounds_data = [x for x in perf_list if x["Scenario"] == code_name]
                    if not rounds_data:
                        continue
                        
                    f.write(f"### {zh_name}\n")
                    headers = ["参数/方式"] + [f"{zh_name.replace('测试','')} - 轮次 {r['Round']}" for r in rounds_data]
                    f.write("| " + " | ".join(headers) + " |\n")
                    f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
                    
                    # 构建行集合
                    rows = [
                        ("带宽", lambda x: str(x.get("Avg BW Text", f'{x.get("Avg BW (MB/s)")}MB/s'))),
                        ("IOPS", lambda x: str(x.get("IOPS", x.get("Max IOPS", 0)))), # TODO: 如果以后加上了 avg IOPS 可以改
                        ("MAXIOPS", lambda x: str(x.get("Max IOPS", 0))),
                        ("延迟<100000(最大us或ms)", lambda x: str(x.get("Max Latency (ms)", 0))),
                        ("CPU使用率", lambda x: f"{x.get('CPU Sys (%)', 0) + x.get('CPU Usr (%)', 0):.2f}%"),
                        ("EMMC利用率", lambda x: f"{x.get('EMMC Util (%)', 0)}%")
                    ]
                    
                    for r_title, r_func in rows:
                        line = [r_title] + [r_func(d) for d in rounds_data]
                        f.write("| " + " | ".join(line) + " |\n")
                    f.write("\n> 分析：(请在此填入该项目的最终判定，是否性能表现良好且利用率饱和等)\n\n")
            
            # 3. 稳定性视图
            f.write("## 3. EMMC稳定性测试\n\n")
            f.write("### (1) 高负载压测散点趋势图与日志截取\n")
            f.write("> 测试背景：挂载底层稳定性跑速，高负载队列下输出图表，持续压测运行观察带宽、IOPS 数据下沉情况。\n\n")
            
            stability_scenarios = {
                "Seq_Read": "顺序读",
                "Seq_Write": "顺序写",
                "Rand_Read": "随机读",
                "Rand_Write": "随机写入"
            }
            has_pics = False
            for code_name, zh_name in stability_scenarios.items():
                pic_name = f"stability_{code_name}_performance_drifts.png"
                if (self.output_dir / pic_name).exists():
                    has_pics = True
                    f.write(f"#### {zh_name} 稳定性切片：\n")
                    f.write(f"![{zh_name}]({pic_name})\n\n")
                    f.write(f"**【{zh_name} 分析】**：\n> 整体读写速率与图表 IOPS 利用率浮动分析情况如上所示。\n\n")
                    
            if not has_pics:
                f.write("> *(当前系统没有捕捉到稳定性图片产出，可能未执行 stability 测试)*\n\n")
                
            # 4. 可靠性推算
            f.write("## 4. EMMC可靠性寿命测试估算\n\n")
            type_a = j_data.get('Life Time Type A (MLC)', 'N/A')
            type_b = j_data.get('Life Time Type B (SLC)', 'N/A')
            pre_eol = j_data.get('Pre EOL Info', 'N/A')
            f.write(f"- eMMC Life Time Estimation A: `{type_a}`\n")
            f.write(f"- eMMC Life Time Estimation B: `{type_b}`\n")
            f.write(f"- PRE EOL Information: `{pre_eol}`\n")
            f.write("！！！！请自己根据数据来进行评估！！！！\n")
            
        logger.info(f"最终的 Markdown 级排版模板已成功生成至: {card_file.name}")
        
        # 同步核心 Markdown 报告至运行根目录（EXE 同级目录）
        import shutil
        try:
            shutil.copy2(card_file, self.root_dir / "Test_Card_Report.md")
            logger.info("已成功将 Markdown 报告同步至根目录。")
        except Exception as e:
            logger.warning(f"同步 Markdown 报告到根目录失败: {e}")

    def generate_word_report(self):
        try:
            from docx import Document
            from docx.shared import Inches, Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError:
            logger.error("未安装 python-docx 模块，无法生成 Word 报告。请打开终端运行: pip install python-docx")
            return

        logger.info("正在生成直接交付用的原生 Word 文档报告 (Test_Card_Report.docx)...")
        doc = Document()
        
        # 报表标题
        heading = doc.add_heading('EMMC 性能测试与验证报告', 0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 1. 核心快照
        doc.add_heading('1. EMMC主要性能参数', level=1)
        snap_file = self.output_dir / "emmc_snapshot.json"
        j_data = {}
        if snap_file.exists():
            with open(snap_file, 'r', encoding='utf-8') as sj:
                j_data = json.load(sj)
            
            table = doc.add_table(rows=1, cols=3)
            # 使用经典的带框线网格样式
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = '主要参数/品牌'
            hdr_cells[1].text = '解析结果'
            hdr_cells[2].text = '影响'
            
            rows_data = [
                ('缓存 Cache Size', j_data.get('Cache Size', 'N/A'), '文件读写性能，开机读取缓存'),
                ('最大数据包(读取) Max Packet Read Cmd', j_data.get('Max Packet Read Cmd', 'N/A'), '并发读取能力'),
                ('最大数据包(写入) Max Packet Write Cmd', j_data.get('Max Packet Write Cmd', 'N/A'), '并发写入能力'),
                ('TRIM Multiplier', j_data.get('TRIM Multiplier', 'N/A'), '操作效率表现及寿命表现'),
                ('扇区大小(容量)', j_data.get('Capacity (GiB)', 'N/A'), '实际容量'),
                ('睡眠电流 Sleep current(VCC/VCCQ)', f"{j_data.get('Sleep Current (VCC)', '-')} / {j_data.get('Sleep Current (VCCQ)', '-')}", '休眠功耗'),
                ('High-capacity Wprotect', j_data.get('HC WP Group Size', 'N/A'), '预定义大批量分组操作尺寸'),
                ('休眠唤醒 Sleep/awake timeout', j_data.get('Sleep / Awake Timeout', 'N/A'), '休眠唤醒响应时长'),
                ('CMDQ 状态队列深度', f"深度: {j_data.get('CMDQ Depth', 'N/A')}", '随机小文件并发提速序列'),
                ('驱动强度 Card Type', j_data.get('Card Type', 'N/A'), 'EMMC 支持的驱动下行频率')
            ]
            for row_dat in rows_data:
                row_cells = table.add_row().cells
                row_cells[0].text = row_dat[0]
                row_cells[1].text = row_dat[1]
                row_cells[2].text = row_dat[2]
                
        doc.add_paragraph("")
                
        # 2. 性能测试 (FIO)
        doc.add_heading('2. EMMC性能测试（FIO）', level=1)
        perf_sum = self.output_dir / "perf_fio_summary.json"
        if perf_sum.exists():
            with open(perf_sum, 'r', encoding='utf-8') as sm:
                perf_list = json.load(sm)
            
            scenarios_map = {
                "Seq_Read": "顺序读取测试",
                "Seq_Write": "顺序写入测试",
                "Rand_Read": "随机读取测试",
                "Rand_Write": "随机写入测试"
            }
            
            for code_name, zh_name in scenarios_map.items():
                rounds_data = [x for x in perf_list if x["Scenario"] == code_name]
                if not rounds_data:
                    continue
                
                doc.add_heading(zh_name, level=2)
                cols_count = len(rounds_data) + 1
                perf_tbl = doc.add_table(rows=1, cols=cols_count)
                perf_tbl.style = 'Table Grid'
                
                hdr = perf_tbl.rows[0].cells
                hdr[0].text = '参数/方式'
                for idx, r in enumerate(rounds_data):
                    hdr[idx+1].text = f"{zh_name.replace('测试','')} - 轮次 {r['Round']}"
                    
                rows = [
                    ("带宽", lambda x: str(x.get("Avg BW Text", f'{x.get("Avg BW (MB/s)")}MB/s'))),
                    ("IOPS", lambda x: str(x.get("IOPS", x.get("Max IOPS", 0)))),
                    ("MAXIOPS", lambda x: str(x.get("Max IOPS", 0))),
                    ("延迟<100000(最大us或ms)", lambda x: str(x.get("Max Latency (ms)", 0))),
                    ("CPU使用率", lambda x: f"{x.get('CPU Sys (%)', 0) + x.get('CPU Usr (%)', 0):.2f}%"),
                    ("EMMC利用率", lambda x: f"{x.get('EMMC Util (%)', 0)}%")
                ]
                
                for r_title, r_func in rows:
                    r_cells = perf_tbl.add_row().cells
                    r_cells[0].text = r_title
                    for idx, d in enumerate(rounds_data):
                        r_cells[idx+1].text = r_func(d)
                        
                doc.add_paragraph("分析：(请在此填入该项目的最终判定，是否性能表现良好且利用率饱和等)").style = 'List Bullet'
                doc.add_paragraph("")
                
        # 3. 稳定性视图
        doc.add_heading('3. 存储稳定性测试', level=1)
        doc.add_heading('(1) 高负载压测散点趋势图与日志截取', level=2)
        doc.add_paragraph("测试背景：挂载底层稳定性跑速，高负载队列下输出图表，持续压测运行观察带宽、IOPS 数据下沉情况。")
        
        stability_scenarios = {
            "Seq_Read": "顺序读",
            "Seq_Write": "顺序写",
            "Rand_Read": "随机读",
            "Rand_Write": "随机写入"
        }
        
        has_pics = False
        for code_name, zh_name in stability_scenarios.items():
            pic_name = f"stability_{code_name}_performance_drifts.png"
            pic_path = self.output_dir / pic_name
            if pic_path.exists():
                has_pics = True
                doc.add_heading(f"{zh_name} 稳定性切片：", level=3)
                doc.add_picture(str(pic_path), width=Inches(6.0))
                doc.add_paragraph(f"【{zh_name} 分析】：整体读写速率与图表 IOPS 利用率浮动分析情况如上所示。").style = 'List Paragraph'
                
        if not has_pics:
            doc.add_paragraph("(当前系统没有捕捉到稳定性图片产出，可能未执行 stability 测试)")
            
        # 4. 可靠性推算
        doc.add_heading('4. 存储可靠性寿命测试估算', level=1)
        type_a = j_data.get('Life Time Type A (MLC)', 'N/A')
        type_b = j_data.get('Life Time Type B (SLC)', 'N/A')
        pre_eol = j_data.get('Pre EOL Info', 'N/A')
        
        doc.add_paragraph(f"Life Time Estimation A: {type_a}", style='List Bullet')
        doc.add_paragraph(f"Life Time Estimation B: {type_b}", style='List Bullet')
        doc.add_paragraph(f"PRE EOL Information: {pre_eol}", style='List Bullet')
        
        b = doc.add_paragraph()
        b.add_run("结论：").bold = True
        b.add_run("！！！！请自己根据板卡数据进行评估！！！！")
        
        word_file = self.output_dir / "Test_Card_Report.docx"
        doc.save(word_file)
        logger.info(f" 原生 Word 版本报告已成功投递保存至: {word_file.name}")
        
        # 同步核心 Word 报告至运行根目录（EXE 同级目录）
        import shutil
        try:
            shutil.copy2(word_file, self.root_dir / "Test_Card_Report.docx")
            logger.info("已成功将 Word 报告同步至根目录。")
        except Exception as e:
            logger.warning(f"同步 Word 报告到根目录失败: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="存储自动化性能测试与分析工具")
    parser.add_argument("--mmc-block", type=str, default=None, help="手动指定存储路径挂载节点 (例如 /dev/block/mmcblk0)")
    parser.add_argument("--mode", type=str, choices=['perf', 'stability', 'both'], default='both', help="测试模式: perf/stability/both(顺序执行)")
    parser.add_argument("--fio-runtime", type=int, default=None, help="重写时效长")
    parser.add_argument("--fio-rounds", type=int, default=None, help="重写执行轮数")
    parser.add_argument(
        "--plot-dir", type=str, default=None,
        help="独立绘图模式：指定包含 FIO 日志的目录，直接生成稳定性曲线图，无需 ADB 连接"
    )
    parser.add_argument(
        "--plot-rounds", type=int, default=1,
        help="独立绘图模式下的轮次数（默认 1）"
    )
    args = parser.parse_args()

    # ── 独立绘图模式（--plot-dir），无需 ADB ────────────────────────────────
    if args.plot_dir:
        plot_dir = Path(args.plot_dir)
        if not plot_dir.is_dir():
            logger.error(f"指定的目录不存在: {plot_dir}")
            sys.exit(1)

        logger.info(f"独立绘图模式启动，日志目录: {plot_dir}")

        # 构造一个最小化 tester（不执行 ADB 操作）
        class _FakeAdb:
            def execute(self, *a, **kw): pass
            def adb_shell(self, *a, **kw): pass

        tester = EMMCTester(_FakeAdb())
        # 覆盖 output_dir，使生成的图片保存到目标目录下
        tester.output_dir = plot_dir

        tester.generate_report(
            mode="stability",
            rounds=args.plot_rounds,
            source_dir=plot_dir
        )
        logger.info(f"曲线图已保存至: {plot_dir}")
        sys.exit(0)

    # ── 正常测试模式（需要 ADB）────────────────────────────────────────────
    adb = AdbRunner()
    tester = EMMCTester(adb, args.mmc_block)

    tester.setup_env()
    tester.detect_mmc_node()
    tester.extcsd_read()

    if args.mode in ['perf', 'both']:
        rtime = args.fio_runtime if args.fio_runtime else 60
        rrounds = args.fio_rounds if args.fio_rounds else 3
        tester.run_fio_tests(mode="perf", runtime=rtime, rounds=rrounds)
        tester.generate_report(mode="perf", rounds=rrounds)

    if args.mode in ['stability', 'both']:
        rtime = args.fio_runtime if args.fio_runtime else 300
        rrounds = args.fio_rounds if args.fio_rounds else 1
        tester.run_fio_tests(mode="stability", runtime=rtime, rounds=rrounds)
        tester.generate_report(mode="stability", rounds=rrounds)

    tester.generate_test_card()
    tester.generate_word_report()
