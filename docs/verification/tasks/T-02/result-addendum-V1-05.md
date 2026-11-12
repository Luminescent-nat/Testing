# T-02 增补（V1-05 / task-11）：幂等数据模型与迁移闭环基础 — 结果记录

- 任务编号：task-11（V1-04/V1-05 基础部分）
- 执行人：migration-idempotency（Agent Team）
- 日期：2026-11-12（Asia/Shanghai，UTC+08:00）
- 设计/契约依据：`docs/design/scheduler-and-data.md` 第 5 节、`docs/contracts/README.md` 第 3 节、`RR-V1-READINESS-20261112.md` V1-04/V1-05
- 关联原始审计复现：`docs/verification/reviews/evidence/v1-readiness-20261112/fresh-init-then-upgrade.log`、`idempotency-repro.log`
- 说明：本文件为**新增增补**，不修改 `result.md` / `result-addendum-RR-T02.md` 既有内容与结论（原 RR-T02「不通过」记录继续有效，本增补提交新的可逆回滚证据供复评）。

## 1. 变更文件

| 文件 | 变更 |
|---|---|
| `test-platform/backend/app/models/__init__.py` | 新增 `IdempotencyRecord`（user_id/operation/idempotency_key/request_sha256/response_json/task_id/created_at；`UNIQUE(user_id,operation,idempotency_key)` 命名约束 `uq_idempotency_user_op_key`；user_id→users、task_id→test_tasks 外键） |
| `test-platform/backend/app/services/idempotency.py`（新） | 幂等服务：`validate_idempotency_key`（8～128 可打印 ASCII）、`canonical_request_sha256`（sort_keys 规范化 JSON 摘要）、`claim_key`（先占键，IntegrityError 兜底并发）、`check_replay_or_conflict`（同键不同体冲突）、`complete_with_response`、`wait_for_response`、`run_idempotent` 编排（重放不重复执行；首次失败释放占键） |
| `test-platform/backend/alembic/versions/002_idempotency.py`（新） | additive revision `002_idempotency`（down_revision=`0817df993d8b`）：仅创建 `idempotency_records` 表（含 3 个索引、命名唯一约束、两个外键）；`downgrade` 只删该表，历史表数据保留 |
| `test-platform/backend/app/database.py` | 新增结构指纹与启动迁移：`_schema_fingerprint`（逐表/列/索引/FK/唯一/CHECK/PK）、`_reference_fingerprint`（app.models 内存建库基准）、`_revision_fingerprint`（隔离库 upgrade 到指定 revision 取基准）、`_fingerprint_diffs`、`SchemaMismatchError`；`init_db` 改为三态：空库→`alembic upgrade head`；有表无版本→全 DDL 指纹比对一致才 stamp（head 或初始 revision）否则明确失败；有版本→`upgrade head`；末尾核验结构==app.models |
| `test-platform/backend/alembic/versions/0817df993d8b_initial_schema.py` | `downgrade()` 增加 `_assert_no_business_data()` 非空库保护：users/test_tasks/test_records 任一有数据即 raise，禁止 `downgrade base` 静默删数据（历史 upgrade 语义未改） |
| `test-platform/backend/scripts/verify_migrations.py` | 强化：逐表/列/索引/FK/唯一/CHECK DDL 指纹对比；sqlite3 backup API 的 WAL 一致性备份（只读源）；head→002→downgrade 0817（数据保留）→再 upgrade 演练；非空库 downgrade base 拒绝；非法外键/重复唯一键拒绝；`idempotency_records` 三元组唯一与非法 task 外键探测；真实库漂移「同表名不同 DDL」反例 |
| `test-platform/backend/tests/unit/test_v1_migration.py`（新） | 9 个用例：新装 upgrade+结构一致+再次幂等、唯一约束由 DB 拒绝、存量 create_all 库 stamp 保存数据、存量初始 revision 库 stamp 初始再升级、同表名不同 DDL 明确失败不 stamp、revision 回滚数据保留、downgrade base 非空保护、空库 downgrade base 允许 |
| `test-platform/backend/tests/conftest.py` | **scope 经 Lead 授权扩充（task-11 write scope rev3）**：导入 app 前 `os.environ.setdefault("DATABASE_URL", 会话级临时 sqlite)`（2 行+注释，含 session 结束清理），确保 `TestClient(app)` 触发 lifespan→init_db 时不触碰真实 `backend/test_platform.db`；test_db fixture 引擎替换逻辑未改 |
| `docs/verification/tasks/T-02/*` | 本增补与全部原始日志/JSON/漂移诊断 |

