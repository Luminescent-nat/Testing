# 批次 G 开发证据索引（2026-11-12）

- 依据：[实施方案](../../plan/implementation-plan-v1.0.md)、[任务清单](../../plan/task-board-v1.0.md)、[验证规则](../verification-rules-v1.0.md)、[阶段1交接单](../stage1-handoff.md)
- 范围：T-01、T-02、T-06、T-17、T-18、T-19、T-20、T-21（批次 G 可并行项 + T-06 判定基础）
- 门禁：T-22～T-34 仍须用户确认组件/页面契约与规格后才可实施；本批次不涉及这些任务
- 基线：后端 `189 passed`（[baseline-session-start-20261112.log](../baseline/baseline-session-start-20261112.log)，2026-11-12 实测，102.66s）
- 环境：Windows 10.0.26200；Python 3.12（`test-platform/.venv/Scripts/python.exe`）；Node v24.15.0 / npm 11.6.4；ADB 1.0.41（35.0.2-12147458）
- 真机：`5c000c2834414751c9d`，A133P / A133P / ceres / Android 10 / SDK 29 / armeabi-v7a / `ro.mc.cpu=A133P`（[设备评审](../reviews/RR-ADB-001-device-compatibility.md)）
- 环境缺口（影响验收，不得写成通过）：本机无 `docker` 命令；无 `mock-api` 外部工具。相关任务按“实现 + 静态/隔离验证 + 无法核验”如实记录

## 目录约定

| 目录 | 内容 |
|---|---|
| `tasks/T-<n>/result.md` | 任务编号、变更集、环境、命令、起止时间、退出码、原始日志路径、DoD 逐条结论、未验证项、回退说明 |
| `tasks/T-<n>/*.log` | 原始命令 stdout/stderr（含失败日志，修复后追加而非覆盖） |
| `reviews/` | 统一评审记录（模板见 [reviews/README.md](../reviews/README.md)），疑问项、ADB 设备兼容性/可靠性审计、逐任务独立评审 |

## 状态表（Lead 集成回归后更新，2026-11-12）

| 任务 | 责任队友 | 实现 | 自测 | 独立评审 | 备注 |
|---|---|---|---|---|---|
| T-01 | backend-errors | 完成 | 完成 | 通过 | 统一错误外层 + 目标路由别名；RR-T01 |
| T-02 | infra-tools | 完成 | 完成 | **不通过** | R20 回滚数据保留未达成；seed FK 启动回归已修复；task-3 in_progress；RR-T02 |
| T-06 | execution-engine | 重开修复中 | - | 原“通过”已撤回 | V1-02 两条 fail-open 动态复现（[RR-V1-READINESS](../reviews/RR-V1-READINESS-20261112.md)）；修复与永久回归进行中 |
| T-17 | infra-tools | 完成 | 完成 | 有条件通过 | 无 docker，干净构建/启动无法核验；RR-T17 |
| T-18 | infra-tools | 完成 | 完成 | 通过 | 弱密钥拒绝启动矩阵通过；RR-T18 |
| T-19 | infra-tools | 完成 | 完成 | 通过 | 参数数组 + A133P 真机只读 7/7；RR-T19 |
| T-20 | frontend-contracts | 完成 | 完成 | 有条件通过 | mock-api 缺失偏差 U1 待用户确认；RR-T20 |
| T-21 | frontend-contracts | 完成 | 完成 | 通过（静态 token 范围） | 浏览器页面走查属 T-22+；RR-T21 |

## 最终集成

- 最终严格全量：`python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning` → **310 passed / 0 failed / exit 0（135.09s）**，原始日志 [FULL-REGRESSION-final-20261112.log](FULL-REGRESSION-final-20261112.log)；评审方独立重跑 310 passed（133.47s）一致。
- 前端：`npm test` 33 用例通过、`npm run lint` 0 error（既有 1037 warning 属 T-35）、`npm run build` exit 0。
- 批次 G 整体结论：**验收不通过**，阻塞项为 T-02/R20 回滚数据保留与 T-17/R27 干净镜像运行时无法核验；详见 [RR-FINAL-batch-G](../reviews/RR-FINAL-batch-G.md) 与 [集成汇总](../integration-summary-20261112.md)。

