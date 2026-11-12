# RR-ADB-001：A133P 真机只读兼容性/可靠性审计

- 评审编号：RR-ADB-001
- 评审对象/任务编号：ADB 设备兼容性与可靠性审计（阶段一；联动 T-19/T-36/UPFM 画像）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：
  - `test-platform/test-tools/upfm/host/board_profiles.py`（当前工作区，HEAD d0b415d，a133p 画像见 71-115 行）
  - `docs/contracts/README.md` v1.0、`docs/design/scheduler-and-data.md` v1.0（设备状态与部署约束）
  - `docs/verification/verification-rules-v1.0.md` §8（实机证据与 skip 边界）
- 环境与 commit/变更集：
  - 主机：Windows 10（10.0.26200）；adb 1.0.41 / 35.0.2-12147458（`D:\andriod\platform-tools-latest-windows\platform-tools\adb.exe`）
  - 设备 serial：`5c000c2834414751c9d`（注意：与画像注释中的 `9c000c8a230487920dd` 为**不同实体**）
  - git HEAD：`d0b415d`；纯只读审计，零设备写入、零业务变更
- 证据路径：`docs/verification/reviews/evidence/adb-a133p-20261112/`（01-devices.log … 17-uptime.log，共 17 份，每份含命令、时间戳、退出码、原始输出）

## 1. 检查项与结论（画像对照）

审计命令全部为只读（getprop / wm / df / cat / ls / dumpsys / pm list features / settings get / getevent -p / uptime）；未执行 push/install/reboot/setprop/开关服务等任何写操作。

| # | 画像项 | board_profiles.py a133p 期望 | 实机实测（5c000c2834414751c9d） | 证据 | 结论 |
|---|---|---|---|---|---|
| 1 | identify ro.mc.cpu | `A133P` | `A133P` | 02/05 | 一致 |
| 2 | identify ro.product.device | `A133P` | `A133P`（board=`exdroid`） | 02 | 一致（board 与 Lead 口头口径"ceres"不符，以实测为准） |
| 3 | Android 版本/SDK | ANDROID10.0 / Android 10 | release=10, sdk=29, ro.mc.android_version=ANDROID10.0 | 03/05 | 一致 |
| 4 | CPU available_freqs | `408000 600000 816000 1008000 1200000 1416000 1608000 1800000` | 完全一致（8 档） | 11 | 一致 |
| 5 | CPU max_freq | `1800000` | `1800000` | 11 | 一致 |
| 6 | GPU supported=False（/sys/class/devfreq 空） | 空 | `ls -la /sys/class/devfreq` 目录为空（total 0） | 09 | 一致 |
| 7 | DDR clk_pattern=ddr, clk_name=pll_ddr, 1584000000 | pll_ddr … 1584000000 | `pll_ddr 1 1 1584000000`（clk_summary 可读，root 权限） | 15 | 一致 |
| 8 | touch expected_points=32（cyttsp5_mt，ABS_MT_SLOT max=31） | — | 触摸设备为 **"techwin"**（event4）：无 ABS_MT_SLOT，ABS_MT_TRACKING_ID(0039) max=9 → **10 点**；另有 MH248(008e/008f)、axp2202-pek、sunxi-codec、sunxi-keyboard | 14 | **不一致（高风险，见 P-A1）** |
| 9 | bluetooth supported=True（开关崩溃风险） | 崩溃/开关风险（2026-07-31 记录） | features 声明 bluetooth+bluetooth_le；bluetooth_on=0，state OFF，`Bluetooth never enabled!`，`crashed 0 times` | 12/13 | 部分一致：当前为全新开机态（up 2:37，从未开过蓝牙），崩溃行为本轮无法复验（只读限制），见 P-A4 |
| 10 | mc_props android_version | ANDROID10.0 | ANDROID10.0 | 05 | 一致 |
| 11 | mc_props custom_api_version | `""`（空） | `1` | 05 | **不一致（见 P-A3）** |
| 12 | mc_props oem.version | `""` | 空（第 4 行空行） | 05 | 一致 |
| 13 | mc_props product | `F7G18PD_HZCL01/HangZhouZeTianChunLai/ShuiZhiJianCe` | `FE7G18P/Standard` | 05 | **不一致（P-A3）** |
| 14 | mc_props version / version_code | `2.1.0` / `3` | `6.5.5` / `6` | 05 | **不一致（P-A3）** |
| 15 | emmc/ddr 二进制架构匹配 | — | 设备 abilist=`armeabi-v7a,armeabi`（zygote32）；emmc 有 armeabi-v7a fio/mmc_utils；ddr **仅有** armeabi-v7a 三件 | 04 + 本地目录清单 | 当前板可用；换 arm64 板 ddr 无 64 位二进制（见 P-A2） |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任任务 |
|---|---|---|---|---|---|
| P-A1 | 触摸画像与实机不符：画像期望 32 点（cyttsp5_mt / ABS_MT_SLOT max=31），本机触摸控制器为 techwin，无 SLOT，TRACKING_ID max=9 → 10 点，与 rk3568 画像的触摸描述一致（techwin 面板） | evidence/14-touch-getevent.log；board_profiles.py:96-99 vs :53-56 | touch_points 用例按画像 32 判定将在本机 FAIL（或按实机判定则画像失效）。画像以"板型"为键，但同板型存在不同触摸面板/固件组合，画像维度不足 | 高 | T-36（画像口径）；本轮记录 |
| P-A2 | ddr 工具链仅 armeabi-v7a：`test-tools/ddr/binaries/` 下只有 armeabi-v7a/{memtester,stress-ng,stressapptest}，无 arm64-v8a；A133P（32 位）可用，rk3568（arm64 用户态）能否执行取决于内核 compat，未验证 | 本地目录清单 + evidence/04 | ddr 测试换板即缺工具；T-17 manifest 若声明全架构会与实际不符 | 中 | T-17/T-36 |
| P-A3 | mc_props 四项期望值与实机不一致（custom_api_version、product、version、version_code），系同板型不同固件版本（画像 2.1.0/3 vs 实机 6.5.5/6） | evidence/05；board_profiles.py:106-114 | mc_props_check 按画像判定将 FAIL；若反过来"以实机为准"则画像失去回归意义。需要明确口径（见待确认 U4） | 高（对 UPFM 判定）/低（对批次 G 开发） | T-36、用户 |
| P-A4 | 蓝牙崩溃风险未复验：只读审计禁止开关蓝牙；本机当前 OFF 且从未开启，无崩溃记录。画像的"开关后协议栈反复崩溃"仍为 2026-07-31 历史观测 | evidence/12/13；board_profiles.py:100-104 | 蓝牙开关用例在本机上的行为当前不可断言；实机执行时须先重测并如实记录 | 中 | T-36/实机项 |
| P-A5 | 内存/负载可靠性：MemTotal≈1.93GiB，MemFree 仅 51.7MB，MemAvailable≈500MB，SwapTotal 1.48GiB（已用≈58MB），Committed_AS 15.5GB 远超 CommitLimit 2.5GB；idle 负载 load average 8.66/8.70/8.72（0 users，up 2:37） | evidence/08/17 | 设备长期高负载+低余量内存，fio/stressapptest 等压测及并行测试易触发 OOM/低内存杀进程，导致结果波动；建议实机任务串行执行并在报告记录内存快照 | 中 | 实机执行策略（记录性） |
| P-A6 | 根分区 100%：`/dev/block/dm-0` 881M 用满（余 2.6M），`/data` 3.4G 余 3.0G | evidence/07 | 系统分区只读满载属正常；但任何向 / 或 /system 写入的测试设计必然失败；/data 余量对大文件 fio 压测（如 3.0G 上限）需预留 | 低 | T-36/实机项 |
| P-A7 | Lead 简报中 board=ceres 与实测 `ro.product.board=exdroid` 不符 | evidence/02 | 简报口径修正；以 getprop 为准 | 低 | 记录性 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 蓝牙开关崩溃复现 | 只读审计禁止 svc/settings 写操作 | P-A4 保持"未复验" |
| L2 | fio/stressapptest/memtester 实际运行 | 需 push 二进制到设备（写操作，禁止） | 二进制可执行性、兼容性未实测；仅架构匹配静态核对 |
| L3 | 触摸面板物理点数 | 驱动上报槽位≠物理点数，需人工多点触控（人工项禁止） | 10 点为驱动上限，非面板实测 |
| L4 | Android 9/10.1、arm64 板 | 无设备 | 契约兼容矩阵相应维度"无法核验" |

