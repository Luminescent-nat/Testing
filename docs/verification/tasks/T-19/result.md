# T-19 移除 test-tools ADB runner shell 拼接 — 结果记录

- 任务编号：T-19（共享任务板 task-4，owner=infra-tools）
- 执行人：infra-tools（Agent Team）
- 日期：2026-11-12（Asia/Shanghai，UTC+08:00）

## 0. 核心契约声明（Lead 要求显式写明）

**本地 `subprocess.run` 一律参数数组 + `shell=False`，本地 shell 永不解释元字符；
远端 `adb shell` 语义保持**：`shell()` 把整条命令作为 `adb shell` 的**单个参数**传给
adb，管道/分号/引号/glob 等仍由**设备端 shell** 解释，与重构前行为一致。
`run(str)`/`shell(str)`/`push`/`pull`/`root` **签名全部兼容**（str 用 shlex 安全解析，
Windows 反斜杠路径做转义保护；`" ".join(...)`/f-string/带引号写法照常工作），
另提供显式 `list[str]` 参数数组 API（`run(list)`、`shell(list)`）。
**未批量改动调用方**（30+ 处调用点原样保留，见第 6 节清单）。

## 1. 变更文件

| 文件 | 变更 |
|---|---|
| `test-platform/test-tools/common/adb_runner.py` | 重写：全部 `subprocess.run(argv, shell=False)`；新增 `normalise_tokens()`（str→shlex 解析/拒空命令/空参数/NUL/非字符串项，Windows 反斜杠转义保护）、`last_command`（完整 argv list）、`last_error`（timeout/file-not-found/exit-code/invalid-command/os-error）；`run(list[str]\|str)`、`shell(str\|list)` 远端单参数、`push/pull` 参数化+空参拒绝、`root` 参数化；新增构造参数 `adb`（可注入参数序列，供测试用真实子进程）、`default_timeout`、`check_adb`；超时返回 None、FileNotFoundError 原样抛出、非零码返回 CompletedProcess——**None 语义与旧调用方完全兼容** |
| `test-platform/test-tools/common/device_info.py` | 调用同步：`detect_arch` 改参数数组 `adb.shell(["getprop", "ro.product.cpu.abi"])`；`detect_mmc_node` 含远端管道 `ls /sys/block/ | grep mmcblk` 保持字符串形态（整条作为远端单参数，`|` 由设备端 shell 解释），并注释说明 |
| `test-platform/backend/tests/unit/test_adb_runner.py` | 新增 25 个契约用例（先红后绿）：真实 subprocess（临时 fake adb，路径带空格）捕获 argv、monkeypatch 间谍断言 `shell` 为 False、str/引号/Windows 路径、管道与元字符不被本地解释（marker 文件不落盘）、push/pull/root 参数化、空命令/空参数拒绝、超时/非零码/adb 缺失可追踪、device_info 调用形态 |
| `docs/verification/tasks/T-19/*` | 本记录、原始日志、真机只读验证脚本 |

未触碰：`backend/app/`、`frontend/`、`Dockerfile`、以及第 6 节全部调用方脚本（范围外，未批量改动）。

## 2. 环境

- OS：Windows 10（主机 MCTECH）
- Python：3.12.10（`D:\MCTEST\test-platform\.venv\Scripts\python.exe`）
- pytest 7.4.4 / pytest-asyncio 0.23.3（backend/tests 下）
- ADB：`Android Debug Bridge version 1.0.41`（35.0.2-12147458，`D:\andriod\platform-tools-latest-windows\platform-tools\adb.exe`）
- 真机（只读）：serial `5c000c2834414751c9d`，A133P/A133P/Android 10/SDK 29，cpu.abi=armeabi-v7a

## 3. 命令、起止时间与退出码

