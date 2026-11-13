# RR-DEMO-PREP-20261113：演示前收口独立评审（task-29/30/31）

- 评审编号：RR-DEMO-PREP-20261113
- 评审对象/任务编号：演示前收口（task-32；实施 task-29/30/31）
- 评审日期：2026-11-13
- 评审人：reviewer（独立评审方）
- 依据：`RR-V1-DEMO-20261113.md`（问题清单 D-01~D-05 + AI 配置口）、`RR-DEMO-PREP-PLAN-20261113.md`（验收断言与门禁）、契约 v1.1、`verification-rules-v1.0.md`
- 环境与 commit/变更集：Windows 10；Python 3.12.10；Node v24.15.0；基线 HEAD `22fd400` + 本轮未提交变更（task-29/30/31）。证据：`evidence/v11-demo-prep-20261113/`；开发证据 `docs/verification/tasks/T-24/`（监控）、`T-25/`（空报告）、`T-27/`（demo 脚本+文档）、`T-35-demo/`（前端收口汇总）、`T-20/result.md` 第 12 节（AI 标注）

## 1. 逐项独立核验（A）

| 项 | 检查点 | 独立结果 | 结论 |
|---|---|---|---|
| D-01 监控页 item_name | 代码 grep 残留 `item.name`；`normalizeRecord` 归一；WS/REST 同口径 | monitor.vue:160/193 已改 `item.item_name`；:432 `normalizeRecord({item_name: res.data?.item_name || item.item_name})`；:504/:588 `normalizeRecords`；:591 `normalizeRecord(current_item)`；:510 `formatRecordTitle(item)`；**grep 无 item.name 读取残留**（唯一 `.name` 命中为 task 标题 :5）。`monitorRecord.js`：item_name 非空保留、缺失→「未知测试项」、module_name 回退 module.name、不读 legacy item.name、不改入参 | 通过 |
| D-02 空报告汇总 200 | 空库 summary/all 形状；非空不变；单任务/batch 404 保持 | reports.py：`_build_multi_task_report(..., allow_empty=False)`；仅 `get_summary_report` 传 `allow_empty=True`→`_empty_multi_task_report`（200）：report_version/type/id/created_at/task_count=0/executor/summary（total_items=0、passed/failed/skipped/error/timeout=0、counts 五类 0、pass_rate=**null**）/module_statistics={}/tasks=[]/results=[]/items=[]/total=0；batch/export 仍 allow_empty=False（404）；单任务不存在仍 404（既有 raise 未动）。新增 4 用例（空态×2+非空形状不变+单任务404+batch空集404） | 通过 |
| D-03 报告 E2E | spec 拆分/禁静默/断言真实统计/选择器 | task-workflow.spec.js 重写：空态用例（console/pageerror 捕获、`.report-card`/`.el-empty` 二选一、空态文案、无 error message、console 0 error、库中已有报告则 `test.skip` 带原因）；非空态用例（API 取在线设备+合法 item、缺数据 `test.skip` 带原因、`POST /tasks` **断言 201** 且禁止静默、轮询 completed、进详情断言统计/通过率）；创建页用例追加 daily/once `is-disabled` 断言；选择器 `.report-card/.report-detail` 对齐当前 DOM。Playwright `--list` exit 0（4 tests） | 通过（代码层；**实跑待 Lead 日志**，见 §3） |
| D-04 demo 库策略 | 干净目录 demo.db 启动链；历史库 SHA 前后一致；文档/只读约束 | **评审方独立实测**：`start_demo.ps1 -MigrateOnly -DemoDbPath <temp>\demo.db -StorageRoot <temp>\storage\demo` → exit 0，alembic `004_task_deleted_at (head)`；**历史库 SHA 前后一致**（`2F919B05…1A789`，HIST_SHA_UNCHANGED=True）；开发证据另有：结构指纹 `schema_matches_models=true`、uvicorn 冒烟 `/health=healthy`（`T-27/demo-server-smoke`）；DEMO.md §1 明确历史库只读/漂移属预期/严禁 downgrade base/独立 demo.db+storage/demo、§5 SHA 约束与实测、§3 只读演示清单（201→cat /proc/meminfo→completed/passed→报告 100%→HTML 导出）、§6 明确不做写入/烧录/重启/压测 | 通过 |
| D-05 daily/once 禁用 | 选项 disabled+标注；无可提交路径 | create.vue:126-135 `once`/`daily` 均 `disabled` 且文案「（后续版本）」；`canStart`/提交逻辑未改；E2E 创建页用例断言两者 `is-disabled`、立即执行非 disabled | 通过 |
| AI-01 配置与标注 | .env 七项；无密钥不冒充 AI；DEMO/DEPLOYMENT 同步 | `.env.example` 新增 LLM 块 7 项（PROVIDER/API_KEY 空/BASE_URL/MODEL/TEMPERATURE/MAX_TOKENS/TIMEOUT）+「仅 OpenAI-compatible；无密钥=规则规划，不得宣称调用 AI」注释；DEPLOYMENT §6/§7 同步；aiTask.js `buildPlanPreview` 增 `llmUsed = plan.llm_used === true`，AI 页标签 true→「AI 规划」、false/缺失→「规则规划（未调用 AI）」；DEMO.md 记录口径 | 通过 |
| 契约/范围 | 契约未被改；未越界 | `git diff HEAD -- docs/contracts` = 空；变更限于 frontend（monitor/create/ai-test/utils/tests/e2e）+ backend reports.py+测试 + scripts/DEMO/.env.example/DEPLOYMENT | 通过 |

