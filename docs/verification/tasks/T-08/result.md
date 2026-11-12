# T-08 / V1-06 统一统计、进度与 result 口径 —— 结果记录

- 任务：task-16（V1-06 统一统计/进度/result 口径，对应 T-08）
- 负责人：stats-unify
- 日期：2026-11-12
- 依据：`docs/verification/reviews/RR-V1-READINESS-20261112.md` V1-06；
  `docs/design/execution-state-machine.md` §3/§5/§6；
  `docs/verification/verification-rules-v1.0.md` §4；
  `docs/contracts/reporting-v1.0.md`、`docs/contracts/device-authorization-v1.0.md` §2

## 1. 结论

V1-06 静态复核缺陷已修复并补端到端动态真值表：新增单一聚合模块
`app/services/statistics.py`，任务详情/列表、WebSocket、Dashboard、报告/导出全部
复用同一口径；skip 不进通过率分母、零有效分母统一返回 JSON `number null`；任务
`result` 严格看 `status`（仅 completed 且 C=N、R=0、P=0 才可 passed/failed）；
running 不计完成、pending 不计完成。新增 `tests/integration/test_v1_statistics.py`
共 9 个用例覆盖 STAT-01/02/03、DASH-01、ZERO-01 及 skip+pass、零记录、pending、
cancelled、平台 failed 真值表，并核对详情 / WS / 报告三处一致。

定向验证：`9 passed`（退出码 0）；受影响的既有消费者套件 `81 passed`（退出码 0）；
剔除在途他人任务导致的无关失败后全量 `416 passed, 2 deselected`（退出码 0）。

## 2. 改动清单（仅本任务授权范围）

| 文件 | 改动 |
|---|---|
| `app/services/statistics.py`（新增） | 唯一统计口径模块：`count_statuses` / `compute_pass_rate` / `compute_task_statistics` / `summarize_records` / `aggregate_counts` / `classify_task_for_dashboard` / `build_dashboard_breakdown` |
| `app/schemas.py` | `TestTaskResponse` 新增 `total_items` / `completed_items` / `counts`（五类）/ `pass_rate`（number\|null）；`compute_result` 改为 `compute_aggregates`，全部经 statistics 聚合且严格看 status，不再仅凭已有记录推 passed/failed；`DeviceResponse` 新增契约字段 `version: int`（device-authorization §2，从 1 开始） |
| `app/websocket.py` | `build_progress_message` 改用 statistics：running/pending 均不计入 `completed_items`；消息新增 `counts` / `pass_rate` / `result` / `pending_items`；任务未完成 `result=null` |
| `app/api/reports.py` | 单任务/批量报告 summary 改用 `statistics`；`pass_rate` 改为 number\|null（skip 不进分母、零分母 null，替换旧字符串 `0%`）；趋势、按模块统计统一公式并新增分列（no_result/execution_failed/cancelled）；新增渲染格式化 `_format_pass_rate` / `_fmt_metric` / `_fmt_pct` 修复 0 被显示为 `-`（R22/ZERO-01）；报告新增 `task_status`/`task_result` 与 summary `counts`/`timeout` 供一致核对 |
| `app/api/dashboard.py` | 任务通过率仅统计 `completed` 且 result∈(passed,failed) 的任务；全 skip/零记录(no_result)、平台 failed、cancelled、running、pending 分别计数（`task_outcomes`）且不进分母；分母 0 → null；今日任务聚合按 task.status+result 计算 |
| `tests/integration/test_v1_statistics.py`（新增） | 9 个集成用例（见 §4） |

未改动：`app/api/tasks.py`（task-12 在改，禁止）、models / alembic / database、
judgement/execution/task_executor、test-tools、frontend、docs/plan。

## 3. 关键口径实现（对照状态机 §3/§5/§6）

- `completed_items` = C = 五类终态记录数；running/pending 不计。
- `progress_percent = floor(C/N*100)`（N>0）；N=0 → 0；不伪造 100。
- 通过率 = `pass/(pass+fail+error+timeout)*100`，skip 排除；分母 0 → `None`。
- 任务 `result`：仅 `status=completed` 且 `C=N`、无 running、无 pending 时判定：
  任一 fail/error/timeout → failed；否则有 pass → passed；否则（全 skip/零记录）→ null。
  pending/running/cancelled/平台 failed 一律 null。
