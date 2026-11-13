# RR-DEMO-PREP-PLAN-20261113：演示前收口阶段一（问题清单核验 + 验收断言映射）

- 评审编号：RR-DEMO-PREP-PLAN-20261113
- 评审对象/任务编号：演示前收口（共享任务 task-32；实施 task-29/30/31）
- 评审日期：2026-11-13
- 评审人：reviewer（独立评审方）
- 依据：`docs/verification/reviews/RR-V1-DEMO-20261113.md`（用户实测 6 项演示前问题清单 D-01~D-05 + AI 配置口）、`verification-rules-v1.0.md`、`contracts v1.1`
- 环境与 commit/变更集：Windows 10；Python 3.12.10；**基线 HEAD `22fd400`**（`docs: 契约v1.1实施轮前端同步缺陷闭环评审…`）；工作区除评审方证据/记录外无业务改动（task-29/30/31 在途）
- 证据路径：本记录 §2 基线核验命令输出；`evidence/v11-demo-prep-20261113/`；问题清单源 `RR-V1-DEMO-20261113.md`

## 1. 演示前问题清单（6 项）与任务映射

| 编号 | 问题 | 严重 | 分派任务 | 记录来源 |
|---|---|---|---|---|
| D-01 | 任务监控页测试项名称字段错误：`monitor.vue` 用 `item.name`（契约/后端为 `item_name`）→ 名称 undefined、日志标题 `=== DDR / undefined ===` | P1 必修 | task-29（frontend） | RR-V1-DEMO §4 D-01 |
| D-02 | 全新空库报告页调用 `GET /reports/summary/all` 返回 404 → 浏览器 console 错误（空态可见但 404） | P1 必修 | task-30（backend-errors/stats） | RR-V1-DEMO §4 D-02 |
| D-03 | 报告 E2E 用例无效：`item_ids=[]`（契约必 400）却静默接受失败继续；空报告选择器等待不存在结构；不能作为验收证据 | P1 必修 | task-29（frontend E2E） | RR-V1-DEMO §4 D-03 |
| D-04 | 默认历史库 `backend/test_platform.db` 结构漂移，直接启动被 `SchemaMismatchError` 拒绝；须明确"新演示库 demo.db"或"历史库对账" | 演示启动策略 | task-31（infra） | RR-V1-DEMO §4 D-04 |
| D-05 | `tasks/create.vue` 暴露"每日定时(daily)"但 T-11/T-12 未实施 → 不得作为可用演示功能（隐藏/禁用并标注，或完成实施） | P1 收口 | task-29（frontend） | RR-V1-DEMO §4 D-05 |
| AI-01 | `.env.example` 未列 LLM 配置（`LLM_API_KEY/BASE_URL/MODEL/TIMEOUT/TEMPERATURE/MAX_TOKENS`）；AI 规划需标注"规则匹配/无 LLM 降级"，不得声称用了 AI | 配置口 | task-29（标注）+ task-31（文档） | RR-V1-DEMO §5.1 |

## 2. 基线核验（当前 HEAD 22fd400，缺陷真实存在）

| # | 基线事实 | 核验命令/证据 | 结论 |
|---|---|---|---|
| B1 | D-01：monitor.vue 使用 `item.name` | grep `item\.name`：monitor.vue:160/193/432/510（`item_name` 仅 283 一处用于 currentLog） | 缺陷存在 |
| B2 | D-02：`GET /reports/summary/all` 零任务抛 404 | reports.py:405 `HTTPException(404,"未找到可汇总的任务报告")`；端点 @1393 | 缺陷存在 |
| B3 | D-03：报告 E2E 用 `item_ids: []` + 宽松选择器 + catch 静默 | task-workflow.spec.js:55 `item_ids: []`、:66 `.reports-page, .report-list, .el-card`、:21/34/75 `catch(()=>false)` | 缺陷存在 |
| B4 | D-04：历史库无 alembic_version 且结构漂移；SHA 前后一致 | `backend/test_platform.db` SHA-256 = `2F919B0544E37618628AC358F1B5684EE16C9253596483B62919166A91B1A789`（与 RR-V1-DEMO §2 一致）；RR-V1-DEMO 隔离副本启动 `SchemaMismatchError`（原库未改） | 缺陷存在（历史库漂移） |
| B5 | D-05：create.vue 暴露 daily/once | create.vue:125-126 `<el-radio label="once">定时一次</el-radio>` / `<el-radio label="daily">每日定时</el-radio>` | 缺陷存在（daily 暴露） |
| B6 | AI-01：.env.example 无 LLM 项 | grep `LLM` 于 `backend/.env.example` → 0 命中 | 缺口存在 |
| B7 | task-31 demo 脚本尚不存在 | `*demo*` 仅 node_modules 噪声；无 `demo.db` 启动脚本 | 待实施 |
| B8 | 基线 HEAD 干净 | git log HEAD=22fd400；业务文件无改动（仅评审方未跟踪记录/证据） | 确认 |

