# RR-V1-FIX-T02：V1-04/V1-05 幂等数据模型与迁移闭环基础（task-11）

- 评审编号：RR-V1-FIX-T02
- 评审对象/任务编号：task-11（V1-04/V1-05 基础；对应 T-02/T-10 基础）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/design/scheduler-and-data.md` v1.0 §5（迁移契约/回滚保留原数据）、`docs/contracts/README.md` v1.0 §3（幂等）、`RR-V1-READINESS-20261112.md` V1-04/V1-05、`verification-rules-v1.0.md` §6（迁移/回滚/R20）
- 环境与 commit/变更集：Windows 10；Python 3.12.10；SQLAlchemy 2.0.25 / Alembic 1.13.1；git HEAD `fa70d3b` + 工作区（task-11 未提交）。变更：`app/models/__init__.py`(IdempotencyRecord)、`app/services/idempotency.py`(新)、`alembic/versions/002_idempotency.py`(新)、`app/database.py`(init_db 三态+DDL 指纹)、`alembic/versions/0817df993d8b_initial_schema.py`(downgrade 非空保护)、`scripts/verify_migrations.py`(强化)、`tests/unit/test_v1_migration.py`(新 9)、`tests/conftest.py`(会话级临时 DATABASE_URL，scope 经 Lead 授权 rev3)
- 证据路径：`docs/verification/tasks/T-02/result-addendum-V1-05.md`、`verify-migrations-v1-20261112.log`、`migration-summary-v1.json`、`real-db-drift-diagnostic-20261112.txt`、`tests/unit/test_v1_migration.py`；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t02-v1migration-reviewer.log`（9 passed）、`v1-fix-t02-fresh-init-repro-reviewer.log`

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | ① 新装空库 init_db 仅走 alembic upgrade、再次 upgrade 幂等、不再 create_all（审计 fresh-init 冲突消除） | 读 database.py init_db（空库→`alembic upgrade head`，无 create_all）；**独立在临时目录复现**：init_db×2 | 独立复现：init#1 → alembic 0817→002、version=002_idempotency、12 表含 idempotency_records；init#2 幂等（表/版本不变，无 `table exists`）；`IDEMPOTENT: True` | 通过 |
| 2 | ② 002 additive 可逆回滚：head→0817→head 数据保留（R20 回滚数据保留证据） | 读 002_idempotency.py（down 仅删该表）；test_v1_migration.py 用例；verify 日志 | 空库与规范化存量副本：head→downgrade 0817 仅删 idempotency_records，test_tasks/records 保持 10/98；再 upgrade head 数据仍保留；单测 9 passed | 通过 |
| 3 | ③ downgrade base 非空库保护实测被拒且数据不变 | 读 0817 downgrade `_assert_no_business_data`；单测/verify | 非空库 downgrade base exit=1「拒绝 downgrade base：表 users 仍有 N 行」，表/数据/版本不变；清空后允许；单测 test_downgrade_base_* | 通过 |
| 4 | ④ DDL 指纹比对与「stamp 0817→upgrade head」措辞/行为如实 | 读 _schema_fingerprint（逐表/列/索引/FK/唯一/CHECK/PK）、_init_db_sync 分支；addendum §2.1 偏差说明 | 无版本存量库：==head→stamp head；否则==初始 revision→stamp 0817→upgrade；两者都不一致→SchemaMismatchError（绝不静默 stamp）；**措辞偏差已如实标注**（stamp 初始 revision 比硬性 head 更安全可执行） | 通过（如实） |
| 5 | ⑤ 真实库漂移诊断与「生产明确失败拒绝 stamp」及运维 A/B 选项如实 | 读 real-db-drift-diagnostic + addendum §6.1 | 真实库与 head/初始 revision 均漂移（knowledge_entries server default/索引、test_tasks.plan/schedule_type）；生产 init_db 明确抛 SchemaMismatchError 拒绝 stamp（fail-closed）；源库 SHA-256 前后一致 `2f919b…`、`源库未被修改 True`；A/B 对账选项如实列出、未代实施 | 通过（如实；遗留见 P-V1T02-1） |
| 6 | ⑥ conftest 会话级临时 DATABASE_URL 是否影响其他测试隔离 | 读 conftest diff；独立跑 v1_migration/全套定向 | 导入 app 前 `setdefault(DATABASE_URL, 会话级临时 sqlite)`，lifespan→init_db 不触真实库；尊重外部显式 DATABASE_URL；test_db fixture 引擎替换逻辑未改；本评审 9 passed 与 17+ 其它集成均正常 | 通过（见 P-V1T02-2 低风险） |
| 7 | ⑦ WAL backup 派生 -wal/-shm 观察项 | 读 addendum §6.4 / verify | 只读 backup 生成空 `-wal`/`-shm`，源库主文件 SHA-256 与既有 sidecar 未变；已作为观察项如实记录，不伪造"无文件变化" | 通过（如实观察） |
| 8 | 74 项校验 | migration-summary-v1.json | `failed=0`，74/74 ok，1 条真实库漂移 observation（met=false，如实） | 通过 |
| 9 | 真实库未改 | 证据 | source_sha before==after `2f919b…` | 通过 |
| 10 | 未越界（红线） | git status | 未改 app/api、judgement/execution/task_executor、test-tools、frontend、docs/plan、真实库（只读）；conftest 变更经 Lead 授权 rev3 | 通过 |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T02-1 | **真实库结构漂移**：现有 `backend/test_platform.db` 与 head/初始 revision 均不一致，新 `init_db` 会明确失败拒绝启动（fail-closed 正确） | drift diagnostic；addendum §6.1 | **V1-05 上线阻塞**：真实库无法直接被新 init_db 启动；须用户选 A（规范化副本重建基线）或 B（显式 reconciling additive revision）对账后上线；本任务未改真实库 | 高（部署/用户决策） | 用户决策 + 后续运维/迁移任务 |
| P-V1T02-2 | conftest `setdefault(DATABASE_URL, 临时库)` 尊重外部显式 DATABASE_URL；若 CI/开发者已导出指向真实库的 DATABASE_URL，测试会使用之 | conftest diff | 隔离依赖"未显式导出真实 DATABASE_URL"；建议 CI 明确不注入真实库 URL | 低 | 记录性/CI 配置 |
| P-V1T02-3 | PostgreSQL 分支迁移/指纹未验证（仅 SQLite） | addendum §6.2 | 多库支持未核验 | 低 | 记录性 |
| P-V1T02-4 | Idempotency-Key 入口集成（201/幂等接线）归 task-12，尚未完成 | addendum §6.6 | V1-04 入口部分待 task-12 | 中（进行中） | task-12 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 真实库在线升级 | 属运维动作、真实库漂移需对账；本任务只读 | 真实库升级未执行/阻塞（P-V1T02-1） |
| L2 | PostgreSQL 迁移/备份 | 本机无 PG | 未验证 |
| L3 | 全量 378 passed 为自报 | 以 Lead 最终严格全量日志为准 | 本 RR 独立重跑 9 passed + fresh-init 复现；全量待补记 |

