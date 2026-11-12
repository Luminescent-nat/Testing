# T-10 任务创建/重跑幂等与 201 入口集成（V1-04）— 结果记录

- 任务编号：task-12（V1-04 入口集成，依赖 task-9 授权版 tasks.py）
- 执行人：migration-idempotency（Agent Team）
- 日期：2026-11-12（Asia/Shanghai，UTC+08:00）
- 契约/依据：`docs/contracts/README.md` 第 3 节（写操作幂等）、`RR-V1-READINESS-20261112.md` V1-04、`docs/verification/reviews/evidence/v1-readiness-20261112/idempotency-repro.log`
- 依赖：task-9（统一设备授权）已完成；本任务未破坏其写前授权守卫 `ensure_can_create_task_on_device`。

## 1. 变更文件

| 文件 | 变更 |
|---|---|
| `test-platform/backend/app/api/tasks.py` | ①`POST /tasks`/`POST /tasks/{id}/reruns`/legacy `POST /tasks/{id}/rerun-failed` 改 `status_code=201`、成功外层 `code=201`；②新增 `Idempotency-Key` 头（8～128 可打印 ASCII），复用 `app/services/idempotency.py`：同用户同操作同键同规范化请求 sha256 重放首次响应与同一任务 ID，同键不同请求体 409 CONFLICT，并发由 DB 唯一约束兜底；③缺失键=不强幂等（兼容策略，见 §4）；④授权/设备/测试项/参数/调度校验完整保留在 `_execute()` 内（写前校验语义不变） |
| `test-platform/backend/tests/integration/test_v1_idempotency.py`（新） | 9 用例：同键同体重放（201/同 ID/DB 1 行）、同键不同体 409、并发 10 至多一次、缺失键不强幂等、非法键 400（过短/过长/不可打印）、reruns+rerun-failed 201 且复用幂等（跨源任务同键 409）、重跑缺失键 201 |
| `test-platform/backend/tests/integration/test_tasks_api.py` | 创建/重跑成功断言 200→201（并断言外层 code=201，更严不放宽）；其余 GET/取消断言不变 |
| `test-platform/backend/tests/integration/test_contract_errors.py` | **scope 经 Lead 授权扩充**：创建成功 1 处、reruns 成功 1 处 200→201（cancellations/cancel 保持 200） |
| `test-platform/backend/tests/integration/test_v1_authorization.py` | **scope 授权扩充**：创建成功 2 处、rerun-failed 成功 1 处 200→201，授权断言不变 |
| `test-platform/backend/tests/integration/test_security_hardening.py` | **scope 授权扩充**：合法参数创建成功 1 处 200→201 |
| `test-platform/backend/tests/e2e/test_full_workflow.py` | **scope 授权扩充**：创建任务成功 1 处 200→201 |
| `docs/verification/tasks/T-10/*` | 本记录与全部原始日志 |

未触碰：`app/services/authorization.py`、`models/alembic/database`、`judgement/execution/task_executor`、`frontend`、`test-tools`。

## 2. 幂等设计（复用 task-11 服务）

- 幂等范围：`(user_id, operation, idempotency_key)`，`operation` 取 `task_create` / `task_rerun`；DB 唯一约束 `uq_idempotency_user_op_key` 兜底并发。
- 请求摘要：`task_create` 用 `TestTaskCreate.model_dump(mode="json")` 规范化 sha256；`task_rerun` 用 `{"task_id": id}` 规范化 sha256（同键不同源任务 → 409）。
- 执行编排（`run_idempotent`）：先查记录（命中即重放/冲突判定）→ 未命中先 `claim_key` 占键（先写 response_json=NULL 并提交）→ `_execute()` 真实校验+建任务 → `complete_with_response` 写回首次响应；并发抢占失败方等待首次响应后重放，首次执行失败会释放占键记录。
- 响应序列化：`ResponseModel(...).model_dump(mode="json")` 保证 datetime → ISO 字符串，可安全存入 JSON 列并在重放时原样返回。
- 重放不重复写：重放路径不调用 `_execute()`，不写设备状态、不启动执行器；HTTP 201 + 外层 code=201。
- 授权守卫：`_execute()` 内先 `ensure_can_create_task_on_device` 再写（与 task-9 一致）；重放路径为同一用户同键重放（不写库），不再重复授权判定。

## 3. 命令、退出码与结果（原始日志见 §5）