## 2. 独立重跑记录（B）

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| 后端严格全量（评审方 1 轮）`pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning` | **472 passed / 0 failed**（266.16s） | 0 | `evidence/v11-demo-prep-20261113/backend-full-reviewer.log` |
| 前端 `npm test` | **7 文件 / 75 用例通过** | 0 | `frontend-npm-test-reviewer.log` |
| 前端 `npm run lint` | **988 warnings / 0 errors**（较上轮 992 −4，无新增） | 0 | `frontend-npm-lint-reviewer.log` |
| 前端 `npm run build` | 构建成功（历史 Sass/chunk 告警不变） | 0 | `frontend-npm-build-reviewer.log` |
| demo 脚本干净目录实测（评审方） | exit 0；alembic 004 head；**HIST_SHA_UNCHANGED=True** | 0 | `demo-script-migrateonly-reviewer.log` |
| 开发证据对照：T-27 demo 日志 | 001→004 全链 + schema_matches_models=true + /health healthy | 0 | `docs/verification/tasks/T-27/demo-init-20261113.log`、`demo-server-smoke-20261113.log` |

## 3. Playwright（C）状态

- **代码层**：spec 重写符合 D-03 要求（拆空/非空、禁静默 201 断言、真实统计断言、skip 带原因、选择器对齐）；`npx playwright test --list` exit 0（4 tests）。
- **实跑**：评审方环境无隔离服务（`global-setup.mjs:12` 要求 `E2E_DATABASE_URL`，`e2e-blocked-prereq.log` 记录前置缺失 exit 1）→ **评审方无法独立实跑**；Lead 将起隔离服务（E2E_DATABASE_URL+后端+前端）运行 `task-workflow.spec.js` 并提供日志，届时据日志复核（空态 console 0 error、非空态 201→completed→统计正确、skip 原因合理）。
- **观察项（低风险，供 E2E 复核时留意）**：`auth.setup.spec.js` 仍用 legacy `/auth/login`、`/auth/register` 且断言 register 200（T-35-demo §5 已如实记录）；若实跑在此 setup 失败，属测试夹具遗留而非产品缺陷，应另行同步（建议后续任务修复，不阻塞本轮演示收口）。

## 4. 问题与观察（如实记录，均低风险）

| # | 观察 | 依据 | 影响 | 等级 |
|---|---|---|---|---|
| O-1 | start_demo.ps1 显示路径拼接瑕疵：打印如 `backend/C:\Users\...\demo.db`（`$Backend/$DemoDbPath` 直拼绝对路径）；实际 DATABASE_URL 使用绝对路径功能正常 | 评审方实测输出 | 仅显示文案误导，不影响运行；建议后续改为相对 backend 展示 | 低 |
| O-2 | E2E 实跑依赖 Lead 隔离服务 | §3 | 当前 E2E 结论为"代码层通过、实跑待复核" | — |
| O-3 | 前端 E2E auth.setup legacy register 200 断言 | T-35-demo §5 | 若后端 register 改 201 需同步（当前未改，不影响） | 低 |
| O-4 | 空态响应额外附加 `items/total` 兼容字段（仅空态） | T-25 §6 | 前端可统一消费 tasks/summary 后移除；记录待确认 | 低 |

## 5. 仍维持项（演示后 / 范围外，单列）

