# RR-FINAL-batch-G：批次 G 整体评审记录

- 评审编号：RR-FINAL-batch-G
- 评审对象/任务编号：批次 G 全部交付（T-01/T-02/T-06/T-17/T-18/T-19/T-20/T-21）及前置依据文档/真机兼容性审计
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/plan/implementation-plan-v1.0.md`、`docs/plan/task-board-v1.0.md`、`docs/contracts/*` v1.0（2026-11-12 确认）、`docs/design/execution-state-machine.md`/`scheduler-and-data.md`/`ui-tokens.md` v1.0、`docs/verification/verification-rules-v1.0.md` v1.0、`docs/verification/stage1-handoff.md`
- 环境与 commit/变更集：Windows 10；Python 3.12.10（`D:\MCTEST\test-platform\.venv`）；Node v24.15.0/npm 11.6.4；adb 1.0.41；真机 serial `5c000c2834414751c9d`（A133P/Android10/SDK29/armeabi-v7a）；**主机无 docker、无 mock-api**；git HEAD `d0b415d` + 各任务未提交变更集
- 证据路径：各 RR 记录（`docs/verification/reviews/RR-*.md`）及其 `evidence/`；各任务 `docs/verification/tasks/T-XX/`；最终全量 `docs/verification/tasks/FULL-REGRESSION-final-20261112.log`

## 1. 各评审记录结论汇总

| 编号 | 对象 | 结论 | R/要点 | 记录 |
|---|---|---|---|---|
| RR-000 | 计划/契约/设计疑问项清单 | 有条件通过（异议项已裁决/结案） | P6 乱码为终端 GBK 显示 artifact 非文件缺陷 | RR-000-plan-questions.md |
| RR-ADB-001 | A133P 真机只读兼容性/可靠性审计 | 有条件通过（环境基线） | 画像 touch/mc_props 偏差、ddr 32 位、内存/负载风险 | RR-ADB-001-device-compatibility.md |
| RR-T01 | 统一错误外层与目标路由适配 | 通过（DoD 达成；503 待 T-13、500/501/reason 为遗留限制） | 错误码表一致、422→400、403→401 如实 | RR-T01-unified-errors.md |
| RR-T02 | Alembic 与外键迁移基础 | **不通过**（DoD2/R20 回滚数据保留）；task-3 reopen | R20 不通过；seed FK 启动回归已修复 | RR-T02-migration-fk.md |
| RR-T06 | 失败关闭与原生 SKIP | 通过（报告/WS 限代码+record 层） | 状态机行3-11 落地；2 旧单测为更严契约变更 | RR-T06-failure-closed-skip.md |
| RR-T17 | 干净镜像工具与启动清单 | **有条件通过 / Docker 运行时无法核验** | 静态 10/10+7 单测通过；docker 不可用，R27 未核验 | RR-T17-clean-image-tools.md |
| RR-T18 | 拒绝弱默认密钥 | 通过（host 启动矩阵） | 8 弱密钥 exit=3、合法/fresh /health=200；容器内 compose 展开未核验 | RR-T18-weak-secret.md |
| RR-T19 | 移除 ADB runner shell 拼接 | 通过 | shell=False 全参数化、真机只读 7/7、25 单测、30+ 调用方零改动 | RR-T19-adb-runner.md |
| RR-T20 | 前端契约客户端与 mock | 有条件通过/待用户最终确认 | P-T20-2/3 已修复；mock-api 偏差 U1 待确认 | RR-T20-frontend-client-mock.md |
| RR-T21 | UI token 映射 | 通过（静态 token 范围） | 逐值一致、无裸值、18 组对比度达标 | RR-T21-ui-tokens.md |

## 2. 独立重跑汇总

| 项 | 命令 | 结果 | 退出码 | 日志 |
|---|---|---|---:|---|
| 后端严格全量（评审方） | `pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA` | **310 passed / 0 failed**（133.47s） | 0 | `evidence/test-rerun-20261112/backend-final-full-regression-reviewer.log` |
| 后端严格全量（Lead） | 同上 | 310 passed（135.09s） | 0 | `docs/verification/tasks/FULL-REGRESSION-final-20261112.log` |
| 前端测试/构建/token | `npm test` / `npm run lint` / `npm run build` / `mock:generate` / `check:tokens` | 33 用例通过 / 1037w-0e / build exit0 / entries24 确定性 / token 差异0对比度18过 | 0 | `evidence/test-rerun-20261112/npm-*.log`、`check-tokens-direct.log` |
| T-19 真机只读 | `verify_device_readonly.py` | 7/7 PASS | 0 | `evidence/test-rerun-20261112/t19-device-readonly-reviewer.log` |
| T-02 seed 修复单测 | `test_clean_empty_db_startup_seeding_survives_foreign_keys_on` | 1 passed | 0 | `evidence/test-rerun-20261112/t02-seedfix-single-reviewer.log` |

后端基线：变更前 189 passed → 现 310 passed（新增覆盖充分，无删除/跳过/放宽）。

## 3. 兼容性与可靠性重点发现

| # | 发现 | 依据 | 影响/处置 |
|---|---|---|---|
| C1 | A133P 画像偏差：实机触摸为 techwin 10 点（TRACKING_ID max=9），画像期望 32 点 cyttsp5；mc_props 四项不符（custom_api_version "" vs "1"、product、version 2.1.0/3 vs 6.5.5/6） | RR-ADB-001；evidence/adb-a133p-20261112/14,05 | 按 U4 裁决：画像=固件特定期望、实机=回归基线双列；冲突标 SKIP/待确认，**不得判 FAIL 作为交付证据** |
| C2 | 32 位 ABI 局限：设备仅 armeabi-v7a（zygote32）；ddr 工具二进制仅 armeabi-v7a（无 arm64-v8a）；emmc 双架构齐备 | RR-ADB-001；evidence/04；test-tools/ddr/binaries | 换 arm64 板 rk3568 时 ddr 工具缺 64 位二进制；**兼容性仅覆盖 Android10/32 位一种形态，Android9/10.1/arm64 均无法核验** |
| C3 | 干净空库首次启动 FK 崩溃（T-02 引入，已修）：foreign_keys=ON 后 seed_data.py 虚构 created_by=1 → FK 失败 | RR-T02 P-T02-4；seed_data.py diff；T-18 矩阵 fresh-empty-db | 影响 Docker 空数据卷部署；已改 None + 回归测试 + fresh /health=200；**可靠性回归闭环** |
| C4 | 设备可靠性：MemFree≈51MB、待机 load 8.66、根分区 100%、蓝牙 OFF 未复验崩溃 | RR-ADB-001 P-A4/P-A5 | 实机压测易 OOM/波动；建议串行执行并记录内存快照；蓝牙开关崩溃仅历史观测未复验 |
| C5 | Docker 不可用：干净镜像构建/容器启动/多架构二进制容器可用性无法核验；compose `:?` 容器展开未核验 | RR-T17/RR-T18；主机无 docker | R27 无法核验；需有 docker 环境补做 |
| C6 | mock-api 缺失：T-20 mock 由仓库确定性脚本生成、非 mock-api | RR-T20 P-T20-1；主机无 mock-api | 偏差 U1，须用户确认后方可隔离开发，不得称替代 mock-api |
| C7 | 前端「乱码」为终端 GBK 误读 UTF-8 显示 artifact，非文件缺陷 | RR-000 P6；字节证据 | theme/index 均为合法 UTF-8 正确中文；建议统一 UTF-8 终端/日志 |

## 4. 待用户确认项（汇总）

| # | 事项 | 当前处置/建议 |
|---|---|---|
| U1 | T-20 mock 非 mock-api 生成 | Lead 已裁决接受仓库脚本+显式标注为临时替代；**待用户最终确认**后方可隔离开发，不得用于真实联调 |
| U4 | A133P 画像 vs 实机冲突口径 | Lead 已裁决双列、冲突标 SKIP/待确认不判 FAIL；**待用户确认画像固件版本适用性** |
| U-T06-1/2 | fail_pattern 全局/pass_pattern 仅 assertion、仅 fail_pattern 未命中→error 的判定语义备案 | 状态机未定义处保守实现，**待用户备案或修订状态机** |
| U-T01-1 | details.reason 英文（pydantic）是否需中文化 | 建议保留安全摘要英文、message 中文 |
| U-T17-1 | 是否需 docker 环境补做干净构建+启动以关闭 R27 | 建议补做，当前 R27 无法核验 |
| 门禁 | T-22～T-34 需用户确认新组件/页面四表契约与六段规格后才可实施 | 依 stage1-handoff H03 不放行，未确认前不得启动 |

## 5. 阻塞项与 R 状态（决定整体结论）

| 项 | 状态 | 说明 |
|---|---|---|
| T-02 / R20 回滚数据保留 | **不通过（阻塞）** | 初始迁移 downgrade base 删表 10/98→0/0；备份恢复不能替代 alembic 回滚证据；待 T-11 可逆迁移或用户修订 design§5 后重判；task-3 rev6 in_progress |
| T-17 / R27 干净镜像运行时 | **无法核验（阻塞）** | 主机无 docker；静态+host 等效通过，镜像构建/容器启动/多架构容器可用性未核验 |
| T-20 mock-api 偏差 U1 | 待用户确认（条件） | 有条件通过 |
| 实机兼容性覆盖 | 部分无法核验 | 仅 Android10/32 位一种形态 |

## 6. 最终结论

**批次 G 整体：验收不通过（不得签发通过）。** 已达成并获独立复核的部分：后端严格全量 310 passed / 0 failed（评审方独立 + Lead 最终日志一致）；前端 test/lint/build/token 全绿；T-01 错误外层与路由、T-06 失败关闭与原生 SKIP、T-18 弱密钥拒绝、T-19 ADB 参数化、T-21 token 映射通过；T-20 契约客户端核心通过（mock 偏差待确认）。

**阻塞项（导致整体不通过）：**
1. **T-02 / R20 回滚数据保留不通过**：downgrade base 删表丢数据，DoD 第2条未达成；task-3 已 reopen，待可逆 additive 迁移或 design§5 修订后重判。备份副本「从备份恢复」不能替代 alembic 回滚证据。
2. **T-17 / R27 干净镜像运行时无法核验**：主机无 docker，镜像构建/容器启动/容器内工具发现/多架构二进制容器可用性未验证；不得声称干净部署通过。

**说明性限制（不单独构成阻塞但影响验收范围）：** 实机仅覆盖 Android10/32 位；A133P 画像与实机 touch/mc_props 存在固件差异（按 U4 双列、冲突不判 FAIL 作为证据）；Docker/mock-api 不可用；T-06 报告/WS 仅代码+record 层；若干 R 项（如 R3 实机、R27）本轮无法核验。

**放行建议：** 在 ①T-02/R20 按补做路径闭环、②有 docker 环境补做 R27、③用户确认 U1/U4/U-T06 及 T-22～T-34 门禁后，方可重新组织最终验收。在此之前按验证规则 §9「任一不通过或无法核验，总体不通过」判定。

## 7. 签名

reviewer，2026-11-12；本记录汇总各 RR 独立评审结论，所有断言可追溯至 `docs/verification/reviews/` 与 `docs/verification/tasks/` 原始证据；未替开发修改任何代码，未对设备执行写操作，未执行 docker（本机不可用）。
