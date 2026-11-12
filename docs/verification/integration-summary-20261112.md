# 批次 G 集成汇总与交付说明

- 日期：2026-11-12
- 范围：T-01、T-02、T-06、T-17、T-18、T-19、T-20、T-21（[任务板](../plan/task-board-v1.0.md) 批次 G 可并行项 + 判定基础 T-06）
- 依据：[实施方案](../plan/implementation-plan-v1.0.md)、[任务板](../plan/task-board-v1.0.md)、[接口契约 v1.0](../contracts/README.md)、[执行状态机 v1.0](../design/execution-state-machine.md)、[调度与数据 v1.0](../design/scheduler-and-data.md)、[UI token v1.0](../design/ui-tokens.md)、[验证规则 v1.0](verification-rules-v1.0.md)
- 门禁：T-22～T-34 仍须用户确认组件/页面契约与六段规格后才可实施，本批次未启动
- 说明：本文件为 Lead 集成记录；逐任务证据见 [tasks/](README.md)，独立评审记录见 [reviews/](../reviews/README.md)，不替代最终 R1～R31 验收

## 1. 环境与基线

| 项 | 值 |
|---|---|
| 主机 | Windows 10.0.26200（中文区域，控制台默认 GBK；判断文件编码须以字节为准） |
| 后端 | Python 3.12.10（`test-platform/.venv/Scripts/python.exe`）、FastAPI 0.109.0、SQLAlchemy 2.0.25 |
| 前端 | Node v24.15.0 / npm 11.6.4（`test-platform/frontend`，node_modules 已存在） |
| ADB | Android Debug Bridge 1.0.41（35.0.2-12147458） |
| 真机 | serial `5c000c2834414751c9d`，A133P / A133P / board exdroid / Android 10 / SDK 29 / armeabi-v7a / `ro.mc.cpu=A133P` |
| 回归基线 | 后端 189 passed（[baseline-session-start-20261112.log](baseline/baseline-session-start-20261112.log)） |
| 环境缺口 | 主机无 `docker` 命令；无 `mock-api` 工具。对应 T-17/R27、T-20 mock 已如实记录，未伪造 |

## 2. 最终验证结果