1. R27 Docker 干净镜像运行时（无 docker，UNVERIFIABLE）。
2. 真实库漂移 A/B 对账（历史库 SHA 锁定、严禁 downgrade base）。
3. V1-11 前端最终门禁：lint **988 warnings** 未清零（演示版技术债，如实记录）+ 浏览器全页面走查（本轮仅 E2E 覆盖报告/创建页）。
4. V1-12 A133P 画像/32 位局限（U4 口径）。
5. V1-13 文档 26 errors（T-37）。
6. U 项：U1 mock 临时机制、U-D1 缺失 Idempotency-Key 策略、V1-08 基线语义确认。
7. 配置导入 R32~R59 需求门禁（未确认，未实施）。
8. 未实施任务：T-09 及 T-11~T-16、T-36~T-38 等。

## 6. 最终结论（初次收口；**最终结论以 §8 为准**）

**有条件通过（D-01/D-02/D-04/D-05/AI-01 通过；D-03 代码层通过、Playwright 实跑待 Lead 日志复核）。**

- 6 项演示前问题与 AI 配置口全部完成修复并经独立核验：D-01 监控页 `item_name` 归一（无 item.name 残留、无 undefined 路径）；D-02 空库 `summary/all` → **200 空汇总**（五类 counts 0、pass_rate=null、items/tasks/results 空、total=0；非空形状不变、batch/export 与单任务 404 保持）；D-03 E2E 拆空/非空两用例、禁静默接受创建失败、真实 201/completed/统计断言、skip 带原因；D-04 demo 脚本干净目录 **001→004 head** 且历史库 SHA 前后一致、DEMO.md 只读约束如实；D-05 daily/once disabled+「后续版本」标注；AI-01 `.env.example` 七项 LLM + 无密钥规则规划不冒充 AI + 规划方式标签。
- 独立重跑：后端 **472 passed / 0 failed**；前端 **75 用例 / 988w-0e / build exit 0**；demo 脚本 exit 0 + 历史库 SHA 不变。
- **剩余关闭条件（唯一）**：Playwright `task-workflow.spec.js` 实跑日志（Lead 起隔离服务后提供）——空态 console 0 error、非空态 201→completed→统计正确；复核通过即转正式通过。若实跑暴露产品缺陷（非 fixture 遗留），按不通过处理并回报。
- 本结论仅覆盖"本机演示版（V1.0-demo）收口"，不构成完整 V1.0 生产上线验收（§5 维持项不变）。

## 7. 签名

reviewer，2026-11-13；本记录基于独立 grep/diff、独立全量/三件套/demo 脚本实测与开发证据核对作出，未替开发修改任何代码，未改真实库/设备/契约。

## 8. E2E 与最终回归复核（收口，2026-11-13 14:4x）——最终结论

### 8.1 Lead 隔离环境日志复核

| # | 证据 | 复核结果 |
|---|---|---|
| 1 | `T-35-demo/e2e-env.txt`：`E2E_DIR=...\e2e-demo-77291f22`、`...\e2e.db` 一次性临时库；`e2e-backend.log`（uvicorn Started/Waiting startup）、`e2e-frontend.log`；管理员由 `backend/scripts/ensure_e2e_admin.py` 预建 | 隔离库/前后端服务前置成立；**未用平台默认库**；历史库 SHA 前后一致另由评审方 demo 脚本实测（§2） |
| 2 | `T-35-demo/e2e-playwright.log`：`npx playwright test tests/e2e/task-workflow.spec.js`（全新空库单跑） | **4 passed**：setup（管理员登录）+ 创建页（含 daily/once disabled 断言）+ **报告空态（console 0 error、`.el-empty` 「暂无报告」）** + 非空报告（**201→轮询 completed→详情统计/通过率**） |
| 3 | `T-35-demo/e2e-playwright-full.log`：`npx playwright test`（完整） | **15 passed / 1 skipped**；skip 为「报告空态」因同一库已有数据按设计 `test.skip` 带原因（非静默、非失败，且该用例已在第 2 项全新库单跑通过）；其余导航/交互/创建/非空报告全绿，日志无失败/5xx；auth.setup 的 legacy register 200 断言在本次真实后端 200 下通过（O-3 遗留风险未触发） |
| 4 | `docs/verification/tasks/V11DEMO-FINAL-STRICT-1-20261113.log` / `STRICT-2-20261113.log` | **472 passed / 0 failed ×2**（265.35s / 263.18s），与评审方独立一轮（§2，472 passed）合计 3 轮 0 failed |
| 5 | 只读 ADB 全链路（门禁项 7） | 沿用 `evidence/v11-demo-review-20261113/readonly-adb-task-smoke.log`：201→pass→completed/passed→报告 pass_rate=100.0→HTML 导出 4869 字节，exit 0；本轮未改导出原语（task-26 原子写保持），且 E2E 非空报告真实创建→completed→报告统计复跑主链 |