- Dashboard 任务通过率：仅 completed+result∈(passed,failed) 进入分母；其余分列。

## 4. 测试覆盖（tests/integration/test_v1_statistics.py，9 passed）

| 用例 | 场景 | 关键断言 |
|---|---|---|
| `test_stat01_pass2_fail1_timeout1_skip2_consistent` | STAT-01：pass2/fail1/timeout1/skip2 | 详情/WS/报告一致：C=6、progress=100、pass_rate=50.0、counts 五类；详情 result=failed；报告 summary passed2/failed2/skipped2/timeout1、task_result=failed |
| `test_stat02_all_skip_result_and_pass_rate_null` | STAT-02：全 skip | completed 但 result=null、pass_rate=null（断言 `is None` 且 `!= "0%"`）、C=3、progress=100 |
| `test_stat03_running_not_counted_task_not_completed` | STAT-03：3 pass + 1 running | completed_items=3（running 不计）、total=4、progress=75、status=running≠completed、result=null、WS 一致 |
| `test_truth_table_skip_pass_zero_pending_cancelled_platform_failed` | skip+pass / 零记录 / pending / cancelled / 平台 failed | skip+pass→passed(pass_rate100)；零记录→null/0/null；pending→null；cancelled（含 pass 记录）→null；平台 failed（error 记录）→null |
| `test_dash01_mixed_outcomes_only_valid_completed_in_rate` | DASH-01 混合 7 任务 | today.passed=1/failed=1/pass_rate=50.0；task_outcomes passed1/failed1/no_result2/execution_failed1/cancelled1/running1/pending0；分列和=总数 |
| `test_dash01_zero_records_pass_rate_null` | DASH-01 零任务 | 分母 0 → pass_rate=null |
| `test_zero01_zero_values_item_id_alignment_and_missing_metric` | ZERO-01：耗时0/值0/无对应项/重名不同ID | 重名不同 item_id 不合并；execution_time=0 保留；bw_mbps=0/iops=0 保留；缺失 max_iops 渲染 `-`；markdown 性能表 0 显示 0 不显示 `-`；Excel 可生成 |
| `test_device_response_includes_version` | 契约补充：Device.version | GET /devices 返回 `version=1` |
| `test_statistics_module_single_source_of_truth` | 聚合函数直接单测 | C/progress/pass_rate/result 及各非 completed 状态 result=null；分母 0→None；skip 不进分母 |

## 5. 原始日志与退出码

| 命令 | 结果 | 日志 |
|---|---|---|
| `pytest tests/integration/test_v1_statistics.py -q -W error::pytest.PytestUnraisableExceptionWarning` | **9 passed，退出码 0** | `pytest-v1-statistics.log` |
| `pytest <受影响消费者：reports_api, reports_stats_api, websocket, security_hardening, tasks_api, task_executor, report_generation, v1_judgement_stop> -q ...` | **81 passed，退出码 0** | `pytest-consumers.log` |
| `pytest tests -q -W error::... --ignore=tests/unit/test_v1_migration.py --deselect=tests/integration/test_devices_api.py::test_refresh_devices --deselect=tests/e2e/test_full_workflow.py::test_full_workflow` | **416 passed, 2 deselected，退出码 0** | `pytest-full-clean.log` |
| `pytest tests -q -W error::... --ignore=tests/unit/test_v1_migration.py` | 416 passed, **2 failed**（均为并在途 device.py 无关失败，见 §6），退出码 1 | `pytest-full-ignore-migration.log` |
| `pytest tests -q -W error::...`（严格全量） | 404 passed, **8 failed**（全部为 `tests/unit/test_v1_migration.py`，在途 task-11/task-19 迁移/Device.version），退出码 1 | `pytest-full.log` |

## 6. 与统计无关的并在途失败（不属本任务，Lead 严格全量前需待其收口）

执行严格全量时存在以下失败，均**不由本任务改动引起**，本任务相关代码路径全部通过：

