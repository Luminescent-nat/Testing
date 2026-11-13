# RR-V11-FIX-C：契约 v1.1 实施轮竞态治理（task-26 / task-C2 export 已收口；task-25 / task-C1 cancel 续节已并入，G7 达成）

- 评审编号：RR-V11-FIX-C
- 评审对象/任务编号：task-26（task-C2：报告导出落盘/读取竞态治理）【本记录当前范围】；task-25（task-C1：cancel 20 连跑+并发 10）完成后以续节并入本文件
- 评审日期：2026-11-13
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`RR-V1-REFINAL-20261112.md` §3.4（reviewer 两轮独立全量各 1 次 `test_export_report_html` 空响应）、`docs/contracts/reporting-v1.0.md`（TC-RPT-011 缓存语义）、`docs/verification/verification-rules-v1.0.md`
- 环境与 commit/变更集：Windows 10；Python 3.12.10；**基线 HEAD `387279e`** + 工作区。task-26 变更：`app/api/reports.py` 仅导出落盘/读取原语（原子写+读侧重试+导出经 _read_report_file 返回）；新增 `tests/integration/test_v1_export_stability.py`(3)；未动统计口径/授权/收尾/既有 reports 测试/契约
- 证据路径：`docs/verification/tasks/T-08/result.md` §10、`red-export-race-before-fix.log`（红证：1 failed 竞态复现）、`green-export-race-after-fix.log`（绿 3 passed）、`green-export-consumers.log`（30 passed）、`green-export-stability-repeat3.log`（连跑 3 轮 15×3 passed）、`pytest-full-clean-c2-green.log`（447 passed）、`pytest-full-clean-c2.log`（447/2 在途）；评审方独立重跑 `reviews/evidence/v11-fix-20261113/v11-fix-c2-export-reviewer.log`（15 passed）

## 1. 门禁与检查项（task-C2 部分）

