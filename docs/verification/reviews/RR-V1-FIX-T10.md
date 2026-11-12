# RR-V1-FIX-T10：V1-04 任务创建/重跑幂等与 201 入口集成（task-12）

- 评审编号：RR-V1-FIX-T10
- 评审对象/任务编号：task-12（V1-04 入口集成；对应 T-10，依赖 task-9 授权版 tasks.py）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/README.md` v1.0 §3（写操作幂等）、`docs/contracts/task-execution-v1.0.md` v1.0 §2（错误码表：设备 offline/maintenance=409 CONFLICT）、`RR-V1-READINESS-20261112.md` V1-04、`targeted-defect-repro.py` R2
- 环境与 commit/变更集：Windows 10；Python 3.12.10；git HEAD `fa70d3b` + 工作区（task-12 未提交）。变更：`app/api/tasks.py`（POST /tasks、/reruns、legacy rerun-failed → 201 + Idempotency-Key 复用 `app/services/idempotency.py`；授权守卫保留）、新增 `tests/integration/test_v1_idempotency.py`(9)、若干既有测试 200→201（scope 经 Lead 授权）
- 证据路径：`docs/verification/tasks/T-10/`（result.md、targeted-defect-repro-20261112.log、pytest-v1-idempotency-20261112.log、regression-full-v1-20261112.log）；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t10-idempotency-reviewer.log`（9 passed）、`v1-repro-R2-after-task12.log`（1 passed）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | ① repro R2：同键同体重放两次 201、同 ID、DB 1 行 | 独立重跑 R2（shim 插件，临时库） | **1 passed / 5 deselected**（两次 201、同 task ID、DB 1 行） | 通过 |
| 2 | ② 同键同体重放（201/同 ID/DB 1 行） | 读 idempotency.py run_idempotent（命中重放不 execute）+ test | test_same_key_same_body_replays_single_task；独立 9 passed | 通过 |
| 3 | ② 同键不同体 409 | check_replay_or_conflict（sha256 不同→ConflictError→409）；test | test_same_key_different_body_returns_409 | 通过 |
| 4 | ② 并发 10 至多一次（DB 唯一约束兜底） | 读 claim_key（IntegrityError→读首次）+ test | test_concurrent_same_key_creates_at_most_one_task（DB 1 行任务/1 行幂等） | 通过 |
| 5 | ② 缺失键兼容策略（不强幂等） | 读 _resolve_idempotency_key + create_task key=None 分支 | 缺失→正常执行每次 201，不写幂等记录；test_rerun_without_key_returns_201... | 通过（偏差见 §3） |
| 6 | ② reruns/legacy rerun-failed 201 复用幂等 | 读 targets 路由 + rerun_failed_items（operation=task_rerun, payload={task_id}） | test_rerun_endpoints_return_201_and_reuse_idempotency（201 同 ID；跨源任务同键 409） | 通过 |
| 7 | ② 非法键 400 | _resolve_idempotency_key→validate→400 | test_invalid_idempotency_key_rejected（过短/过长/不可打印） | 通过 |
| 8 | ③ 授权守卫未破坏 | 读 create_task `_execute` 内先 ensure_can_create_task_on_device 再写；重放不重复执行 | test_v1_authorization.py 17 passed（越权 403 零写入仍成立）；R1 仍 403 | 通过 |
| 9 | 201 契约（HTTP 201 + 外层 code=201） | 读 status_code=201 + ResponseModel(code=201) | 既有 tasks/contract_errors/security/e2e 断言更新为 201（更严） | 通过 |
| 10 | 失败占键释放（异常后不锁死） | 读 run_idempotent except→delete record&commit&raise | 并发/失败可重试（代码级） | 通过 |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| repro R2（shim 插件，临时库） | **1 passed / 5 deselected** | 0 | `evidence/v1-fix-20261112/v1-repro-R2-after-task12.log` |
| `pytest tests/integration/test_v1_idempotency.py` | **9 passed** | 0 | `evidence/v1-fix-20261112/v1-fix-t10-idempotency-reviewer.log` |
| 开发证据：定向反例 | 1 passed | 0 | `docs/verification/tasks/T-10/targeted-defect-repro-20261112.log` |
| 开发证据：全量 | 404 passed | 0 | `docs/verification/tasks/T-10/regression-full-v1-20261112.log` |
| 最终严格全量 | 待 Lead 最终日志，届时补记 | — | — |

## 3. 三个遗留偏差的如实性与对 V1-04 的判定

| # | 偏差 | 是否如实记录 | 是否阻塞 V1-04 通过 | 待用户确认 |
|---|---|---|---|---|
| D1 | 缺失 `Idempotency-Key` = 不强幂等（契约 §3 将任务创建/重跑列为**必填**） | 如实（result §4） | **不阻塞幂等核心**：提供 key 时重放/冲突/并发均正确；缺失只是放宽为不强幂等 | **是**：是否改为缺失即 400（强制必填，会破坏旧客户端） |
| D2 | 设备 offline/maintenance 返回 **400 VALIDATION_ERROR**，契约错误码表与审计 V1-04 明列应为 **409 CONFLICT** | 如实（result §4） | **阻塞 V1-04 完全闭环**：这是审计 V1-04 明列的"设备不可用等冲突按契约 409"未达成，属契约错误码不符 | **是/应修复**：改 409（或用户明确修订契约接受 400 并留变更记录） |
| D3 | 幂等键 TTL/清理未实现（记录永久保留） | 如实（result §7.3） | **不阻塞**（非 DoD，运维/后续增强） | 可后续 |

## 4. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T10-1 | 设备 offline/maintenance 仍 400，契约/审计要求 409 | contract task-execution §2；RR V1-04；result §4 | 契约错误码不符；V1-04「设备不可用=409」未闭环 | 中 | task-12 后续修复 / 用户改契约 |
| P-V1T10-2 | 缺失键=不强幂等，契约 §3 必填 | result §4 | 客户端可绕过幂等；兼容期偏差 | 中 | 待用户确认 |
| P-V1T10-3 | 幂等记录无 TTL 清理 | result §7.3 | 表长期增长；运维后续 | 低 | 后续 |
| P-V1T10-4 | 仅 ASGI 层 10 并发功能验证，无生产规模压测 | result §7.4 | 生产并发未知；SQLite busy_timeout 兜底 | 低 | 记录性 |

## 5. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 真实高并发/生产压测 | 未做 | 仅功能级 10 并发；生产规模未验证 |
| L2 | 全量 404 passed 为自报 | 以 Lead 最终严格全量日志为准 | 独立重跑 9 passed + R2；全量待补记 |

## 6. 最终结论

**有条件通过（V1-04 幂等+201 核心达成；设备不可用 409 契约项未达成）。** repro R2 由 FAILED 转 **PASS**（两次 201、同 ID、DB 1 行，独立重跑 1 passed）；9 用例独立重跑 9 passed 覆盖同键同体重放、不同体 409、并发 10 至多一次、缺失键策略、非法键 400、reruns/rerun-failed 201 复用；201 契约落地（HTTP+外层 code=201）；task-9 授权守卫保留（越权 403 零写入）。三个遗留偏差均如实记录：D1（缺失键不强幂等）**不阻塞核心、待用户确认是否强制必填**；**D2（设备不可用 400 vs 契约 409）阻塞 V1-04 完全闭环，属契约错误码不符，应修复 409 或经用户修订契约**；D3（TTL）不阻塞、后续。故 V1-04 记「有条件通过/部分未闭环」，D2 记入 RR-V1-FINAL。全量以 Lead 最终严格日志为准。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、契约、定向反例与独立幂等/重跑测试作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