1. `tests/unit/test_v1_migration.py`（8 failed）：`SchemaMismatchError ... devices 缺少列: version`
   —— 因并在途 `task-19`（Device.version 列 + `003_device_version` 迁移）与
   `task-11` 迁移测试期望仍在收敛，`app/models`、`app/database.py`、`alembic/versions`
   由他人改动。本任务未改 models/alembic/database。
2. `tests/integration/test_devices_api.py::test_refresh_devices` 与
   `tests/e2e/test_full_workflow.py::test_full_workflow`：`device.py` 现有实现调用
   `self.adb.get_device_list()`，而 `conftest.mock_adb` 仍只 mock `get_devices`，
   属并在途 `device.py` 设备改派改造未同步 mock，与本任务无关（本任务未改 device.py/conftest）。

上述项已用 `--ignore` / `--deselect` 隔离后得到全绿 416 passed 证据；**最终以 Lead 在
task-11/task-19 收口后的严格全量为准**。

## 7. 偏差与遗留（如实说明）

1. **Dashboard 响应形状偏差**：契约 `reporting-v1.0 §5` 要求 `data.today` 直接含
   `completed/no_result/execution_failed/cancelled` 等键；但既有
   `tests/integration/test_security_hardening.py::test_dashboard_stats_response_shape`
   断言 `set(data.today.keys()) == {tasks, passed, failed, pass_rate}`，而该测试文件
   当前属并在途 `task-12` 写入范围（不得并发修改）。为避免破坏既有测试与跨任务冲突，
   本任务保持 `today` 原有 4 键，并把 `completed/no_result/execution_failed/cancelled/
   running/pending` 的完整分列放在顶层 `data.task_outcomes`（语义等价、可核对）。
   建议 task-12 收口后由后续任务把 `task_outcomes` 字段并入 `data.today` 以严格对齐
   reporting §5，并同步更新该形状断言（更严不放宽）。
2. **Legacy 报告 summary 兼容字段**：为不破坏前端 `views/reports/index.vue` 对
   `summary.passed/failed/skipped/error` 的读取，保留旧键，其中 `failed` 历史口径仍
   为 fail+timeout；但 `pass_rate` 已严格按五类分母（skip 排除、零分母 null），并额外
   暴露 `timeout` 与 `counts` 五类计数。完整报告 v2.0 字段（`pass/fail/skip/error/
   timeout` 改名、`task_status/task_result/execution_context/coverage`）属 reporting
   契约迁移，超出 V1-06 范围，未在本任务强制切换。
3. **前端通过率展示未改**：`views/reports/index.vue` 仍以 `passed/total_items` 自行
   计算展示通过率（把 skip 计入分母）；V1-06 后端口径已统一，前端展示整改属前端任务
   范围（本任务禁止改 frontend）。
4. **ZERO-01「无对应项标不可对比」**：后端无跨报告对比实现；本任务保证报告 `results`
   按稳定 `item_id` 不合并、耗时 0 / 提取值 0 原样保留、缺失指标渲染 `-`（不伪造 0）。
   跨报告对比的「无对应项→不可对比」文案属前端对比视图（`docs/design/pages/reports.md`），
   未在 backend 落地，如实记录。
5. **DeviceResponse.version**：应 Lead 追加要求在同文件 `schemas.py` 增加 `version: int`；
   依赖并在途 `task-19` 的 `Device.version` 列与 `003` 迁移（本任务未改 models/alembic）。

## 8. 未执行事项声明

- 未 `git commit`（由 Lead 统一提交）；未改 `docs/plan`；未改其它任务文件。
- 未运行前端测试/lint/build（本任务范围仅后端统计口径）。

## 9. 前端章节（task-21，V1-06 前端显示收口，2026-11-12）

### 9.1 任务与结论
按 `RR-V1-READINESS-20261112.md` V1-06 收口前端展示：报告页与仪表盘不再自行用
passed/total（skip 计入分母）计算通过率，全部改用后端 `pass_rate`（number|null）与
五类计数；null 统一显示“无有效结果”；报告对比按稳定 `item_id` 对齐；耗时/数值 0
保真不显示缺失。保持 `isSuccessResponse`（2xx）成功判定与既有授权/加载逻辑，
未改业务分支与跳转。