未触碰（红线）：`app/api/*`、`judgement_engine.py` / `execution_engine.py` / `task_executor.py`、`test-tools/`、`frontend/`、`docs/plan`、真实 `backend/test_platform.db`（只读）。

## 2. 关键实现说明

### 2.1 启动迁移三态（`app/database.py::init_db`）
- 空库（无业务表）：只执行 `alembic upgrade head`，**不再 create_all**；升级后核验结构==app.models。
- 有业务表但无 `alembic_version`（历史 create_all 存量库）：
  1. 先取当前库完整 DDL 指纹，与 head（app.models）基准比对；
  2. 完全一致 → `stamp head` → `upgrade head`；
  3. 否则与初始 revision `0817df993d8b` 基准比对；完全一致（典型：引入幂等表之前的存量库）→ `stamp 0817df993d8b` → `upgrade head` 补齐 002；
  4. 两者都不一致 → 抛 `SchemaMismatchError` 明确失败，**绝不静默 stamp**。
- 有 `alembic_version`：`alembic upgrade head`（已在 head 为幂等 no-op）。
- 全部路径结束后（SQLite）核验结构==app.models，不一致即失败。
- 测试 conftest 的 create_all 不受影响（每用例独立引擎，不调用 init_db）。

> 与设计「stamp head」措辞的偏差说明：「有表无版本」的存量库若对应初始 revision 结构（缺 002 幂等表），不可能等于 head；硬性要求 ==head 会使这类库永远无法安全登记。因此实现按「与哪个 revision 结构完全一致就 stamp 哪个 revision，再 upgrade head」处理，并保留「不一致明确失败」。这是比「仅 head」更安全的可执行策略，特此如实标注。

### 2.2 非空库 downgrade base 保护
`0817df993d8b.downgrade()` 开始时检查 `sqlite_master` 中 users/test_tasks/test_records，任一表存在且 `count(*)>0` 即抛 `RuntimeError: 拒绝 downgrade base：表 X 仍有 N 行数据…`，回滚在真正删表前终止；数据、表结构、alembic_version 均保持不变（见 verify 日志 `*-protection-keeps-data/keeps-tables`）。

### 2.3 DDL 指纹定义
逐表：列名/类型（SQLite 方言编译串）/nullable/server default；PK 列；索引（名/列/unique）；外键（约束列→被引用表/列）；唯一约束（名/列）；CHECK（名/表达式）。排除 `alembic_version`。参考基准由 app.models 在内存 SQLite `create_all` 生成，或由隔离库 `alembic upgrade <revision>` 生成。可检测「同表名不同 DDL」：新增列（`rogue_col`）、类型/默认值/索引差异均被识别。

### 2.4 WAL 一致性备份
`sqlite_wal_consistent_backup` 以只读 URI（`mode=ro`）打开源库，用 `sqlite3.Connection.backup` 生成快照（覆盖 WAL 中已提交数据），核对 integrity_check、foreign_key_check、关键表行数（source=backup=10/98）、快照 SHA-256；源库主文件 SHA-256 演练前后一致。

## 3. 环境与命令/退出码（原始日志见第 4 节）

- OS：Windows 10（主机 MCTECH，Asia/Shanghai）；Python 3.12.10（`D:\MCTEST\test-platform\.venv\Scripts\python.exe`）
- SQLAlchemy 2.0.25 / Alembic 1.13.1 / pytest 7.4.4 / pytest-asyncio 0.23.3 / SQLite
- 源库基线：`backend/test_platform.db` size=1060864，SHA-256=`2f919b0544e37618628ac358f1b5684ee16c9253596483b62919166a91b1a789`；11 张业务表（无 alembic_version），test_tasks=10、test_records=98（只读探测）