| # | 命令（WORKDIR） | 起 | 止 | 退出码 | 结果 |
|---|---|---|---|---|---|
| 1 | `python -m pytest tests/unit/test_adb_runner.py -q`（backend，实现前红测） | 11:48:25 | 11:48:27 | 1 | 24 failed（无 `adb=`/`last_command` 等契约，device_info 仍传 str）+ 1 passed（远端管道保持 str） |
| 2 | `python docs/verification/tasks/T-19/verify_device_readonly.py`（MCTEST，真机只读） | 11:56:06 | 11:56:06 | 1 | 首跑 5/7：2 项为验证脚本自身缺陷（version 断言写错、同进程连导多模块触发既有 stdout 包装怪癖），非 runner 缺陷；修复脚本后重跑 |
| 3 | `python docs/verification/tasks/T-19/verify_device_readonly.py`（MCTEST，终版） | 11:57:02 | 11:57:03 | 0 | **7/7 PASS**（3 条真机只读命令 + argv 形态 + detect_arch + 22 文件 py_compile + 6 调用方模块独立子进程导入） |
| 4 | `python -m pytest tests/unit/test_adb_runner.py -q`（backend，实现后绿测） | 11:57:21 | 11:57:25 | 0 | **25 passed** |
| 5 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`（backend，全量回归） | 11:57:37 | 11:59:42 | 0 | **236 passed**（基线 189，0 failed，无删除/跳过/放宽） |

## 4. 原始日志与产物

- `docs/verification/tasks/T-19/pytest-T19-red-20261112.log` — 实现前红测完整输出
- `docs/verification/tasks/T-19/verify-device-readonly-20261112.log` — 真机只读验证原始输出（argv/exit/stdout/stderr 全量）
- `docs/verification/tasks/T-19/verify_device_readonly.py` — 验证脚本（可复现）
- `docs/verification/tasks/T-19/pytest-T19-green-20261112.log` — 实现后绿测
- `docs/verification/tasks/T-19/regression-full-20261112.log` — 全量回归（236 passed）

真机只读验证原始结论（经 `AdbRunner(serial="5c000c2834414751c9d")`）：

```
argv=['adb','-s','5c000c2834414751c9d','version']                      -> exit=0, Android Debug Bridge version 1.0.41 ...
argv=['adb','-s','5c000c2834414751c9d','shell','getprop ro.product.cpu.abi'] -> exit=0, armeabi-v7a
argv=['adb','-s','5c000c2834414751c9d','shell','echo ok']              -> exit=0, ok
device_info.detect_arch -> armeabi-v7a（参数数组调用）
py_compile test-tools 全部 22 个 .py                                   -> PASS
独立子进程导入 6 个高频调用方模块（board_detect/touch_points/apk_install_check/emmc_tester/emmc_fio_runner/emmc_stability_runner）-> 全部 IMPORT_OK
```

单元测试关键证据（`pytest-T19-green-20261112.log`，25 项）：
- `test_subprocess_is_never_called_with_shell_true`：间谍捕获真实 `subprocess.run` 入参，argv 为 `list[str]`，`shell` 为 False；
- `test_shell_str_is_one_remote_argument_and_metacharacters_are_data`：`shell("echo ok; echo hacked > <marker> && echo $(id)")` 的 argv 末项为**整条原字符串**，marker 文件不落盘；
- `test_run_str_is_shlex_parsed_and_windows_paths_are_preserved`：`'install -r "C:\\tools\\my app.apk"'` → `['install','-r','C:\\tools\\my app.apk']`（引号剥离、反斜杠路径保留、含空格不拆裂）；
- `test_push_pull_root_are_parameterized`：`push("a & b.bin", "/sdcard/a; rm -rf /")` 全程单参数数组；
- `test_timeout_returns_none_and_is_tracked` / `test_nonzero_exit_code_is_tracked` / `test_missing_adb_binary_raises_and_is_tracked`：真实子进程超时→None+`last_error="timeout: …"`；exit 3→`last_error` 含退出码；adb 缺失→`FileNotFoundError` 且 `last_error="file-not-found: …"`。

## 5. DoD 逐条

| DoD | 状态 | 证据 |
|---|---|---|
| `subprocess.run` 全部参数数组 + `shell=False` | ✅ | 重写后的 `adb_runner.py`；`test_subprocess_is_never_called_with_shell_true` |
| `run(list[str]\|str)`，str 用 shlex 安全解析并拒绝空命令 | ✅ | `normalise_tokens()`；`test_run_rejects_empty_commands`（6 形态） |
| `shell(cmd)` 远端 adb shell 单条命令参数传递（本地不解释元字符） | ✅ | `test_shell_str_is_one_remote_argument...`、`test_shell_list_is_joined_into_single_remote_command` |
| `push/pull/root` 参数化 | ✅ | `test_push_pull_root_are_parameterized` |
| 超时/FileNotFoundError/非零码可追踪（保留 None 兼容 + last_error/last_command） | ✅ | 第 4 节异常三用例 + `last_command` 断言 |
| `common/device_info.py` 调用同步 | ✅ | 两个 device_info 用例 + 真机 `detect_arch` 通过 |
| `tests/unit/test_adb_runner.py` 正常/边界/异常，真实 subprocess 捕获参数 | ✅ | 25 用例（真实 fake-adb 子进程 + 间谍双保险），元字符不被本地 shell 解释 |
| 真机只读验证（version/getprop/echo ok）保存原始日志 | ✅ | `verify-device-readonly-20261112.log` 7/7 |
| 证据目录 `docs/verification/tasks/T-19/` | ✅ | 本目录 |
| 禁止改 backend/app、frontend、Dockerfile | ✅ 未改 | 见第 1 节 |
| 签名兼容、不批量改调用方（Lead 追加要求） | ✅ | 全部旧调用形态（str/f-string/`" ".join`/引号路径）原样可用，30+ 调用点零改动 |

## 6. 高风险残留调用方清单（本次范围外，未批量改动）

以下调用点继续使用**字符串**调用形态；经 `run()`/`shell()` 新实现安全（本地不解释元字符），
但其**远端语义**仍由设备端 shell 解释，参数内如含用户可控内容需自行校验（现状与重构前一致）：

| 文件 | 调用点（约数） | 形态 / 风险点 |
|---|---|---|
| `common/device_info.py` | 2 | 已参数化 1 处；远端管道 1 处保留 str |
| `upfm/host/touch_points.py` | 1 | `shell("getevent -pl")` |
| `upfm/host/toggle_check.py` | 8 | `svc`/`settings put`/`am broadcast` f-string |
| `upfm/host/storage_rw_check.py` | 6 | `sm list-volumes`、`ls /mnt/media_rw/`、`rm -f {remote_file}`、`root()` |
| `upfm/host/apk_install_check.py` | 3 | **`run(f'install -r "{apk_path}"')` 引号+Windows 路径**（已单测等价形态）、`pm list/uninstall` |
| `upfm/host/mc_props_check.py` | 1 | `shell(f"getprop {prop}")` |
| `upfm/host/board_detect.py` | 2 | `shell_out` helper、`AdbRunner(serial)` |
| `upfm/host/sleep_check.py` | 7 | `settings put` f-string（含 `args.timeout_ms`） |
| `upfm/host/mem_ratio_check.py` | 1 | `shell("dumpsys meminfo", timeout=60)` |
| `upfm/host/rotation_check.py` | 3 | `settings put {ns} {key} {value}` f-string |
| `upfm/host/ddr_freq_check.py` | 1 | `root()` |
| `emmc/host/emmc_extcsd_runner.py` | 6 | `root()`、`push`、`mkdir/chmod`、`{remote_mmc} extcsd read {mmc_node}` |
| `emmc/host/emmc_fio_runner.py` | 5 | `root()`、`push`、**`shell(" ".join(cmd_parts))`**、fio 参数拼接 |
| `emmc/host/emmc_stability_runner.py` | 8 | `root()`、`push/pull`×2、`shell(" ".join(cmd_parts))`、`rm {log_prefix}_*` 远端 glob |
| `emmc/host/emmc_tester.py` | ~13 | `root()`、`push`×2、`pull`×2、`mv/rm` 远端 glob、`shell(cmd)` 多形态 |

另记录一个**既有怪癖（与 T-19 无关，未改）**：upfm/emmc 多个脚本在 Windows 上于模块导入时
重包装 `sys.stdout = io.TextIOWrapper(...)`；同一进程连导多个模块时旧包装被 GC 会关闭底层
buffer，报 `I/O operation on closed file`。真实用法每脚本独立进程不受影响（验证脚本已按
独立子进程冒烟通过），建议后续统一到 `common/logger.py` 或延迟到 main() 处理。

## 7. 未验证项

1. `push/pull/root`、fio/eMMC 稳定性、APK 安装卸载的**端到端真机执行**未做（写操作/耗时，
   且 T-19 只读验证约束）；仅以单元契约（真实子进程捕获 argv）+ 独立子进程 import 冒烟覆盖。
2. `adb root` 真机行为未验证（会重启 adbd，非只读），仅 `root(wait=False)` 参数化单测。
3. POSIX 平台的 `run(str)` 反斜杠处理未实测（Windows 做转义保护，非 Windows 原样送 shlex）。
4. 真机命令**超时**路径未触发（只读命令秒回）；超时语义由 fake-adb 真实子进程验证。
5. `run(str)` 的罕见畸形引号（shlex 无法解析）→ 抛 ValueError 且 `last_error=invalid-command`，单测未穷举全部畸形输入。

## 8. 回退说明

1. `test-platform/test-tools/common/adb_runner.py`：恢复旧实现（字符串拼接 + `shell=True`）。
   **注意：旧实现是本地 shell 注入面，不建议回退**；如必须回退请同步恢复 `device_info.py`
   两处调用（`adb.shell("getprop ro.product.cpu.abi")` 与 `adb.shell("ls /sys/block/ | grep mmcblk")` 保持一致）。
2. 删除 `test-platform/backend/tests/unit/test_adb_runner.py` 与 `docs/verification/tasks/T-19/`。
3. 本次未 git commit；回退需手工反向编辑或经 Lead 确认后 `git restore` 对应文件。
4. 回退后运行 `python -m pytest tests -q` 确认无残留引用（全量当前 236 passed）。
