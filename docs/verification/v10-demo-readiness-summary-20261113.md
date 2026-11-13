# V1.0-demo（本机演示版）收口汇总（2026-11-13）

- 依据：[RR-V1-DEMO-20261113](../reviews/RR-V1-DEMO-20261113.md)（本机演示版独立复核与收尾方案，D-01～D-05 / AI-01）与用户实测结果
- 范围：仅「本机可部署、可运行、可演示」；**不是完整 V1.0 生产上线验收**
- 方式：Agent Team 三路并行（task-29 前端、task-30 后端、task-31 部署/文档）+ 独立评审（[RR-DEMO-PREP-20261113](../reviews/RR-DEMO-PREP-20261113.md)）

## 1. 本轮修复（逐项）

| 项 | 问题 | 修复 | 验收 |
|---|---|---|---|
| D-01 | 监控页误用 `item.name`，契约/后端字段为 `item_name`；实测日志 `DDR / undefined` | [monitorRecord.js](../../test-platform/frontend/src/utils/monitorRecord.js) 归一（缺失→「未知测试项」）；monitor.vue 时间线/列表/详情/日志/WS 全路径统一；不依赖 legacy `name` | 9 条 Vitest；grep 无 `item.name` 残留；Playwright 页面无 undefined |
| D-02 | 全新库报告页 `GET /reports/summary/all` 404 → 控制台错误 | [reports.py](../../test-platform/backend/app/api/reports.py) 仅 summary/all 增加 `allow_empty=True`：200 空汇总（tasks/results/items 空、五类 counts 全 0、pass_rate=null、total=0）；batch/export 与单任务 404 语义保持 | +4 后端用例；空态浏览器 console 0 error |
| D-03 | Playwright 报告用例 `item_ids=[]`（契约必 400）失败后仍继续、选择器过期 | [task-workflow.spec.js](../../test-platform/frontend/tests/e2e/task-workflow.spec.js) 拆空态/非空态：非空态 API 取在线设备+合法 item、断言 201、轮询 completed、验证报告详情/统计/时间；无数据 skip 带原因；创建页断言 daily/once disabled | Playwright 单跑 4 passed；全套 15 passed / 1 skipped |
| D-04 | 默认历史库结构漂移，直接启动被 SchemaMismatchError 拒绝 | [start_demo.ps1 / .sh](../../test-platform/scripts/) + [DEMO.md](../DEMO.md)：历史库保留只读（SHA-256 前后一致 `2f919b05…1a789`），演示用独立 `demo.db` + `storage/demo`，空库 alembic 001→004；若必须保留历史数据另立迁移任务 | 干净目录实测 exit 0、`current=004 (head)`、schema_matches_models=true、/health healthy、历史库 SHA 不变 |
| D-05 | 页面暴露未实施的「每日定时/一次性」 | [create.vue](../../test-platform/frontend/src/views/tasks/create.vue) once/daily 均 disabled +「（后续版本）」标注，仅立即执行可选；T-11/T-12 未实施如实留痕 | E2E 断言 is-disabled；DEMO.md 记录 |
| AI-01 | `.env.example` 缺 LLM 配置；无密钥时口径 | 补 7 项（PROVIDER/API_KEY/BASE_URL/MODEL/TEMPERATURE/MAX_TOKENS/TIMEOUT），注明仅 OpenAI-compatible `/chat/completions`、无密钥=规则规划不得宣称 AI；DEPLOYMENT §6；AI 页按 `plan.llm_used` 显示「AI 规划」/「规则规划（未调用 AI）」 | 独立评审核对；Vitest 10 用例 |

## 2. 最终回归（收口基线）

| 项 | 结果 | 日志 |
|---|---|---|
| 后端严格全量连续 2 轮（Lead） | **472 passed / 0 failed ×2**（265.35s / 263.18s） | [STRICT-1](tasks/V11DEMO-FINAL-STRICT-1-20261113.log)、[STRICT-2](tasks/V11DEMO-FINAL-STRICT-2-20261113.log) |
| 前端 Vitest / lint / build | **75 用例通过**；lint 0 error / **988 warning（演示技术债，如实记录）**；build exit 0 | [T-35-demo](tasks/T-35-demo/) 三件套日志 |
| Playwright 报告 spec（全新空库） | **4 passed**（含报告空态 console 0 error、非空态 201→completed→统计） | [e2e-playwright.log](tasks/T-35-demo/e2e-playwright.log) |
| Playwright 全套 | **15 passed / 1 skipped**（空态因同库已有数据按设计 skip 带原因） | [e2e-playwright-full.log](tasks/T-35-demo/e2e-playwright-full.log) |
| 演示库脚本 | start_demo.ps1 -MigrateOnly 干净目录 exit 0，001→004，历史库 SHA 前后一致 | [T-27](tasks/T-27/) |
| 演示闭环（用户实测） | 全新隔离库启动、首管理员/登录/主要页面、A133P 只读 ADB：创建 201→cat /proc/meminfo→completed/passed→报告 100%→HTML 导出成功 | RR-V1-DEMO §2 证据 |

## 3. 演示标签与边界

- **已签：V1.0-demo / 本机演示版通过**（[RR-DEMO-PREP-20261113 §8.4](../reviews/RR-DEMO-PREP-20261113.md)）；演示使用 `demo.db` + `storage/demo`，历史库保留只读。988 warnings/0 errors 作为演示技术债如实记录、未清零；监控页无 undefined 为 grep+Vitest 级证明，HTML 导出沿用 22fd400 轮 exit 0 证据（本轮未改导出原语），如实不夸大。
- 不得宣称：完整 V1.0 生产上线、多用户高并发、完整调度（daily/T-11/T-12）、全 AI 能力、全设备矩阵、Docker/服务器部署已验收。
- 真实设备：仅 A133P 只读 ADB；未执行写入、烧录、重启、压测；原业务数据库未修改、SHA-256 前后一致。

## 4. 演示后/范围外维持项

R27 Docker 运行时；真实库漂移 A/B 对账（U-V1-05）；V1-11 前端最终门禁（988w 未清零、浏览器全页面/可访问性矩阵）；V1-12 画像/32 位 ABI；V1-13 文档 26 errors；U 项（U1 mock、U4 画像、U-D1 缺失键、V1-08 基线语义）；配置导入 R32~R59/D1~D9；未实施任务 T-09/T-11~T-16/T-36~T-38。