## 4. 待用户确认项

| # | 事项 | 建议 |
|---|---|---|
| U-V1T02-1 | 真实库漂移对账方案 A（规范化副本重建）/ B（显式 reconciling revision） | 请用户二选一并授权；完成前真实库不得用新 init_db 启动、严禁 downgrade base |

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/unit/test_v1_migration.py` | **9 passed** | 0 | `evidence/v1-fix-20261112/v1-fix-t02-v1migration-reviewer.log` |
| 独立 fresh-init 复现（临时库 init_db×2） | 新装 0817→002、version=002、12 表；二次幂等、无 table exists | 0 | `evidence/v1-fix-20261112/v1-fix-t02-fresh-init-repro-reviewer.log` |
| 开发证据：verify_migrations.py | 74/74 PASS | 0 | `docs/verification/tasks/T-02/verify-migrations-v1-20261112.log` + `migration-summary-v1.json` |
| 开发证据：全量 | 378 passed | 0 | `docs/verification/tasks/T-02/regression-full-v1-20261112.log` |
| 最终严格全量 | 待 Lead 最终日志，届时补记 | — | — |

## 6. 最终结论

**通过（V1-05 迁移闭环基础，R20 revision 级可逆回滚数据保留成立）；但真实库落地受阻，需用户对账（不改变本任务基础设施结论）。**

- ① 新装空库仅走 `alembic upgrade head`、再次 init 幂等、不再 create_all——审计 fresh-init `table exists` 冲突**已消除**（我独立临时库复现确认）。
- ② 002 additive revision 真实可逆：head→downgrade 0817 仅删 idempotency_records、历史表 test_tasks/records **10/98 数据保留**、再 upgrade head 恢复——**R20「回滚恢复原结构且保留原数据」在 revision 级成立**。
- ③ 非空库 `downgrade base` 被代码保护实测拒绝、数据不变（初始迁移 downgrade base 对非空库**受保护不可用**，属安全设计而非缺陷）。
- ④ DDL 指纹完整（逐表/列/索引/FK/唯一/CHECK/PK），stamp 仅在结构完全匹配 head 或初始 revision 时执行，否则明确失败；「stamp 初始 revision→upgrade head」偏差已如实标注。
- ⑤ 真实库漂移诊断如实、生产 `init_db` 明确拒绝 stamp（fail-closed）、源库 SHA-256 前后一致、A/B 对账选项如实列出未代实施。⑥ conftest 会话级临时 DATABASE_URL 隔离有效（尊重外部显式配置，低风险）。⑦ WAL backup 派生 -wal/-shm 观察项如实记录。

**R20 结论口径：通过（revision 级可逆回滚数据保留证据成立；初始迁移 downgrade base 对非空库受保护、不可用于非空库——合规）。** 遗留（记入 RR-V1-FINAL）：**真实库结构漂移 → 新 init_db 拒绝启动，需用户在方案 A/B 中对账后方可在真实库上线；真实库严禁 downgrade base。** Idempotency-Key 入口（V1-04）待 task-12。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、迁移演练日志、migration-summary-v1.json、漂移诊断与独立 fresh-init 复现作出，未替开发修改任何代码，未改真实库。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