| # | 门禁/检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | G9 契约 diff 空（本轮复核） | `git diff HEAD -- docs/contracts` | 0 行 | 通过 |
| 2 | G1 红：确定性竞态复现（mid-write 空响应） | 读 red-export-race-before-fix.log | `test_export_html_mid_write_cache_never_serves_empty_body` **FAILED（导出响应体为空）**，exit 1 | 通过 |
| 3 | G1 绿：同用例转绿 | 读 green-export-race-after-fix.log | 3 passed / exit 0 | 通过 |
| 4 | ③ 取舍①不放宽：缓存契约 TC-RPT-011 保持（缓存命中直接回吐、不现算） | 读 _write_report_file 原子写文档注释 + `git diff test_reports_api.py`=**未改** | `test_export_report_serves_cached_file` 既有断言原样通过（独立 15 passed 内） | 通过 |
| 5 | 修复原语：原子替换（唯一临时文件+flush+fsync+os.replace+异常清理）与读侧 PermissionError×5 重试 | 读 reports.py diff | 代码级确认；docstring 记录根因（截断窗口）与 Windows 共享冲突 | 通过 |
| 6 | 导出端点改经 _read_report_file 一次性读出（FileResponse→Response），200/Content-Type/attachment/字节/授权不变 | 读 export_report diff | 测试断言响应非空且含 `<html` | 通过 |
| 7 | **G8：20 连跑**（模块级连续 20 次导出，每 5 次删缓存混合现算+缓存两路径） | 独立重跑 test_export_html_20_consecutive_exports_non_empty | 通过（响应非空含 `<html`） | 通过 |
| 8 | 并发重写循环 20 轮（不引入人为延迟） | 独立重跑 test_export_html_concurrent_rewrite_loop | 通过（覆盖 os.replace×读 open 共享冲突瞬态） | 通过 |
| 9 | 既有测试不放宽 | git diff test_reports_api 未改；独立 15 passed（3 stability + 12 reports_api） | 通过 | 通过 |
| 10 | 根因定位可信 | 旧实现 `open(path,"wb")` 打开即截断 + exists 判缓存 + FileResponse 发送期 stat → content-length=0 | 与 reviewer 当初观察（两轮各 1 次空响应、隔离 3/3）一致 | 通过 |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest test_v1_export_stability.py test_reports_api.py` | **15 passed**（含 20 连跑与并发重写循环 20 轮） | 0 | `evidence/v11-fix-20261113/v11-fix-c2-export-reviewer.log` |
| 开发证据：红/绿 | 1 failed（竞态复现）→ 3 passed | 1→0 | `T-08/red-export-race-before-fix.log` / `green-export-race-after-fix.log` |
| 开发证据：连跑 3 轮 | 15×3 passed | 0×3 | `T-08/green-export-stability-repeat3.log` |
| 开发证据：剔除在途全量 | 447 passed, 4 deselected | 0 | `T-08/pytest-full-clean-c2-green.log` |
| 最终严格全量 | 待 Lead 两轮日志，届时补记 | — | — |

## 3. 问题与风险等级 / 遗留（C2）

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V11C-1 | 导出端点由 FileResponse 改为读出后 Response：大文件将整体载入内存 | reports.py export_report | 当前报告体量小（KB 级）；超大报告需流式化 | 低 | 记录性 |
| P-V1T26-2 | os.replace 在 Windows 对被读打开目标的失败仍按 best-effort 记日志（缓存保持旧完整文件） | reports.py docstring | 缓存更新可能滞后一轮，响应始终完整 | 低 | 记录性 |
| P-V1T26-3 | 严格全量当时含在途 AI/迁移失败 | pytest-full-clean-c2.log | 非本任务；最终以 Lead 两轮为准 | 记录性 | — |

## 4. 限制/无法核验项（C2）

全量口径以 Lead 连续 2 轮严格全量日志为准（待补记）。其余无。

## 5. 待用户确认项（C2）

无新增。

## 6. 最终结论（task-C2 部分）

**通过（G8 达成）。** 竞态根因定位可信且与 reviewer 原观察一致；先红（确定性复现空响应）后绿；修复采用①原子替换+读侧重试，完整保留 TC-RPT-011 缓存契约（既有测试 0 改动、独立 15 passed 含 20 连跑与并发重写循环 20 轮）；未动统计口径/授权/收尾。task-C1（cancel 20 连跑+并发 10，task-25）续节见下。

## 7. 签名（C2 部分）

reviewer，2026-11-13；本记录基于源码 diff、红绿日志与独立导出稳定性重跑作出，未替开发修改任何代码。

---

# 续节：task-C1 cancel 状态机条件更新与竞态治理（task-25，G7）

- 收口日期：2026-11-13；对应 `docs/verification/tasks/T-14/result.md`（task-C1 章节）与 `v1.1-*` 日志
- 变更：`app/api/tasks.py`（cancel 端点：标量化查询+条件更新 WHERE status IN(pending,running)+退避重试+提交 happens-before）、`app/services/task_executor.py`（收尾全条件化 `_transition_task_status` rowcount 判定；`_handle_cancel` 幂等收尾；`_skip_remaining_items`/stop 语义不变；单次投递 `_cancel_signalled`；取消收尾移出 except 作用域避免 exc_info 钉游标帧）、新增 `tests/unit/test_v1_cancel_stability.py`(7)、`tests/conftest.py`（busy_timeout 30+WAL+sidecar 清理，**Lead 授权测试夹具域**）、`tests/unit/test_v1_judgement_stop.py`（1 处打桩 exception→error+格式化堆栈，断言强度不变）

## C1-1. 根因链复核（红→绿逐层实证）

| # | 缺陷 | 评审核实 | 修复核实 |
|---|---|---|---|
| 1 | 无条件 ORM 写 + 陈旧属性 flush 后门（completed 覆盖 cancelled） | 红用例 1 日志 `v1.1-red-evidence.log` | 全部状态推进条件更新（rowcount），输者零写入 |
| 2 | _release_device 异常替换在飞 CancelledError → _handle_cancel 不执行 | 红用例 2（failed） | finally 加固：日志+rollback+重试一次，语义不变 |
| 3 | **真根因**：CancelledError traceback 钉住被打断 ORM 游标帧 → SQLite 读锁五连 BUSY（5.4s×5，diag-stab-run2 时间线吻合）→ cancelled 落不了库 | diag 日志逐条吻合 | 收尾移出 except 作用域（不绑定异常对象），锁释放后再 _handle_cancel+_ensure_cancelled_persisted |
| 4 | 并发取消重复投递打断收尾 | 并发 10 失败现场 | cancel_task 单次投递（_cancel_signalled） |
| 5 | 测试夹具：回滚日志模式读者被 PENDING 写锁拒 | STAB run2/run3 鉴权 SELECT BUSY | WAL+busy_timeout 30s（Lead 授权夹具域） |

## C1-2. 门禁与检查项

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | **G7：模块级 20 连跑双路径**（legacy /cancellations 各 20，事件钉 running 消除时序假失败） | **独立重跑** test_v1_cancel_stability | **7 passed / exit 0**（含 test_cancel_twenty_consecutive_cycles_legacy_api/_cancellations_api） | 通过（G7 达成） |
| 2 | **G7：并发 10**（legacy + 混发 5+5）全部返回、终态 cancelled、无 500 | 独立重跑 | test_concurrent_ten_cancels_legacy_no_500/_mixed_paths_no_500 通过 | 通过 |
| 3 | 终态重复取消→400 VALIDATION_ERROR 外层形状不变；竞态输者已 cancelled→200 幂等 | 读端点+单测 | test_cancel_terminal_task_returns_400_validation_error（双路径）；契约用例通过 | 通过 |
| 4 | 执行器收尾全条件化，输者零写入/不调度报告/不做记忆体 | 读 _transition_task_status + 红用例转绿 | 通过 | 通过 |
| 5 | 既有取消用例不放宽（test_cancel_running_task_keeps_cancelled 等 0 改动） | git diff test_task_executor.py 未改 | 通过 | 通过 |
| 6 | 两项范围扩展（Lead 批准）合规性 | 读 conftest diff（仅测试夹具引擎：timeout=30/WAL/sidecar 清理，生产连接参数未动）；读 test_v1_judgement_stop diff（仅 patch exception→error，call_count 断言不变，canary 断言保留——独立重跑 **32 passed**） | 均为测试基础设施/打桩语义，无生产影响、无放宽 | 通过（Lead 授权域确认） |
| 7 | G2：严格全量连续 2 轮 0 failed | Lead r1/r2 日志 | **467 passed ×2**（256.62s/255.66s，exit 0） | 通过 |
| 8 | G9 契约 diff 空 | 本轮复核 | 0 行 | 通过 |
| 9 | 未越界 | git status | 未触契约/ai_tasks/task_creation/reports/websocket/frontend | 通过 |

## C1-3. 独立重跑记录（续节）

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/unit/test_v1_cancel_stability.py` | **7 passed**（20×2 连跑 + 并发 10×2 + 终态 400） | 0 | `evidence/v11-fix-20261113/v11-fix-c1-cancel-stability-reviewer.log` |
| `pytest tests/unit/test_v1_judgement_stop.py`（打桩更新后） | **32 passed** | 0 | `evidence/v11-fix-20261113/v11-fix-c1-judgement-stop-reviewer.log` |
| 开发证据：红/诊断/稳定性 | 2 failed→diag→4 连绿 | 1→0×4 | `T-14/v1.1-red-evidence.log`、`v1.1-diag-stab-run1~3.log`、`v1.1-green-stability-run1~4.log` |
| 开发证据：全量 r1/r2 | **467 passed ×2** | 0×2 | `T-14/v1.1-pytest-full-r1.log`、`r2.log` |
| 开发证据：定向回归 | 75/94 passed | 0 | `T-14/v1.1-targeted-regression.log` |

## C1-4. 遗留 / 说明（续节）

1. 连续 2 轮全量 0 failed 达成（G2）；第 3 轮可继续累积（本轮按门禁 G2 收口）。
2. WAL/busy_timeout 仅测试临时库；生产库（行锁）无需同步——核实仅 conftest 测试夹具。
3. 并发 10"全部返回无 500"依赖 SQLite BUSY 退避（防御性）；生产行锁下不触发。
4. 打桩语义更新（exception→error+格式化堆栈）：完整堆栈仍仅进服务端日志，断言强度不变（call_count≥1、canary 不泄露）——核实通过，非放宽。

## C1-5. 续节结论

**G7 达成：通过（task-C1 cancel 竞态治理）。** 真根因链（条件更新缺失/异常替换/exc_info 钉帧五连 BUSY/重复投递/测试夹具锁模式）五层全部红→绿实证并独立复核；20 连跑双路径与并发 10 独立重跑 7 passed；既有取消断言零改动；两项 Lead 批准范围扩展均为测试域且无放宽。全量连续 2 轮 467×2 留痕。
