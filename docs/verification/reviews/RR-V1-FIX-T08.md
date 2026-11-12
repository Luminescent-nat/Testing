# RR-V1-FIX-T08：V1-06 统一统计、进度与 result 口径（task-16）

- 评审编号：RR-V1-FIX-T08
- 评审对象/任务编号：task-16（V1-06 统计口径；对应 T-08）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/design/execution-state-machine.md` v1.0 §3/§5/§6、`docs/contracts/reporting-v1.0.md` v1.0 §5、`docs/verification/verification-rules-v1.0.md` §4（STAT/DASH/ZERO）、`RR-V1-READINESS-20261112.md` V1-06
- 环境与 commit/变更集：Windows 10；Python 3.12.10；git HEAD `fa70d3b` + 工作区。变更：新增 `app/services/statistics.py`；`app/schemas.py`（TestTaskResponse 增 total_items/completed_items/counts/pass_rate、compute_result→compute_aggregates 经 statistics、DeviceResponse.version）、`app/websocket.py`、`app/api/reports.py`、`app/api/dashboard.py`；新增 `tests/integration/test_v1_statistics.py`(9)
- 证据路径：`docs/verification/tasks/T-08/`（result.md、pytest-v1-statistics.log、pytest-consumers.log、pytest-full-clean.log）；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t08-statistics-reviewer.log`（9 passed）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | ① 单一 statistics.py 被详情/列表/WS/报告/导出复用 | grep import/调用 + 读 | `from app.services import statistics`：schemas.py:6（compute_aggregates:350/367→详情/列表）、websocket.py:12/118、reports.py:23、dashboard.py:12；无消费者另写相反公式 | 通过 |
| 2 | ② STAT-01（pass2/fail1/timeout1/skip2） | 独立跑 test_v1_statistics | C=6、progress=100、pass_rate=50.0、详情/WS/报告一致；result=failed | 通过 |
| 3 | ② STAT-02（全 skip） | 同上 | completed、result=null、pass_rate=null（断言 is None 且 != "0%"）、C=3、progress=100 | 通过 |
| 4 | ② STAT-03（3 pass + 1 running） | 同上 | completed_items=3（running 不计）、total=4、progress=75、status=running、result=null、WS 一致 | 通过 |
| 5 | ② DASH-01（混合 7 任务 + 零任务） | 同上 | today passed1/failed1/pass_rate50.0；task_outcomes passed1/failed1/no_result2/execution_failed1/cancelled1/running1；零任务 pass_rate=null；分列和=总数 | 通过 |
| 6 | ② ZERO-01（耗时0/值0/无对应项/重名不同ID） | 同上 | 重名不同 item_id 不合并；execution_time=0、bw_mbps=0/iops=0 保留；缺失指标渲染 `-`；markdown 0 显示 0 非 `-`；Excel 可生成 | 通过 |
| 7 | ③ running/pending 不计 completed、未完成 result=null | 读 statistics.compute_task_statistics:94-107（仅 completed & C=N & R=0 & P=0 才判 result） | 代码级 + STAT-03/truth_table 真值表 | 通过 |
| 8 | ③ skip 不进分母、零分母 number null | 读 compute_pass_rate（分母 pass+fail+error+timeout，skip 排除；<=0→None） | STAT-02/零记录断言 pass_rate=None | 通过 |
| 9 | ④ 报告趋势/模块同口径、0 显示修复 | 读 reports.py（trend/by-module 改 statistics + 分列；_format_pass_rate/_fmt_metric/_fmt_pct） | 用例 + 独立 9 passed；0 值渲染 0 不再 `-` | 通过 |
| 10 | 9 用例独立执行 | `pytest tests/integration/test_v1_statistics.py` | **9 passed**，exit 0 | 通过 |
| 11 | 未越界 | git diff/status | 未改 tasks.py（task-12 在改）、models/alembic/database、judgement/execution/task_executor、frontend、test-tools | 通过 |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/integration/test_v1_statistics.py` | **9 passed** | 0 | `evidence/v1-fix-20261112/v1-fix-t08-statistics-reviewer.log` |
| 开发证据：消费者套件 81 passed | 81 passed | 0 | `docs/verification/tasks/T-08/pytest-consumers.log` |
| 开发证据：剔除在途后全量 | 416 passed, 2 deselected | 0 | `docs/verification/tasks/T-08/pytest-full-clean.log` |
| 严格全量（当前含在途） | 404 passed, 8 failed（task-19 Device.version 迁移在途） | 1 | `docs/verification/tasks/T-08/pytest-full.log` |
| 最终严格全量 | 待 Lead 收口 task-11/19/20/21 后日志，届时补记 | — | — |

## 3. 问题与风险等级 / 遗留偏差（如实性）

| # | 偏差/遗留 | 是否如实记录 | 判定 | 去向 |
|---|---|---|---|---|
| G1 | **Dashboard `data.today` 形状**：reporting §5 要 today 直接含 completed/no_result/execution_failed/cancelled；当前保持既有 4 键 `{tasks,passed,failed,pass_rate}`，完整分列放在顶层 `data.task_outcomes`（因 test_security_hardening 形状断言属 task-12 在途文件，未并发改） | 如实（result §7.1） | **语义等价、可核对；严格契约形状待收口** | task-20（stats-unify）收口 + 同步更新形状断言（更严） |
| G2 | 前端 reports 仍自算通过率（passed/total，把 skip 计入分母） | 如实（result §7.3） | 后端口径已统一；前端展示整改属前端任务 | task-21（在派） |
| G3 | Legacy 报告 summary `failed`=fail+timeout（历史展示口径），pass_rate 已严格 | 如实（result §7.2） | 兼容旧前端；完整 v2.0 字段迁移超 V1-06 范围 | 报告契约迁移后续 |
| G4 | ZERO-01「无对应项→不可对比」跨报告对比属前端对比视图，后端未落地 | 如实（result §7.4） | 后端保证 item_id 对齐/0 保留/缺失指标 `-`；对比文案前端 | 前端 reports 对比任务 |
| G5 | DeviceResponse.version 依赖 task-19 Device.version 列/003 迁移（在途） | 如实（result §7.5） | 字段已加，依赖迁移收口 | task-19 |
| P-V1T08-1 | 严格全量 8 failed = test_v1_migration.py（`devices 缺少列: version`），2 failed = device.py mock 在途 | 非本任务（result §6） | 不影响统计口径结论 | task-19/task-11 收口 |

## 4. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 浏览器页面/前端 reports、dashboard 展示 | 本任务仅后端；前端属 task-20/task-21 | 前端展示未核验 |
| L2 | 全量为自报 | 以 Lead 最终严格全量日志为准 | 独立重跑 9 passed；全量待补记 |

## 5. 待用户确认项

无新增（统计口径严格对齐已确认状态机 §3/§5/§6）。G1/G2 由 task-20/task-21 收口。

## 6. 最终结论

**通过（V1-06 后端统计/进度/result 口径）。** 新增 `app/services/statistics.py` 为唯一口径来源，任务详情/列表（经 schemas.compute_aggregates）、WebSocket、报告、导出、Dashboard 全部复用（grep 确认无第二套公式）；running/pending 不计 completed、未完成任务 result=null（仅 completed&C=N&R=0&P=0 才判 passed/failed）；skip 不进通过率分母、零分母统一 number null；报告趋势/模块同口径且 0 值显示修复。STAT-01/02/03、DASH-01、ZERO-01 等 **9 用例独立重跑 9 passed**。遗留如实：G1 Dashboard today 形状待 task-20 收口（当前 task_outcomes 顶层语义等价）、G2 前端展示待 task-21、G3 legacy summary 兼容、G4 跨报告对比前端、G5 Device.version 依赖 task-19；严格全量 8+2 failed 均他任务在途，最终以 Lead 收口后严格全量为准。

## 7. 签名

reviewer，2026-11-12；本记录基于源码、statistics 单源复核、契约与独立统计测试作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