### 9.2 改动文件
| 文件 | 改动 |
|---|---|
| `src/utils/stats.js`（新增） | 纯函数：`countStatuses` / `toPassRate` / `formatPassRate`（null→“无有效结果”，0→“0%”）/ `formatDurationSeconds`（0→“0秒”，null→“—”）/ `normalizeSummary`（优先 counts，其次契约字段，兼容旧键）/ `deriveTaskSummary`（严格取后端 task.pass_rate）/ `normalizeDashboardOutcomes`（task_outcomes 分列，明确不用 completed 充当 passed）/ `buildCompareRows`（按 item_id 对齐） |
| `src/views/reports/index.vue` | 卡片/详情通过率与状态标签改用后端 `summary.pass_rate`；统计数字改用五类 `counts`（新增超时）；卡片耗时走 `reportDuration`（0 保真）；结果表耗时 `formatDurationSeconds`、原因字段优先契约 `reason`；对比表新增“项 ID”列，按 `item_id` 对齐，仅一方存在标“不可对比”，耗时 0 显示 0秒；移除本地 `getPassRate`/`buildCompareRows` 自算实现 |
| `src/views/dashboard/index.vue` | 统计卡按后端 `today` + `task_outcomes` 分列展示（在线设备/今日任务/通过(业务)/业务失败/无有效结果/执行失败/已取消/通过率）；通过率 null → “无有效结果”；模块通过率 tooltip 与柱状图使用后端 `pass_rate`（null 不画 0）及五类计数；`fetchStats` 经 `normalizeDashboardOutcomes`，不把 completed 当 passed |
| `src/utils/__tests__/v1-06-stats.test.js`（新增） | 13 个纯函数用例：null/0 通过率格式化、耗时 0 保真、五类计数、summary 归一化（counts 优先/旧键兼容）、deriveTaskSummary（null/0 保真）、dashboard 分列（明确断言仅有 completed 时 passed=0）、对比按 item_id、重名不同 item_id 不互换 |

### 9.3 实现要点与联调依据
- **通过率口径**：后端 `summary/all` 的 tasks 项与 `GET /reports/{id}` 的 summary 均提供
  `pass_rate`（number|null，statistics 统一公式）；前端仅做 `toPassRate` 归一与展示，
  无任何 `passed/total*100` 计算（grep 证明见 9.5）。
- **counts 来源**：单任务报告（详情）直接使用后端 `summary.counts` 五类计数；
  汇总列表接口（legacy `/reports/summary/all`）的 tasks 项暂无逐任务 counts，
  前端用 `countStatuses` 对 `data.results` 按 `task_id` 精确汇总五类状态——
  这是状态精确计数而非通过率公式，skip/error/timeout 均如实分列，未并入失败。
- **dashboard 分列**：优先 `data.task_outcomes`（后端完整分列），回退 `data.today` 同名字段；
  明确断言：仅有 `completed` 而无 `passed` 字段时 `passed=0`，不把 completed 当 passed。
- **报告对比**：键为 `item_id`（稳定对比键），`item_name` 仅显示；重名不同 item_id
  不合并不互换（用例覆盖）；`execution_time=0` 保留为 `0秒`，缺失为 null（不显示为 0）。
- **isSuccessResponse / 授权加载**：reports/dashboard 所有请求仍经 `isSuccessResponse`
  2xx 判定与原有 try/catch/finally 加载逻辑，未改动授权与加载行为。

### 9.4 命令与退出码（2026-11-12 17:24）
| 命令 | 开始 | 结束 | 退出码 | 原始日志 |
|---|---|---|---|---|
| `npm test` | 17:24:36.366 | 17:24:37.950 | 0 | `v1-06-frontend-npm-test.log` |
| `npm run lint` | 17:24:37.960 | 17:24:39.323 | 0 | `v1-06-frontend-npm-lint.log` |
| `npm run build` | 17:24:39.324 | 17:24:46.398 | 0 | `v1-06-frontend-npm-build.log` |

- `npm test`：5 个测试文件 **56 用例全绿**（datetime 3 + client 27 + v1-10 10 + v1-06 13 + request 3）。
- `npm run lint`：**994 warnings / 0 errors**（相对改动前基线 1037 warnings/0 errors 减少 43 条：
  dashboard 70→29、reports 191→189，为新增模板按 vue 规则格式化与删除旧自算代码所致；
  未新增任何 error/warning，未关闭规则或排除文件）。