| # | 命令（WORKDIR=backend） | 退出码 | 结果 |
|---|---|---:|---|
| 1 | 审计定向反例 `test_audit_same_idempotency_key_creates_only_one_task`（targeted-defect-repro.py，临时拷入 tests 运行后删除） | 0 | **1 passed（fail→pass 确认）**：两次 201、同 ID、DB 1 行 |
| 2 | `python -m pytest tests/integration/test_v1_idempotency.py -v` | 0 | **9 passed** |
| 3 | `python -m pytest tests/integration/test_tasks_api.py tests/integration/test_contract_errors.py tests/integration/test_v1_authorization.py tests/integration/test_security_hardening.py tests/e2e/test_full_workflow.py -q` | 0 | **50 passed** |
| 4 | `python -m pytest tests -q`（全量回归） | 0 | **404 passed in 195.58s**（0 failed） |

## 4. 缺失键兼容策略与需用户确认的偏差

- **缺失 `Idempotency-Key` = 不强幂等**：正常创建并每次返回 201（不写幂等记录）。理由：保证既有客户端与全部既有用例可运行；契约第 3 节将任务创建/重跑列为「`Idempotency-Key` 必填」，故此处为**兼容期偏差，待用户确认**。若需强制必填，可改为缺失即 400（会破坏现网旧客户端），需用户拍板后另行实施。
- **设备不可用状态码**：offline/maintenance 当前仍返回 **400 VALIDATION_ERROR**（既有契约与用例）；`RR-V1-READINESS` V1-04 曾提「设备不可用等冲突按契约 409」。本任务未改（避免与既有测试/其他契约冲突，且非本任务 DoD 明列项），列为**待确认偏差**。
- **幂等键命名空间**：`task_create` 与 `task_rerun` 为不同 operation，同一 key 字符串在两个操作间互不影响（符合 `(user_id,operation,key)` 设计）。

## 5. 原始日志与产物（UTF-8）

- `docs/verification/tasks/T-10/targeted-defect-repro-20261112.log` — 审计定向反例 fail→pass（1 passed）
- `docs/verification/tasks/T-10/pytest-v1-idempotency-20261112.log` — 新增 9 用例逐项 passed
- `docs/verification/tasks/T-10/regression-full-v1-20261112.log` — 全量回归 404 passed（0 failed，exit 0）

## 6. DoD 逐条

| 要求 | 状态 | 证据 |
|---|---|---|
| POST /tasks 支持 Idempotency-Key（8～128 可打印 ASCII） | ✅ | `test_invalid_idempotency_key_rejected`（400）；`test_same_key_same_body_replays_single_task` |
| 同用户同操作同键同请求重放首次响应与任务 ID | ✅ | 同上 + 定向反例 1 passed |
| 同键不同请求体 409 CONFLICT | ✅ | `test_same_key_different_body_returns_409` |
| 并发 10 次至多一次（DB 唯一约束兜底） | ✅ | `test_concurrent_same_key_creates_at_most_one_task`（DB 1 行任务/1 行幂等） |
| 创建成功 HTTP 201（外层 code=201） | ✅ | test_tasks_api / contract_errors / security / e2e 断言更新 |
| /reruns 与 legacy rerun-failed 同样 201 且复用幂等 | ✅ | `test_rerun_endpoints_return_201_and_reuse_idempotency`（201 同 ID；跨源任务同键 409） |
| 不破坏 task-9 授权守卫 | ✅ | `test_v1_authorization.py` 17 passed（越权 403 零写入仍成立） |
| 新增 tests/integration/test_v1_idempotency.py | ✅ | 9 用例 |
| 更新既有 tasks 测试 200→201（更严不放宽） | ✅ | 本文件 + 4 个授权 scope 文件仅收紧状态码并加 code 断言 |
| 证据 docs/verification/tasks/T-10/ | ✅ | 本目录 |

## 7. 遗留 / 无法核验项

1. 缺失键=不强幂等（兼容期偏差，待用户确认是否改为必填 400）。
2. 设备不可用仍 400（RR 提到 409，未改，待确认）。
3. 幂等键过期/清理策略未实现（当前记录永久保留；后续可加 TTL 清理任务，不属本任务 DoD）。
4. 真实高并发压测未做（仅 ASGI 层 10 并发功能验证；SQLite busy_timeout 兜底，未做生产规模压测）。
