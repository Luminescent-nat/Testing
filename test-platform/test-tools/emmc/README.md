# EMMC 存储测试工具

本目录包含 EMMC 性能与信息测试所需的设备端二进制、PC 端执行脚本及报告生成能力。

## 目录结构

```
emmc/
├── binaries/                      # 设备端可执行文件，按架构存放
│   ├── arm64-v8a/
│   │   ├── fio
│   │   └── mmc_utils
│   └── armeabi-v7a/
│       ├── fio
│       └── mmc_utils
└── host/                          # PC 端脚本
    ├── emmc_tester.py             # 完整测试入口
    ├── emmc_extcsd_runner.py      # 仅读取 extcsd
    ├── emmc_fio_runner.py         # 仅执行 fio 单场景
    └── emmc_report.py             # 基于日志生成报告
```

## 脚本说明

### emmc_tester.py（推荐统一入口）

一次执行完整的 EMMC 测试流程：
1. `adb root` 获取权限；
2. 按设备架构推送 `fio` 和 `mmc_utils`；
3. 自动识别 eMMC 节点；
4. 读取并解析 extcsd；
5. 执行 FIO 性能 / 稳定性测试；
6. 生成 Markdown 测试报告。

```bash
python emmc/host/emmc_tester.py --serial <adb_serial> --mode both --rounds 3
```

参数：
- `--serial`: ADB 设备序列号；
- `--mode`: `perf` / `stability` / `both`；
- `--runtime`: fio 运行时长（秒），perf 默认 60，stability 默认 300；
- `--rounds`: 每个场景执行轮数；
- `--output-dir`: 报告输出目录，默认 `./report/emmc_test_<timestamp>`。

### emmc_extcsd_runner.py

仅读取 eMMC extcsd 寄存器信息，输出 JSON。

```bash
python emmc/host/emmc_extcsd_runner.py --serial <adb_serial>
```

### emmc_fio_runner.py

仅执行单个 FIO 场景，输出 JSON 性能指标。

```bash
python emmc/host/emmc_fio_runner.py --serial <adb_serial> --mode seq_read --runtime 60
```

### emmc_report.py

基于已有 FIO 日志生成聚合 Markdown/JSON 报告。

```bash
python emmc/host/emmc_report.py \
  --output-dir ./report \
  --seq-read-log seq_read.log \
  --seq-write-log seq_write.log \
  --rand-read-log rand_read.log \
  --rand-write-log rand_write.log
```

## 与后端测试平台集成

在测试平台中创建 EMMC 测试项时，建议：

- **模块**: EMMC / 存储
- **执行方式**: `host_exec`
- **执行命令**: `python test-tools/emmc/host/emmc_tester.py --serial {{device_serial}} --mode perf --rounds 3`
- **判定方式**: `ai_fallback` 或 `assertion`
- **标签**: `performance`, `emmc`, `storage`

测试项可通过 `{{device_serial}}` 占位符由执行引擎替换为实际设备序列号。