- `npm run build`：退出码 0（7.1s），历史告警（Sass legacy-js-api、chunk>500kB）与基线一致。

### 9.5 静态 grep 证明
`v1-06-frontend-grep.log`：对 `reports/index.vue`、`dashboard/index.vue` 扫描——
自算通过率公式（passed/total*100、Math.round 除法）0 处；旧 summary 字段
passed/failed/skipped 读取 0 处；`getPassRate` 残留 0 处；`execution_time ||` 0 处；
统一口径调用点（formatPassRate/toPassRate/normalizeSummary/deriveTaskSummary/
buildCompareRows）9 处，逐行列出。

### 9.6 未验证项与遗留
- 未做浏览器亮/暗主题与真实后端联调实测（环境无后端/未启动前端服务）；null 通过率、
  分列卡片、对比“不可对比”标签的实际渲染属页面走查范围。
- legacy `/reports/summary/all` 的 tasks 项未含逐任务 `counts`，前端以结果状态精确计数
  代替；后端将该字段并入 tasks 项后可进一步收口（属后端契约迁移，超出本任务范围）。
- `createSubmitGuard` 等此前交付项不受影响；未改 `package.json`（不在本任务写范围）。
- 迁移与设备改派的并在途失败未由本任务修复，最终严格全量以 Lead 收口为准。

## 9. task-20 追加记录（V1-06 收口：Dashboard `data.today` 完整分列）

- 日期：2026-11-12；改动仅限 `app/api/dashboard.py`、
  `tests/integration/test_security_hardening.py`、`tests/integration/test_v1_statistics.py` 与本证据目录。

### 9.1 改动

1. `app/api/dashboard.py`：按 `docs/contracts/reporting-v1.0.md` §5，把完整分列并入
   `data.today`：在保留既有兼容键 `tasks/passed/failed/pass_rate` 的基础上，新增
   `completed`（= passed+failed+no_result，status=completed 总数）、`no_result`
   （全 skip/零记录）、`execution_failed`（平台 failed）、`cancelled`、`running`、
   `pending`。每个今日任务只归入一个分列键，各分列之和恒等于 `today.tasks`；
   `pass_rate` 分母仍仅取 completed 且 result∈(passed,failed)，分母 0 → null。
   顶层 `task_outcomes` 与 `today` 分列同源同值（保留兼容，不删除）。
2. `tests/integration/test_security_hardening.py::test_dashboard_stats_response_shape`：
   today 键集合断言由 4 键收紧为 reporting §5 的 10 键，并新增零态下
   completed/no_result/execution_failed/cancelled/running/pending 全为 0、
   pass_rate=None（分母 0）断言（更严不放宽）。
3. `tests/integration/test_v1_statistics.py` DASH-01：断言 `set(today.keys())` 完整 10 键、
   混合场景 completed=4 / no_result=2 / execution_failed=1 / cancelled=1 / running=1 /
   pending=0、分列和=tasks=7、today 与 task_outcomes 同值；零任务用例同样收紧为
   10 键全 0 + pass_rate None。上述 §7-1 的「Dashboard 响应形状偏差」由此关闭。

### 9.2 测试与原始日志

| 命令 | 结果 | 日志 |
|---|---|---|
| `pytest tests/integration/test_v1_statistics.py tests/integration/test_security_hardening.py -q -W error::pytest.PytestUnraisableExceptionWarning` | **15 passed，退出码 0** | `pytest-dashboard-task20.log` |
| `pytest tests -q -W error::... --ignore=tests/unit/test_v1_migration.py --deselect=tests/integration/test_devices_api.py::test_refresh_devices --deselect=tests/e2e/test_full_workflow.py::test_full_workflow` | **416 passed, 2 deselected，退出码 0** | `pytest-full-clean-task20.log` |

§6 所述并在途失败（task-11/task-19 迁移、device.py 与 mock 未同步）在本次全量中
状态不变，仍不由本任务（task-16/task-20）修复；最终以 Lead 严格全量为准。