## 4. 待用户确认项

| # | 事项 | 建议决定 | 处置 |
|---|---|---|---|
| U4 | mc_props/touch 画像口径（P-A1/P-A3） | 画像标注适用固件版本与面板型号；判定冲突时记 SKIP/待确认而非 FAIL；实机值只作回归基线（与 verification-rules §8 一致） | **Lead 2026-11-12 裁决：画像期望=固件特定期望、实机实测=回归基线，双列记录；touch 10 vs 画像 32、mc_props 四项、board=exdroid、serial 为另一台实体等冲突一律标 SKIP/待用户确认，不得判 FAIL 作为交付证据** |
| U7 | 是否为 ddr 工具补 arm64-v8a 二进制（P-A2） | 若 rk3568 在交付范围内则必须补并实测；否则 manifest 明确声明仅 32 位支持 | 待用户确认 |

## 5. 独立重跑记录

不适用（本记录本身即独立执行的原始审计；17 条命令输出见 evidence 目录，全部退出码 0，执行时间 2026-11-12 11:45:23–11:45:28 +08:00）。无任何写设备命令。

## 6. 最终结论

**有条件通过（作为环境兼容性基线）。** 设备可服务批次 G 的 ADB 只读抽查与后续只读实机项；但 ①touch/mc_props 画像偏差（P-A1/P-A3）按 Lead U4 裁决以"画像=固件期望、实机=回归基线"双列记录，冲突项标 SKIP/待用户确认，**不得判 FAIL 作为交付证据**；②ddr 32 位限制与内存/负载风险（P-A2/P-A5）写入实机执行注意事项。本记录不签发任何"实机通过"。

**兼容性覆盖范围（写入最终整体结论）：本轮实机仅覆盖 Android 10 / SDK 29 / armeabi-v7a（32 位）一种形态；Android 9、10.1、arm64（rk3568）等其他契约兼容维度均「无法核验」。**

## 7. 签名

reviewer，2026-11-12；本记录基于原始终端证据独立作出，未代开发修改任何代码，未对设备执行任何写操作。

## 7. 签名

reviewer，2026-11-12；本记录基于原始终端证据独立作出，未代开发修改任何代码，未对设备执行任何写操作。