| 验证 | 命令 | 结果 | 原始日志 |
|---|---|---|---|
| 后端严格全量（Lead） | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA` | **310 passed / 0 failed，exit 0（135.09s）** | [FULL-REGRESSION-final-20261112.log](tasks/FULL-REGRESSION-final-20261112.log) |
| 后端严格全量（评审方独立重跑） | 同上 | 310 passed / 0 failed，exit 0（133.47s） | [reviews/evidence/test-rerun-20261112/](../reviews/evidence/test-rerun-20261112/) |
| 前端单测 | `npm test` | 33 用例通过（client 27 + datetime 3 + request 3） | tasks/T-20、T-21 |
| 前端 lint | `npm run lint` | exit 0，1037 warnings / 0 errors（既有告警，T-35 范围，无新增） | tasks/T-20 |
| 前端构建 | `npm run build` | exit 0（历史 legacy-js-api/chunk 告警不变） | tasks/T-20、T-21 |
| token 静态检查 | `npm run check:tokens` | 表外裸值 0、token 差异 0、18 组对比度达标 | tasks/T-21 |
| ADB runner 真机只读 | AdbRunner（T-19） | version / getprop abi=armeabi-v7a / echo ok 7/7 | tasks/T-19 |
| 启动矩阵 | uvicorn（T-18） | 8 类弱/占位/短密钥 exit=3 拒绝；合法密钥与 fresh 空库 /health=200 | tasks/T-18 |

## 3. 变更文件（按任务，均为工作区改动，尚未 git commit）

| 任务 | 生产代码 | 测试/脚本 |
|---|---|---|
| T-01 | `app/errors.py`(新)、`app/main.py`(异常处理部分)、`app/api/tasks.py`(目标路由别名) | `tests/integration/test_contract_errors.py`(新)；6 个集成测试旧 detail 断言等价更新 |
| T-06 | `app/services/judgement_engine.py`、`execution_engine.py`、`task_executor.py`(注释) | `tests/unit/test_execution_failure_closed.py`(新，45)；`test_judgement_engine.py`(2 处契约变更) |
| T-02 | `app/database.py`(FK/WAL/busy_timeout)、`alembic/env.py`、`app/seed_data.py`(created_by=None 修复) | `scripts/verify_migrations.py`(新)、`tests/unit/test_migration_contract.py`(新) |
| T-19 | `test-tools/common/adb_runner.py`、`common/device_info.py` | `tests/unit/test_adb_runner.py`(新，25) |
| T-17 | `Dockerfile`、`.dockerignore`、`app/services/tool_manifest.py`(新)、`app/main.py`(lifespan 校验) | `scripts/check_image_tools.py`(新)、`tests/unit/test_tool_manifest.py`(新，7) |
| T-18 | `app/config.py`、`app/main.py`(lifespan 校验)、`docker-compose.yml`、`backend/.env.example`、`DEPLOYMENT.md` | `tests/unit/test_secret_strength.py`(新，21) |
| T-20/T-21 | `frontend/src/api/client.js`(新)、`utils/request.js`、`styles/theme.scss`、`styles/index.scss`、`src/mocks/generated/*`、`package.json` | `scripts/generate-contract-mocks.mjs`、`scripts/check-tokens.mjs`、`src/utils/__tests__/client.test.js`(新，27) |

> 回退提示：`app/main.py` 同时承载 T-01（异常处理注册）与 T-17/T-18（lifespan 启动校验）的改动，回退时需按 hunk 处理，不能整文件回退。其余文件均按任务独立。逐任务回退说明见各 `tasks/T-xx/result.md`。

## 4. 独立评审结论（reviewer）

| 任务 | 结论 | 记录 |
|---|---|---|
| T-01 | 通过 | [RR-T01](../reviews/RR-T01-unified-errors.md) |
| T-02 | **不通过（DoD2/R20 回滚数据保留）** | [RR-T02](../reviews/RR-T02-migration-fk.md) |
| T-06 | 通过 | [RR-T06](../reviews/RR-T06-failure-closed-skip.md) |
| T-17 | 有条件通过 / Docker 运行时无法核验 | [RR-T17](../reviews/RR-T17-clean-image-tools.md) |
| T-18 | 通过 | [RR-T18](../reviews/RR-T18-weak-secret.md) |
| T-19 | 通过 | [RR-T19](../reviews/RR-T19-adb-runner.md) |
| T-20 | 有条件通过（mock-api 偏差 U1 待用户确认） | [RR-T20](../reviews/RR-T20-frontend-client-mock.md) |
| T-21 | 通过（静态 token 范围） | [RR-T21](../reviews/RR-T21-ui-tokens.md) |
| 整体 | **批次 G 验收不通过**（R20/R27 阻塞） | [RR-FINAL-batch-G](../reviews/RR-FINAL-batch-G.md) |

## 5. 兼容性与可靠性评审重点（按用户要求）

1. **真机仅一种形态**：唯一实机 A133P 为 Android 10 / SDK 29 / armeabi-v7a（zygote32，abilist 仅 armeabi-v7a,armeabi）。`ddr` 工具二进制只有 32 位（无 arm64-v8a）。**Android 9、10.1、arm64（如 rk3568）均无实机，兼容性无法核验**，不得据单一设备宣称多版本兼容。
2. **画像与实机偏差（U4）**：UPFM a133p 画像与实机不一致——触摸面板实为 techwin 10 点（无 ABS_MT_SLOT）vs 画像 32 点；`mc_props` 四项不符；`ro.product.board` 实测 exdroid（非 ceres）；画像注释 serial 指向另一台实体。处置：画像=固件期望、实机=回归基线双列，冲突项标 SKIP/待用户确认，**不得判 FAIL 作为交付证据**。
3. **可靠性回归（已修复闭环）**：T-02 打开 `PRAGMA foreign_keys=ON` 后，干净空库首次启动因 `seed_data.py` 虚构 `created_by=1` 触发 FK 失败（Docker 空数据卷会直接崩溃）。已修为 `created_by=None` 并新增 `test_clean_empty_db_startup_seeding_survives_foreign_keys_on`（独立单跑 1 passed，fresh 空库 /health=200）。
4. **迁移回滚风险（未通过）**：初始迁移 `downgrade base` 删表导致存量副本回滚 10/98→0/0，不满足设计§5「回滚恢复原结构且保留原数据」；**真实库严禁执行 `alembic downgrade base`**。备份恢复不能替代 alembic 回滚数据保留证据。
5. **ADB 可靠性**：T-19 全参数数组 `shell=False` 消除本地 shell 注入面；`shell(str)` 兼容签名保留、远端命令作为单参数交远端设备 shell；30+ 调用方零改动；真机只读 7/7。写操作（push/pull/root/fio/eMMC/APK）与超时未做端到端验证。
6. **环境限制**：主机无 Docker，T-17/R27 干净构建、容器启动、多架构二进制容器可用性均**无法核验**；无 mock-api，T-20 mock 由仓库确定性脚本生成并显式标注。
7. **编码澄清**：`theme.scss`/`index.scss` 等文件本身是合法 UTF-8 正确中文；PowerShell GBK 控制台会显示为乱码，属显示 artifact，不是文件缺陷（已用字节级证据结案，见 RR-000 P6）。

## 6. 待用户确认/决策项

| 编号 | 事项 | Lead 建议 |
|---|---|---|
| U1 | T-20 mock 来源（无 mock-api，改用仓库确定性脚本 + 显式标注） | 接受为临时口径；真实联调前须切真实 API 或补 mock-api 工具 |
| U4 | 画像期望与实机实测冲突口径 | 画像=固件期望、实机=回归基线双列，冲突判 SKIP/待确认，不判 FAIL |
| U-T06-1/2 | 状态机未定义处：fail_pattern 全局生效、pass_pattern 仅 assertion 正则层；仅 fail_pattern 未命中→error | 备案后可在后续版本细化；当前保守方向（不误 pass） |
| U-T01-1 | `details.reason` 使用 pydantic 英文模板（message 为中文） | 若验收要求 reason 中文化，后续统一 |
| U-T17-1 | 是否在具备 Docker 的环境补做 R27 干净构建/容器启动 | 建议补做，未补前 R27 不得判通过 |
| 门禁 | T-22～T-34 组件/页面契约与六段规格确认 | 仍需用户确认后才可实施 |

## 7. 最终结论

- 代码与测试层面：后端 310 passed / 0 failed（>189 基线，无删除/跳过/放宽），前端 test/lint/build/token 全绿，真机只读 7/7。
- 验收层面：**批次 G 整体验收不通过**——阻塞项为 **T-02/R20 回滚数据保留**与 **T-17/R27 干净镜像运行时无法核验**；T-20 为有条件通过（U1）。
- 本批次已完成的任务（T-01/T-06/T-18/T-19/T-21）可作为后续任务基础；T-02 保持进行中，T-17/T-20 保持有条件/进行中，均不得记为无条件完成。
