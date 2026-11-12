# RR-V1-FIX-T08B：V1-06 收口——Dashboard today 完整分列 + 前端统计显示（task-20/task-21 合并）

- 评审编号：RR-V1-FIX-T08B
- 评审对象/任务编号：task-20（Dashboard today 完整分列）+ task-21（前端 reports/dashboard 统计显示）；对应 RR-V1-FIX-T08 遗留 G1/G2 收口
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/reporting-v1.0.md` v1.0 §5、`docs/design/execution-state-machine.md` §3/§5/§6、`RR-V1-FIX-T08.md`（G1/G2 遗留）、`verification-rules-v1.0.md` §4/§7
- 环境与 commit/变更集：Windows 10；Node v24.15.0 / Python 3.12.10；git HEAD `fa70d3b` + 工作区。task-20 变更：`app/api/dashboard.py`（today 10 键完整分列 + task_outcomes + pending_tasks，全部经 statistics.classify_task_for_dashboard）、`tests/integration/test_security_hardening.py`（today 形状断言收紧为 10 键+零态全 0+pass_rate None；另含 task-12 scope 的 201 一处）。task-21 变更：`views/dashboard/index.vue`、`views/reports/index.vue`（统计显示统一走后端口径）
- 证据路径：评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t08b-backend-focused-reviewer.log`（15 passed）、`v1-fix-t08b-npm-test.log`（56 passed）、`v1-fix-t08b-npm-lint.log`（994w/0e）、`v1-fix-t08b-npm-build.log`（exit 0）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | ① today 10 键（tasks/passed/failed/pass_rate + completed/no_result/execution_failed/cancelled/running/pending） | 读 dashboard.py 返回体 | today 含全部 10 键 | 通过 |
| 2 | ① 每任务唯一归桶 → 分列和 = tasks | 读 dashboard.py classify 循环 + build_dashboard_breakdown | 每任务恰入一个计数键；`today_completed=passed+failed+no_result` | 通过 |
| 3 | ① 零态全 0 + pass_rate=None | 独立跑 test_security_hardening::test_dashboard_stats_response_shape | 断言 10 键集合、completed/passed/failed/no_result/execution_failed/cancelled/running/pending 全 0、pass_rate is None | 通过（15 聚焦 passed 内） |
| 4 | ② 前端 formatPassRate null/0 语义 | grep + 读 views | dashboard/reports 均用 `formatPassRate(pass_rate)`/`toPassRate`；null→"无有效结果"，0 显示 0 | 通过 |
| 5 | ② 通过率不自算（自算残留 0） | grep `passed/total`、`pass_rate` | reports：`summary?.pass_rate` 严格取后端 number|null（注释"不自算通过率"）；grep 无 `passed/total_items` 自算残留 | 通过 |
| 6 | ② completed ≠ passed（分列展示不把 completed 当 passed） | 读 dashboard/index.vue:3,197,217,324,350-360 | 卡片"通过（业务）"取 passed；completed 单独分列展示 | 通过 |
| 7 | ② 耗时 0 保真、item_id 对齐 | 读 reports/index.vue:263-265,481（formatDurationSeconds(row.execution_time)，`?? 0` 不吞 0） | 0 秒显示 0 秒；对比按稳定 item_id（RR-V1-FIX-T08 ZERO-01 已核） | 通过 |
| 8 | ③ lint 减少 43 条成因 | `.eslintrc.cjs`/`package.json` **未变更**（git status 空）；diff 为删除旧自算代码 + 统一格式化 | 1037→994 warnings（-43）、0 errors；未关规则/未排除文件 | 通过（未关规则） |
| 9 | 独立重跑前端 test/lint/build | `npm test` / `npm run lint` / `npm run build` | **56 passed**（5 文件，+13 统计显示用例）/ 994w-0e / build exit 0 | 通过 |
| 10 | ④ 未与真实后端联调 | 环境 | 无后端服务；前端以契约口径实现，未联调 | 如实（记限制） |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/integration/test_v1_statistics.py tests/integration/test_security_hardening.py`（聚焦） | **15 passed** | 0 | `evidence/v1-fix-20261112/v1-fix-t08b-backend-focused-reviewer.log` |
| `npm test` | **56 passed**（5 文件） | 0 | `evidence/v1-fix-20261112/v1-fix-t08b-npm-test.log` |
| `npm run lint` | 994 warnings / 0 errors（较基线 −43，未关规则） | 0 | `evidence/v1-fix-20261112/v1-fix-t08b-npm-lint.log` |
| `npm run build` | 构建成功 | 0 | `evidence/v1-fix-20261112/v1-fix-t08b-npm-build.log` |
| 最终严格全量 | 待 Lead 最终日志（task-17 完成后），届时补记 | — | — |

## 3. 问题与风险等级 / 遗留

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T08B-1 | 前端与真实后端联调未做（无后端服务） | 环境限制 | 201/统计字段真实链路待联调 | 中（范围外） | 最终联调/T-38 |
| P-V1T08B-2 | 浏览器 console 0 error/warning、九状态/断点/可访问性页面验收未做 | verification §7 属 T-22+/T-35 | 前端最终门禁未达（V1-11/T-35 范围） | 中（范围外） | T-35/T-22+ |
| P-V1T08B-3 | lint 仍 994 warnings（0 errors） | lint 日志 | 较基线 −43 但远未达 0 warning 门禁 | 中（V1-11/T-35） | T-35 |

## 4. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 真实后端联调、浏览器验收 | 环境无后端；浏览器验收属 T-22+/T-35 | 无法核验 |
| L2 | 最终严格全量 | 待 Lead（task-17 完成后） | 待补记 |

## 5. 待用户确认项

无新增。前端最终 0 warning 门禁（T-35）与浏览器验收仍为 V1-11/T-35 范围。

## 6. 最终结论

**通过（V1-06 收口：G1/G2 遗留关闭）。** task-20：Dashboard `today` 按 reporting §5 直接含 10 键完整分列，每任务唯一归桶（分列和=tasks），零态全 0+pass_rate=None，形状断言收紧为 10 键（更严）；task-21：前端 dashboard/reports 统计显示统一走后端口径（formatPassRate null/0、自算通过率残留 0、completed≠passed 分列、耗时 0 保真、item_id 对齐）；lint 994w/0e 的 −43 来自删除旧自算代码与格式化，**未关闭任何规则**（.eslintrc/package.json 未变）。独立重跑：后端聚焦 15 passed、前端 56 passed、lint/build exit 0。限制：未与真实后端联调、浏览器/0-warning 门禁属 T-22+/T-35（V1-11）。全量以 Lead 最终严格日志为准。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、契约与独立重跑作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
