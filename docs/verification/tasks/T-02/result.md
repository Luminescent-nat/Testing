# T-02 Alembic 与 SQLite 外键迁移基础 — 结果记录

- 任务编号：T-02（共享任务板 task-3，owner=infra-tools）
- 执行人：infra-tools（Agent Team）
- 日期：2026-11-12（Asia/Shanghai，UTC+08:00）
- 设计依据：`docs/design/scheduler-and-data.md` 第 5 节「迁移契约」

## 1. 变更文件

| 文件 | 变更 |
|---|---|
| `test-platform/backend/app/database.py` | 新增可复用 helper `configure_sqlite_connection(dbapi_connection, connection_record=None)`：每连接执行 `PRAGMA foreign_keys=ON`、`PRAGMA journal_mode=WAL`、`PRAGMA busy_timeout=30000`（保留原有 WAL/busy_timeout）；运行时异步引擎 connect 事件改为直接注册该 helper（可用 `event.contains()` 核对注册关系） |
| `test-platform/backend/alembic/env.py` | 迁移连接（alembic 在线模式）同样注册 `configure_sqlite_connection`；注释说明本迁移 batch 操作仅含索引、不触发影子表重建，未来需重建被引用表的 batch 迁移必须按 SQLite 要求在事务外管理外键（设计第 5 节） |
| `test-platform/backend/scripts/verify_migrations.py` | 新增：tempfile 隔离目录演练脚本（空库 + 存量库备份副本），输出 alembic version、表清单、tasks/records 行数、integrity_check、唯一键/非法外键失败证据，源库 SHA-256 前后一致校验 |
| `test-platform/backend/tests/unit/test_migration_contract.py` | 新增 6 个契约测试（先红后绿）：PRAGMA helper 生效、生产引擎注册关系、每连接生效、唯一约束、非法外键拒绝、裸 SQLite FK=OFF 对照缺陷证据 |
| `docs/verification/tasks/T-02/*` | 本记录与全部原始日志/JSON |

未触碰：`app/main.py`、`app/config.py`、`app/services/judgement_engine.py`、`frontend/`、`backend/test_platform.db`、`alembic/versions/*`（迁移脚本本身未改动）。

## 2. 环境

- OS：Windows 10（主机 MCTECH，Asia/Shanghai）
- Python：3.12.10（`D:\MCTEST\test-platform\.venv\Scripts\python.exe`）
- SQLAlchemy 2.0.25 / Alembic 1.13.1 / pytest 7.4.4 / pytest-asyncio 0.23.3
- 数据库：SQLite（默认 `backend/test_platform.db`，**只读**）
- 源库基线：size=1060864，SHA-256=`2f919b0544e37618628ac358f1b5684ee16c9253596483b62919166a91b1a789`；
  只读探测：11 张业务表（无 `alembic_version`，即 create_all 建立的存量库）、test_tasks=10 行、test_records=98 行
- 演练全部发生在 `%TEMP%\t02_migrations_*` 隔离目录

## 3. 命令、起止时间与退出码（原始日志见第 4 节）

