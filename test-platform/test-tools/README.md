# 测试工具目录（test-tools）

本目录存放 Android 设备自动化测试所需的 PC 端脚本、设备端二进制工具及相关资源。

## 目录结构

```
test-tools/
├── README.md                      # 本说明
├── common/                        # 通用基础设施（所有模块可复用）
│   ├── adb_runner.py              # 统一 ADB 命令执行器
│   ├── device_info.py             # 设备架构 / eMMC 节点 / 工具路径解析
│   └── logger.py                  # 统一日志配置
├── emmc/                          # EMMC 存储测试
│   ├── binaries/                  # 设备端二进制，按 CPU 架构存放
│   │   ├── arm64-v8a/
│   │   │   ├── fio
│   │   │   └── mmc_utils
│   │   └── armeabi-v7a/
│   │       ├── fio
│   │       └── mmc_utils
│   ├── host/                      # PC 端执行脚本
│   │   ├── emmc_tester.py         # 统一入口：extcsd + fio + 报告
│   │   ├── emmc_extcsd_runner.py  # 仅读取 extcsd
│   │   ├── emmc_fio_runner.py     # 仅执行 fio 单场景
│   │   └── emmc_report.py         # 基于日志生成 Markdown/JSON 报告
│   └── README.md
├── ddr/                           # DDR 内存测试
│   └── binaries/
│       └── armeabi-v7a/
│           ├── memtester
│           ├── stress-ng
│           └── stressapptest
└── wifi_bt/                       # Wi-Fi / 蓝牙测试（待补充）
└── ethernet/                      # 以太网测试（待补充）
```

## 设计原则

1. **按模块组织**：每个硬件模块（emmc/ddr/wifi_bt/ethernet）独立目录，便于单独维护。
2. **按架构存放二进制**：`binaries/<arch>/` 避免 32/64 位工具混用导致设备上执行失败。
3. **通用能力下沉到 `common/`**：ADB 执行、设备信息识别、日志配置等能力复用，禁止各模块重复实现。
4. **PC 端脚本在 `host/` 下**：所有需要连接 ADB 在 PC 端运行的脚本统一放 `host/`。
5. **统一入口与原子脚本并存**：
   - `emmc/host/emmc_tester.py` 是一次性跑完 extcsd + fio + 报告的统一入口；
   - `emmc_extcsd_runner.py` / `emmc_fio_runner.py` 是原子能力，便于测试平台按测试项单独调用。

## EMMC 测试快速开始

```bash
# 进入 test-tools 根目录
cd D:\MCTEST\test-platform\test-tools

# 完整测试（性能 + 稳定性）
python emmc/host/emmc_tester.py --serial <adb_serial> --mode both

# 只读 extcsd
python emmc/host/emmc_extcsd_runner.py --serial <adb_serial>

# 只跑顺序读 fio
python emmc/host/emmc_fio_runner.py --serial <adb_serial> --mode seq_read --runtime 60
```

## 新增模块流程

1. 在 `test-tools/` 下新建模块目录，如 `wifi_bt/`。
2. 创建 `wifi_bt/binaries/<arch>/` 存放设备端二进制。
3. 创建 `wifi_bt/host/` 存放 PC 端执行脚本。
4. 脚本中优先复用 `common.adb_runner`、`common.device_info`。

## 与测试平台集成

后端测试项执行时，通过 `exec_type` 区分调用方式：

- `adb_shell`：直接通过 ADB 执行命令；
- `push_exec`：先推送 `binaries/<arch>/` 下的工具到设备，再执行；
- `host_exec`：在 PC 端调用 `host/` 下的脚本，由脚本负责 ADB 交互。

EMMC 推荐用 `host_exec` 调用 `emmc/host/emmc_tester.py`，由脚本统一管理 root、工具推送、日志收集和报告生成。