| # | 命令（WORKDIR=backend） | 退出码 | 结果 |
|---|---|---:|---|
| 1 | `python scripts/verify_migrations.py --report docs/verification/tasks/T-02/migration-summary-v1.json` | 0 | **74/74 checks PASS**；1 条真实库漂移观察（不伪造通过） |
| 2 | `python -m pytest tests/unit/test_v1_migration.py -v` | 0 | **9 passed** |
| 3 | `python -m pytest tests -q`（全量回归） | 0 | **378 passed in 156.62s**（0 failed；含 websocket 3 项在 conftest 隔离后通过） |
| 4 | `python <temp>\drift_diag.py`（只读漂移诊断） | 0（stderr 仅 alembic INFO） | 生成 `real-db-drift-diagnostic-20261112.txt`，`SOURCE_UNCHANGED True` |

## 4. 原始日志与产物

- `docs/verification/tasks/T-02/verify-migrations-v1-20261112.log`（UTF-8，949 行）— 完整演练：每条 alembic 命令 exit/stdout/stderr、离线 `--sql`、空库/规范化存量副本各阶段表清单/行数/integrity_check、revision 回滚、downgrade base 保护、约束探测、DDL 指纹、源库前后 SHA-256、74 项汇总
- `docs/verification/tasks/T-02/migration-summary-v1.json`（UTF-8）— 机器可读汇总（checks/known_limitations/empty/legacy 全量状态）
- `docs/verification/tasks/T-02/pytest-v1-migration-20261112.log`（UTF-8）— 9 用例明细
- `docs/verification/tasks/T-02/regression-full-v1-20261112.log`（UTF-8）— 全量回归 378 passed
- `docs/verification/tasks/T-02/real-db-drift-diagnostic-20261112.txt`（UTF-8，只读）— 真实库漂移明细（与 head、与初始 revision 两组差异）、行数、源库 SHA-256 前后一致

演练关键结论（详见日志）：
- 空库：`upgrade head` → 12 表（含 idempotency_records）、version=002_idempotency、integrity ok、FK 0 违规、DDL 指纹==models；再次 `upgrade head` 幂等（版本/表集不变）；离线 SQL 生成全部 `CREATE TABLE`。
- revision 回滚（空库与规范化存量副本两个库都做）：head→`downgrade 0817df993d8b` 仅删 idempotency_records，test_tasks/test_records 保持 1/1 与真实 10/98 不变；再 `upgrade head` 表恢复、数据仍保留。
- 非空库 `downgrade base`：exit=1 且报「拒绝 downgrade base：表 users 仍有 N 行数据」，数据/表/版本不变；清空后 `downgrade base` exit=0，再 `upgrade head` 恢复 12 表。
- 约束：users.username、devices.serial_number、idempotency_records(user_id,operation,idempotency_key) 重复均被数据库拒绝；合法外键成功、非法外键（devices.owner_id=999999、idempotency_records.task_id=999999）被拒绝。
- 真实库漂移反例：备份副本 DDL 指纹与初始 revision/head 均不一致 → 生产 `init_db`（`_init_db_sync`）**明确抛 SchemaMismatchError 拒绝 stamp**（`legacy-source:init-db-refuses-drifted-schema` PASS）。

## 5. DoD 逐条

| 要求 | 状态 | 证据 |
|---|---|---|
| 新增 IdempotencyRecord + 唯一约束 + 外键 | ✅ | models；`empty/legacy:idempotency_duplicate_key_rejected`、`idempotency_illegal_task_fk_rejected`；单测 `test_idempotency_records_unique_constraint_enforced_by_db` |
| 新增 app/services/idempotency.py | ✅ | 服务文件；临时冒烟：REPLAY calls=1、CONFLICT_OK、KEY_VALIDATION_OK、sha 规范化稳定 |
| alembic 002 additive、downgrade 只删该表、历史数据保留 | ✅ | 002 文件；`revision-downgrade-*`、`revision-reupgrade-*`（1/1、10/98 保留） |
| 空库 alembic upgrade 成功且与 models 逐列一致 | ✅ | `empty:ddl-fingerprint-ok`；单测 `test_fresh_install_...`、`test_upgrade_head_is_idempotent...` |
| 存量库 stamp 前完整 DDL 指纹比对、不一致明确失败 | ✅ | `legacy/pre-initial:ddl-fingerprint-ok`、`legacy-source:init-db-refuses-drifted-schema`；单测 `test_legacy_*`、`test_legacy_mismatched_schema_is_refused_without_stamp` |
| 初始迁移 downgrade 非空库保护 | ✅ | `empty/legacy:downgrade-base-protection-*`；单测 `test_downgrade_base_*` |
| verify_migrations.py 强化（指纹/WAL 备份/revision 回滚/非法 FK/重复唯一键） | ✅ | 74/74 PASS 日志与 JSON |
| tests/unit/test_v1_migration.py 覆盖四类 | ✅ | 9 passed |
| 不得修改真实库 | ✅ | 源库 SHA-256 前后一致（2f919b…），漂移诊断 `SOURCE_UNCHANGED True` |