## 演示前收口轮（2026-11-13，V1.0-demo 本机演示版）

依据 [RR-V1-DEMO-20261113](../reviews/RR-V1-DEMO-20261113.md)：D-01 监控页 `item_name`、D-02 空报告 200 空态、D-03 报告 E2E 拆分、D-04 demo.db 隔离脚本、D-05 daily/once 禁用、AI-01 LLM 配置与规则规划标注全部修复；独立评审 [RR-DEMO-PREP-20261113](../reviews/RR-DEMO-PREP-20261113.md)。基线：后端严格全量 **472 passed ×2**（[STRICT-1](V11DEMO-FINAL-STRICT-1-20261113.log)/[STRICT-2](V11DEMO-FINAL-STRICT-2-20261113.log)）、前端 **75 用例 / lint 0e 988w / build 0**、Playwright 报告 spec **4 passed** 与全套 **15 passed/1 skipped**、start_demo 干净目录实测 001→004 且历史库 SHA 不变。汇总见 [v10-demo-readiness-summary-20261113](../v10-demo-readiness-summary-20261113.md)。

## 契约 v1.1 实施轮次（2026-11-13，已完成收口）

依据 [RR-V1-REFINAL-20261112](../reviews/RR-V1-REFINAL-20261112.md)（tool_manifest F1~F4 fail-open、AI 授权顺序/收口、全量不稳定）与已确认契约 v1.1（scheduler §6.1 A1~A5、task-execution §10），四路并行实施完成并经独立评审收口（[RR-V11-PLAN](../reviews/RR-V11-PLAN-20261113.md)、RR-V11-FIX-A/B/C、[RR-V11-FINAL-20261113](../reviews/RR-V11-FINAL-20261113.md)）：A1~A5 红绿落地、F1~F4 销项 9/9 CLOSED、B1/B2 计数=0 + B3 差分、cancel/export 两类竞态根治（20 连跑+并发验证）。门禁基线：**全量连续 2 轮 467 passed / 0 failed**（T-14/v1.1-pytest-full-r1/r2.log）+ Lead 独立验证轮 467 passed（[V11-FINAL-STRICT-LEAD-20261113.log](V11-FINAL-STRICT-LEAD-20261113.log)）+ 前端最终 `npm test` 65 用例/lint 992w-0e/build exit0。交付后独立复核发现 AI 创建响应形状前端未同步（P1），已由 task-28 修复并经 [RR-V11-REVIEW §4](../reviews/RR-V11-REVIEW-20261113.md) 闭环，本轮实施签收通过。明细见 [v11-implementation-summary-20261113](../v11-implementation-summary-20261113.md)。总体上线结论仍为"不通过/受控开发基线"。

## V1 readiness 修订轮次（2026-11-12，已完成收口）

依据 [RR-V1-READINESS](../reviews/RR-V1-READINESS-20261112.md) 与用户测试记录，第三轮修订已完成并由独立评审收口（[RR-V1-FINAL-20261112](../reviews/RR-V1-FINAL-20261112.md)、逐项 [RR-V1-FIX-*](../reviews/README.md)）：审计 6 项动态反例以 v2 永久基线 7/7 通过（R6 基线语义随 V1-08 契约更新，待用户确认）；后端严格全量 **448 passed / 0 failed**（[V1-FINAL-STRICT-3-20261112.log](V1-FINAL-STRICT-3-20261112.log)），前端 56 用例 / lint 0 error（994w，T-35 未清）/ build exit 0。修复明细、逐缺陷闭环与仍阻塞项（V1-05 真实库对账、V1-08/R27 Docker、V1-11 mock/lint/浏览器、V1-12 画像、V1-13 文档 26 errors、T-09/T-11～T-16/T-21～T-38 未实施）见 [v1-remediation-summary-20261112](../v1-remediation-summary-20261112.md)。
