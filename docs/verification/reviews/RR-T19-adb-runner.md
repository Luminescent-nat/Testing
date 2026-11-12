# RR-T19：移除 ADB runner shell 拼接

- 评审编号：RR-T19
- 评审对象/任务编号：T-19（共享任务板 task-4，owner infra-tools）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/plan/task-board-v1.0.md` T-19、`docs/verification/verification-rules-v1.0.md` v1.0（输入校验/命令安全、实机只读证据）、Lead U6 裁决（保留 `shell(str)` 兼容签名 + 内部参数数组 + 新增 list API，禁止破坏性换签名）
- 环境与 commit/变更集：Windows 10，Python 3.12.10，pytest 7.4.4；adb 1.0.41(35.0.2)；真机 serial `5c000c2834414751c9d`（A133P/Android10/armeabi-v7a）；git HEAD `d0b415d` + 工作区。T-19 变更：`test-tools/common/adb_runner.py` 重写、`test-tools/common/device_info.py` 调用同步、新增 `backend/tests/unit/test_adb_runner.py`
- 证据路径：
  - 开发证据：`docs/verification/tasks/T-19/`（result.md、pytest-T19-red/green、verify-device-readonly-20261112.log、verify_device_readonly.py、regression-full-20261112.log）
  - 评审方独立重跑：`docs/verification/reviews/evidence/test-rerun-20261112/t19-device-readonly-reviewer.log`、`t19-compat-spotcheck-reviewer.log`、`backend-targeted-t01-t02-t19-reviewer.log`

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 只改声明 scope | `git status`/diff | 仅 adb_runner.py、device_info.py、test_adb_runner.py；未改 backend/app、frontend、Dockerfile、30+ 调用方脚本 | 通过 |
| 2 | 无 `shell=True`，本地全参数数组 | 读 adb_runner.py:148-156；grep 全 test-tools `shell=True/os.system/os.popen/subprocess.Popen` | `subprocess.run(argv, shell=False, ...)`；全 test-tools 0 处 `shell=True`/`os.system`/`os.popen` | 通过 |
| 3 | `run(str)` 兼容 f-string/引号/`" ".join` 形式 | 独立跑 normalise_tokens 抽查 | `settings put global airplane_mode_on 1`→token数组；`install -r "C:\tools\my app.apk"`→`['install','-r','C:\\tools\\my app.apk']`（引号剥离/反斜杠保留/空格不裂） | 通过 |
| 4 | 远端 `adb shell` 单参数语义保持 | 独立构造 argv（不执行） | `shell("ls /sys/block/ | grep mmcblk")`→argv `[adb,-s,SER,shell,'ls /sys/block/ | grep mmcblk']`（整条单参数）；`shell("echo ok; echo hacked > marker && echo $(id)")`→单参数；`shell(" ".join(cmd_parts))`→单参数 | 通过 |
| 5 | 元字符不被本地解释（marker 不落盘） | 单测 + 抽查 | test_adb_runner `test_shell_str_is_one_remote_argument...`、`test_run_special_characters_are_not_interpreted_locally` 断言 marker 不存在 | 通过 |
| 6 | push/pull/root 参数化 | 读 adb_runner.py:198-254；单测 | 全 argv；空参拒绝并记 last_error | 通过 |
| 7 | 超时/FileNotFoundError/非零码可追踪，None 语义兼容 | 读 adb_runner.py:157-177；单测 3 例 | timeout→None+last_error；缺失→raise FileNotFoundError+last_error；非零→CompletedProcess+last_error；last_command 完整 argv | 通过 |
| 8 | 签名兼容（U6）且 30+ 调用方零改动 | 读 result.md §6 清单；grep 调用方；抽查 2～3 个 | `run/shell/push/pull/root` 签名保留 str/list；调用方脚本未见改动；抽查 toggle_check/sleep_check(settings put f-string)、device_info(远端管道)、emmc_fio(`" ".join`) 形态均正常解析 | 通过 |
| 9 | 真机只读验证 7/7 | 独立运行 `verify_device_readonly.py` | 7/7 PASS：version/getprop abi/echo ok argv 正确、detect_arch、py_compile 22 文件、6 模块独立子进程 import | 通过（原始日志见证据） |
| 10 | py_compile 与 import 冒烟 | 独立运行脚本内含 | 22 个 test-tools .py 编译通过；6 个高频调用方模块 IMPORT_OK | 通过 |
| 11 | 25 单测 | 独立定向跑 | test_adb_runner.py 25 passed（并入 87 passed） | 通过 |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-T19-1 | 远端语义仍由设备端 shell 解释：`shell(str)` 整条作为远端单参数传入，若参数内混入用户可控内容仍可能在**设备端**被解释（本地已安全） | adb_runner.py:179-196；result.md §6 | 与重构前远端行为一致，未扩大攻击面；但字符串拼接调用方（toggle/sleep/rotation 的 `settings put {值}`）若值用户可控仍需调用方校验 | 低-中 | 后续 UPFM/调用方任务（T-36 等） |
| P-T19-2 | push/pull/root、fio/eMMC、APK 安装卸载端到端真机执行未做 | result.md §7.1 | 写操作类命令仅单测 argv 覆盖，实机未跑 | 低 | 实机执行阶段 |
| P-T19-3 | `run(str)` 畸形引号抛 ValueError（invalid-command）；POSIX 反斜杠分支未实测 | adb_runner.py:50-54；result.md §7.3/§7.5 | 边界输入未穷举；非 Windows 平台差异 | 低 | 记录性 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | adb root 真机行为 | 会重启 adbd、非只读 | 仅 root(wait=False) 参数化单测 |
| L2 | 真机超时路径 | 只读命令秒回 | 以 fake-adb 真实子进程验证超时语义 |
| L3 | push/pull/root/fio eMMC 端到端 | 写操作/耗时且本轮只读约束 | 未执行，记"未验证" |
| L4 | 独立全量回归当前 2 failed（test_judgement_engine） | T-06 并行编辑，与 T-19 无关；T-19 定向 25 passed；证据全量 236 passed 为 11:57 时间点 | 最终全量由 Lead 统一重跑 |

## 4. 待用户确认项

无新增（U6 已由 Lead 裁决并落实；实现符合"保留 str 签名 + 内部参数数组 + 新增 list API"）。

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `python docs/verification/tasks/T-19/verify_device_readonly.py` | 真机只读 **7/7 PASS**（version/getprop/echo ok/detect_arch/22 py_compile/6 import） | 0 | `evidence/test-rerun-20261112/t19-device-readonly-reviewer.log` |
| normalise_tokens + shell argv 抽查（f-string/引号/管道/`" ".join`） | 全部符合预期（见 §1 #3/#4） | 0 | `evidence/test-rerun-20261112/t19-compat-spotcheck-reviewer.log` |
| `pytest tests/unit/test_adb_runner.py`（并入定向跑） | 25 passed | 0 | `evidence/test-rerun-20261112/backend-targeted-t01-t02-t19-reviewer.log` |

## 6. 最终结论

**通过。** 本地 `subprocess.run` 全部参数数组 + `shell=False`，全 test-tools 无 `shell=True`/`os.system`/`os.popen`；`run(str)`/`shell(str)`/push/pull/root 签名兼容（U6），f-string、带引号路径、`" ".join`、远端管道/元字符形态经抽查逐项符合"本地不解释、远端单参数由设备端 shell 解释"；30+ 调用方零改动。独立真机只读验证 7/7 PASS（含 22 文件 py_compile、6 模块 import），单测 25 passed，定向回归 87 passed 退出码 0。P-T19-1～3 与未验证项（push/pull/root/fio/APK 端到端、adb root 真机、POSIX 反斜杠、真机超时）记入限制，不影响本任务命令安全与兼容结论。

## 7. 签名

reviewer，2026-11-12；本记录基于源码、单测、独立真机只读与兼容抽查日志作出，未替开发修改任何代码，未对设备执行写操作。