## 6. 遗留、偏差与「无法核验」项（如实上报，不伪造通过）

1. **【V1-05 上线阻塞 / 真实库无法直接被新 init_db 启动】** 真实 `backend/test_platform.db` 由更早版本 create_all 建立，与初始 revision 及当前 models 存在结构漂移（明细见 `real-db-drift-diagnostic-20261112.txt`）：
   - `knowledge_entries`：`entry_type/source_type/status/pass_count/fail_count/hit_count` 带 server default（`'document'/'manual'/'draft'/0`），当前迁移/模型无该 server default；
   - `knowledge_entries`：多出索引 `ix_knowledge_entries_category / _entry_type / _status`（模型仅有 `ix_knowledge_entries_id`）；
   - `test_tasks.plan`：DB 为 `TEXT`，模型为 `JSON`（SQLite 亲和均 TEXT，但 DDL 指纹不同）；
   - `test_tasks.schedule_type`：DB 带 server default `'immediate'`，模型为客户端默认。
   
   因此对现有真实库，生产 `init_db` 会**明确失败、拒绝 stamp**（符合 V1-05「不一致必须明确失败、不得静默 stamp」）。本任务**未修改真实库、未对其执行任何迁移**。上线前须由用户在以下两种运维对账方案中**二选一**（本任务不代为决定、不实施）：
   - **方案 A**：以初始 revision 规范化结构 + 真实数据副本重建基线（先用 `build_normalized_legacy_copy` 思路产出结构=0817、数据=真实的副本，核对行数/约束后由运维切换；真实库严禁 `downgrade base`）；
   - **方案 B**：新增一个**显式 reconciling additive revision**（把上述 server default/索引/类型差异以 additive DDL 对齐），经人工确认后在受控环境对副本演练通过再上线；须保留变更记录与回退。
   
   在该对账完成并经用户确认前，「现有真实库无法被新 init_db 直接启动」列为 V1-05 遗留/上线阻塞项，不标记通过。
2. **PostgreSQL 分支未验证**：DDL 指纹与结构核验仅覆盖 SQLite（`_verify_schema_matches_models` 对非 SQLite 跳过）；`postgresql+asyncpg` 的迁移/外键/备份未演练（本机无 PG）。
3. **真实库在线迁移未执行且不应执行**：仅在只读备份与规范化副本上演练；真实库升级属运维动作。
4. **只读 backup 会物化 sidecar**：SQLite backup API 以只读打开 WAL 库时会生成空的 `-wal`（0 字节）与 `-shm`（32KB 派生）文件；源库**主文件 SHA-256 未变、既有 sidecar 未变**，已作为观察项（非数据变更）记录，不伪造「无任何文件变化」。
5. **`stamp head` 措辞偏差**：见 2.1，对「初始 revision 结构」的存量库采用 `stamp 0817df993d8b` 再 upgrade head（更安全可执行），已如实标注。
6. **Idempotency-Key 入口集成（task-12）未在本任务完成**：本任务只交付数据模型、迁移与服务层；`app/api/tasks.py` 的 201/幂等接线按计划在 task-12（等 task-9 授权版 tasks.py 完成后）进行。

## 7. 回退说明

1. 删除 `alembic/versions/002_idempotency.py`、`app/services/idempotency.py`、`tests/unit/test_v1_migration.py`、本增补及新增证据文件。
2. `app/models/__init__.py`：删除 `IdempotencyRecord` 与 `UniqueConstraint` 导入改动。
3. `app/database.py`：恢复 `init_db` 为原 create_all 版本并删除新增指纹/迁移辅助函数。
4. `alembic/versions/0817df993d8b_initial_schema.py`：删除 `_assert_no_business_data()` 及调用。
5. `scripts/verify_migrations.py`、`tests/conftest.py`：按 git 差异回退。
6. 真实库未改动（SHA-256 应仍为 `2f919b0544e37618628ac358f1b5684ee16c9253596483b62919166a91b1a789`）。