| # | 命令（WORKDIR） | 起 | 止 | 退出码 | 结果 |
|---|---|---|---|---|---|
| 1 | `python -m pytest tests/unit/test_migration_contract.py -q`（backend，实现前红测） | 11:48:18 | 11:48:19 | 1 | 3 failed + 2 errors（helper 不存在）+ 1 passed（FK=OFF 对照缺陷证据） |
| 2 | `python scripts/verify_migrations.py --report docs/verification/tasks/T-02/migration-summary.json`（backend） | 11:51:30 | 11:51:35 | 1 | 首跑：37/38，仅 `legacy:rollback-preserves-original-data` 不满足（真实发现）；另发现 pragma 助手导入 URL 与日志编码两处脚本缺陷，修复后重跑 |
| 3 | `python scripts/verify_migrations.py --report docs/verification/tasks/T-02/migration-summary.json`（backend，终版） | 11:53:15 | 11:53:20 | 0 | **37/37 PASS**；已知缺陷单列于「已知缺陷/观察」不伪造通过 |
| 4 | `python -m pytest tests/unit/test_migration_contract.py -q`（backend，实现后绿测） | 11:57:20 | 11:57:21 | 0 | 6 passed |
| 5 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`（backend，全量回归） | 11:57:37 | 11:59:42 | 0 | **236 passed**（基线 189，含各队友新增测试；0 failed，无删除/跳过/放宽） |

## 4. 原始日志与产物

- `docs/verification/tasks/T-02/pytest-T02-red-20261112.log` — 实现前红测（完整 pytest 输出）
- `docs/verification/tasks/T-02/verify-migrations-20261112.log` — 迁移演练完整原始输出（含每条 alembic 命令、exit、stdout/stderr、离线 `--sql` 全量脚本、每阶段表清单/行数/integrity_check、约束探测、源库前后 SHA-256、37 项校验汇总）
- `docs/verification/tasks/T-02/migration-summary.json` — 机器可读汇总（checks/known_limitations/empty/legacy 全量状态）
- `docs/verification/tasks/T-02/pytest-T02-green-20261112.log` — 实现后绿测
- `docs/verification/tasks/T-02/regression-full-20261112.log` — 全量回归（236 passed）

演练关键原始结论（详见日志）：
- 空库：`alembic upgrade head` → 11 表、alembic_version=0817df993d8b、integrity_check=ok、foreign_key_check 空；`upgrade head --sql` 生成 11 张 `CREATE TABLE`；`downgrade base` → 0 表；再次 `upgrade head` → 恢复 11 表且 integrity_check=ok；`alembic current` = `0817df993d8b (head)`。
- 存量库备份副本（源库只读复制，copy_sha256 与源一致）：升级前 11 表（结构与 head 一致独立核对通过）、test_tasks=10 / test_records=98；`--sql` 核对通过；`stamp head`（仅因结构与 head 完全一致，副本上执行，非新装默认）→ `upgrade head`（无变更，行数仍 10/98）→ `downgrade base` → 再次 `upgrade head` → 结构恢复、integrity_check=ok、行数 0/0。
- 约束探测（两个库均执行，使用 `app.database.configure_sqlite_connection`，`PRAGMA foreign_keys=1`）：
  `UNIQUE constraint failed: users.username`、`UNIQUE constraint failed: devices.serial_number`、合法外键写入成功、`FOREIGN KEY constraint failed`（owner_id=999999）→ 全部由数据库实际拒绝。
- 源库保护：前后 SHA-256 完全一致（含 `-wal`/`-shm` sidecar 哈希一致），从未向 alembic 传入真实库路径（脚本内置安全断言）。

## 5. DoD 逐条

| DoD | 状态 | 证据 |
|---|---|---|
| 新装空库 `alembic upgrade head` | ✅ | 日志 `empty/upgrade` exit=0，11 表 + version 0817df993d8b |
| 存量库备份副本演练（只对备份副本） | ✅ | `legacy/*` 段；copy 在 tempfile，源库只读复制 |
| downgrade 回滚演练 | ✅ | `empty/downgrade-base`、`legacy/downgrade-base` 均 exit=0，表清单清空后再次 upgrade 恢复 |
| SQLite 每连接 `PRAGMA foreign_keys=ON`，保留 WAL/busy_timeout | ✅ | `app/database.py` helper；单测 `test_configure_sqlite_connection_...`、`test_pragma_is_applied_on_every_new_connection`；脚本 `foreign_keys_pragma_on (got=1)` |
| 唯一约束实际生效（users.username、devices.serial_number） | ✅ | 单测 + 脚本 `duplicate_*_rejected`，数据库报 UNIQUE constraint failed |
| 非法外键写入必须失败 | ✅ | 单测 + 脚本 `illegal_foreign_key_rejected`，数据库报 FOREIGN KEY constraint failed |
| `scripts/verify_migrations.py`（隔离临时副本、输出 head/表清单/行数/integrity_check/约束失败证据） | ✅ | 新增脚本 + `verify-migrations-20261112.log` + `migration-summary.json` |
| `tests/unit/test_migration_contract.py` 新增 | ✅ | 6 用例，先红后绿 |
| 不得修改真实库；只在备份副本/临时目录演练 | ✅ | 源库 SHA-256/sidecar 前后一致；脚本内含拒绝真实库路径的安全断言 |
| 证据目录 `docs/verification/tasks/T-02/` | ✅ | 本目录 |
| 禁止改 app/main.py、config.py、judgement_engine.py、frontend | ✅ 未改 | 见第 1 节 |

## 6. 未验证项与已知缺陷（如实记录，不伪造通过）

1. **回滚保留原数据：不满足（已知缺陷）**。初始迁移 `0817df993d8b` 的 `downgrade()` 直接删表，存量副本回滚演练后 test_tasks/records 由 10/98 变 0/0。设计第 5 节「回滚恢复原结构且保留原数据」对初始迁移尚不满足。已作为 `legacy:rollback-preserves-original-data (KNOWN DEFECT, NOT A GATE)` 记录在脚本「已知缺陷/观察」段与 `migration-summary.json` 的 `known_limitations`。建议后续以新迁移引入「回滚前归档表/导出」或修订 downgrade 语义，不在 T-02 范围内擅自改迁移历史。
2. `alembic stamp head` 仅按设计第 5 节在「独立核对结构与 head 完全一致」后的副本上演练；真实库的 stamp/升级属运维动作，本次未对真实库执行（不验证）。
3. PostgreSQL 分支（`postgresql+asyncpg`）的迁移与外键行为未验证（本任务只覆盖 SQLite；helper 只挂在 sqlite 连接事件上）。
4. 真实库在线升级（对 `backend/test_platform.db` 执行 upgrade）未执行也不应执行；存量升级只在副本上验证通过。
5. 迁移连接的外键策略：当前 alembic 在线连接与应用一致 `foreign_keys=ON`，本次迁移全部步骤（含删表顺序 child-first）在 FK=ON 下通过；但未来含影子表重建的 batch 迁移需按 SQLite 要求在事务外管理外键（已在 env.py 注释标注，尚无此类迁移可验证）。

## 7. 回退说明

回退 T-02 全部改动（无数据迁移、无真实库变更，可安全回退）：

1. `test-platform/backend/app/database.py`：删除 `configure_sqlite_connection` 与 `event.listen(engine.sync_engine, "connect", ...)` 注册块，恢复原 `_set_sqlite_pragma`（WAL/busy_timeout 两条 PRAGMA）监听器。
2. `test-platform/backend/alembic/env.py`：删除 `event` 导入与 `run_migrations_online()` 中 sqlite 分支的 `event.listen(...)` 块。
3. 删除 `test-platform/backend/scripts/verify_migrations.py`、`test-platform/backend/tests/unit/test_migration_contract.py`、`docs/verification/tasks/T-02/`。
4. 回退后运行 `python -m pytest tests -q`（应恢复 189+ 其他任务用例），并确认 `backend/test_platform.db` SHA-256 仍为
   `2f919b0544e37618628ac358f1b5684ee16c9253596483b62919166a91b1a789`（本次未改动真实库）。

---

## 8. 评审不通过（RR-T02）— 2026-11-12 追加（详见增补记录，本节仅为指针）

独立评审 RR-T02 判定本任务 **不通过（DoD 第 2 条 / R20 回滚数据保留项）**：初始迁移
`downgrade base` 删表使存量副本 10/98 → 0/0，备份恢复不能替代 alembic 数据保留回滚证据；
真实库严禁 `downgrade base`；R20 维持不通过，task-3 已 reopen 保持 in_progress，不再标
complete。全部说明、合规回滚路径演练（运维层）、补做路径与新增的「干净空库 FK 崩溃」
发现/修复见增补记录：`docs/verification/tasks/T-02/result-addendum-RR-T02.md`（新文件，
本文件原有内容与结论未改动，`migration-summary.json` 保持如实）。

---

## 9. V1-05 / task-11 增补 — 2026-11-12（指针，本节不改变上文结论）

task-11（migration-idempotency）在初始迁移与 models 对齐的基础上新增 additive revision
`002_idempotency`、幂等数据模型/服务、启动迁移三态（空库 upgrade head / 无版本先完整 DDL
指纹比对再 stamp / 有版本 upgrade）、初始迁移 `downgrade base` 非空库保护、强化
`verify_migrations.py`（DDL 指纹/WAL 一致性备份/revision 级回滚数据保留/downgrade base 保护/
非法 FK 与重复唯一键）与 `tests/unit/test_v1_migration.py`。规范化存量副本上的 revision 级
回滚演练（head→downgrade 0817 仅删幂等表、test_tasks/test_records 10/98 保留→再 upgrade）
为 R20「回滚恢复原结构且保留原数据」补交新证据，供独立复评。

真实存量库 `backend/test_platform.db` 存在结构漂移，生产新 `init_db` 会明确失败、拒绝
stamp（符合 V1-05），**未修改真实库**；上线前运维对账方案 A/B 待用户选择。详见增补记录：
`docs/verification/tasks/T-02/result-addendum-V1-05.md`，原始日志
`verify-migrations-v1-20261112.log`、`migration-summary-v1.json`、
`pytest-v1-migration-20261112.log`、`regression-full-v1-20261112.log`、
`real-db-drift-diagnostic-20261112.txt`。本文件既有 §1～§8 内容与「不通过」结论未改动。