### 8.2 D-03 判定更新

**D-03 = 通过（实跑 Playwright 达成）。** 报告 spec 已拆空态/非空态并经全新空库独立单跑 4 passed：空态 console 0 error/page error；非空态严格断言创建 201、轮询 completed、报告详情统计与通过率；无数据 skip 带原因；选择器对齐当前 DOM；完整套件 15 passed / 1 skipped（设计性 skip 且已单跑覆盖）。§6 的"有条件"唯一剩余条件已关闭。

### 8.3 RR-V1-DEMO §6「V1.0-demo 最终门禁」逐条对照

| 门禁 | 状态 | 依据 |
|---|---|---|
| D-01/D-02/D-03 修复+边界/异常测试 | ✅ | §1（item_name 归一+9 Vitest；200 空汇总+4 用例；E2E 空/非空两用例实跑） |
| D-04 明确新演示库+脚本文档一致 | ✅ | §1/§2（demo.db 001→004、历史库 SHA 不变、DEMO.md） |
| daily 禁用/隐藏不展示可用 | ✅ | create.vue disabled+「后续版本」；E2E 创建页 `is-disabled` 断言通过 |
| .env.example/DEMO 补 AI 配置+无密钥降级+启动步骤 | ✅ | 七项 LLM、规则规划口径、DEMO.md §2/§5 |
| 严格全量连续 2 轮 0 failed；前端三件套 0 error | ✅ | 472×2（Lead）+ 472×1（评审方）；75 用例 / 988w-0e / build exit0 |
| Playwright 全绿；空/非空无 console/page error/5xx；监控页无 undefined | ✅ | 单跑 4 passed（空态 console 0 error）+ 完整 15 passed/1 design skip；监控页无 undefined 由代码 grep + `monitorRecord.js` 与 9 项 Vitest 证明（**如实说明：E2E 未新增监控页专属断言**，浏览器级名称展示未单独复跑，属演示版可接受边界） |
| 只读 ADB 全链路保留/复跑 | ✅ | §8.1 #5（保留原证据 + 本轮 E2E 复跑创建→completed→报告统计；HTML 导出沿用未改动的导出原语证据） |
| 标签明确 V1.0-demo / 本机演示版，不含生产/高并发/全调度/全 AI/全设备矩阵承诺 | ✅ | DEMO.md 标题与 §1/§4/§5 边界；本记录 §5 维持项单列 |

### 8.4 最终结论（覆盖 §6 初次收口）

**V1.0-demo 本机演示版通过。** 演示前收口的 6 项问题（D-01~D-05 + AI-01）全部修复并经独立复核；后端严格全量连续 2 轮（Lead 472×2，评审方另 1 轮 472）0 failed、前端 75 用例/988w-0e/build exit 0、Playwright 报告 spec 全新空库 4 passed 与完整套件 15 passed/1 设计性 skip、空态 console 0 error、非空报告 201→completed→统计校验真实通过；demo 脚本干净目录 001→004 head 且历史库 SHA 前后一致；RR-V1-DEMO §6 门禁逐条达成。

**边界声明（必须随结论引用）**：
- **988 warnings / 0 errors 作为演示版技术债如实记录**，未清零；本结论**不等于完整 V1.0 生产上线通过**（R27/真实库对账/V1-11 剩余门禁/V1-12/13/U 项/配置导入/T-09 等见 §5 维持项，全部单列不并入）。
- 监控页无 `undefined` 为代码 grep + Vitest 级证明，E2E 未新增该页专属浏览器断言；只读 ADB 全链路 HTML 导出沿用 22fd400 轮 exit 0 证据（本轮未改导出原语）——如实记录，不夸大。
- 演示标签仅限 **V1.0-demo / 本机演示版**：不含生产部署、多用户高并发、完整 daily/once 调度、全 AI 能力、全设备矩阵承诺。

## 9. 最终签名

reviewer，2026-11-13；§8 复核基于 Lead 隔离环境/E2E/严格全量原始日志与评审方独立重跑，未替开发修改任何代码，未改真实库/设备/契约。