## 3. 逐项验收断言（阶段二判定标准）

| 项 | 验收断言（须独立复核） |
|---|---|
| D-01 监控页 item_name | ①代码 grep：monitor.vue 及 WS/记录渲染使用 `item_name`，不再依赖 `item.name`（或 API 归一化层显式映射，WebSocket `current_item/completed_results` 与 REST 同口径）；②Vitest/组件测试含 `item_name` 断言且旧 `name` 不被当契约字段；③返回体/页面文本无 `undefined`（grep + 若可跑浏览器断言） |
| D-02 空报告汇总 200 | ①空库 `GET /reports/summary/all` → **200** 且 `tasks=[]/results=[]`、五类计数=0、`pass_rate=null`（number null）；②非空库行为不变（统计口径与 V1-06 一致）；③单任务 `GET /reports/{id}`（不存在）仍 404（不改既有语义）；④前端空态无 404 console |
| D-03 报告 E2E | ①拆两个用例：空报告态 + 有报告态；②有报告态用合法已完成真实 fixture，**不得 silent catch 创建失败**；③选择器用当前稳定结构/测试标识；④断言非空报告、时间、五类计数、详情（不只证明空页面能开）；⑤Playwright 全绿（若可运行） |
| D-04 demo 库策略 | ①新脚本在**干净临时目录**以 `demo.db` 启动：alembic 001→004、/health=200；②历史库 `backend/test_platform.db` **SHA-256 前后一致**（=B4 值）、未被改动；③启动脚本/文档一致指向 demo.db + 独立 storage/demo，避免误用历史库；④DEMO.md 内容与只读约束（不写真实库、不做设备写操作/APK/烧录/重启）如实 |
| D-05 daily 禁用 | ①`tasks/create.vue` daily 选项隐藏/禁用并标注"后续版本"（或完成 daily 实施——二选一，推荐前者）；②once 若纳入演示需到点触发+重启恢复验证，否则同样隐藏/标注；③无残留可提交 daily 的 UI 路径 |
| AI-01 配置与标注 | ①`.env.example` 补 LLM_API_KEY/BASE_URL/MODEL/TIMEOUT/TEMPERATURE/MAX_TOKENS 注释与示例（密钥留空）；②无 `LLM_API_KEY` 时规则规划不冒充 AI（页面/日志标注"规则匹配"）；③不夸大 OpenAI 兼容为任意供应商；④DEMO.md 记录启动步骤与降级口径 |

## 4. 通用门禁（阶段二）

- G1 各修复先红后绿（红测证据保留）。
- G2 后端严格全量连续 2 轮 0 failed（Lead 两轮日志为准，评审方可独立复跑）。
- G3 前端 `npm test` / `npm run lint` / `npm run build` 均 0 error（992 warning 作为演示版技术债如实记录）。
- G4 Playwright E2E 能跑则跑，空态/非空态两组报告用例通过、console 0 error/page error/5xx。
- G5 demo 脚本实测（干净目录 + 历史库 SHA 前后一致）。
- G6 契约文本未被本轮改动（`git diff docs/contracts` 重查）。
- G7 只读 ADB 全链路（若环境允许）：201→pass→completed/passed→报告→HTML 导出 保留/复跑。

## 5. 仍维持项（演示后 / 范围外，最终记录单列）

R27 Docker、真实库对账（历史库漂移 A/B）、V1-11 剩余（lint 992w 未清零 + 浏览器全页面走查）、V1-12 画像/32 位、V1-13 文档 26 errors、U 项（U1 mock、U-D1 缺失键策略、V1-08 基线语义）、配置导入 R32~R59 门禁、T-09 及 T-11~T-16/T-36~T-38 未实施任务。

## 6. 阶段一结论

**通过（计划放行）。** 6 项演示前问题与 AI 配置口在当前 HEAD `22fd400` 均基线确认存在（B1~B7），历史库 SHA 已锁定供前后一致核验。阶段二待 Lead 通知 task-29/30/31 完成后，按 §3 断言与 §4 门禁逐项独立复核，写 RR-DEMO-PREP-20261113.md 并更新 README。发现夸大/回归立即报 Lead。

## 7. 签名

reviewer，2026-11-13；本记录基于 HEAD 22fd400 基线 grep/哈希核验作出，未修改任何业务代码与契约。
