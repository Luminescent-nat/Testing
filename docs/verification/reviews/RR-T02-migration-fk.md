# RR-T02：Alembic 与外键迁移基础

- 评审编号：RR-T02
- 评审对象/任务编号：T-02（共享任务板 task-3，owner infra-tools）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/design/scheduler-and-data.md` v1.0 §5（迁移契约）、`docs/verification/verification-rules-v1.0.md` v1.0 §6（迁移：新装/存量、回滚必须恢复原结构且保留原数据；"没有实际回滚日志则 R20 不通过"）、`docs/plan/task-board-v1.0.md` T-02 DoD
- 环境与 commit/变更集：Windows 10，Python 3.12.10，SQLAlchemy 2.0.25 / Alembic 1.13.1 / pytest 7.4.4；git HEAD `d0b415d` + 工作区未提交变更。T-02 变更：`app/database.py`、`alembic/env.py`、新增 `scripts/verify_migrations.py`、新增 `tests/unit/test_migration_contract.py`；未改 `alembic/versions/*`、`main.py`、真实库
- 证据路径：
  - 开发证据：`docs/verification/tasks/T-02/`（result.md、verify-migrations-20261112.log、migration-summary.json、pytest-T02-red/green-20261112.log、regression-full-20261112.log）
  - 评审方独立重跑：`docs/verification/reviews/evidence/test-rerun-20261112/backend-targeted-t01-t02-t19-reviewer.log`

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 只改声明 scope，未碰真实库/迁移脚本 | `git diff`、git status | 仅 database.py/env.py/verify_migrations.py/test_migration_contract.py；`alembic/versions/*` 未改；真实库只读 | 通过 |
| 2 | SQLite 每连接 PRAGMA foreign_keys=ON，保留 WAL/busy_timeout | 读 database.py `configure_sqlite_connection`；单测 | helper 三 PRAGMA；运行时引擎与 alembic 迁移连接均注册 | 通过 |
| 3 | 新装空库 upgrade head 到同一 head | verify 日志 empty 段 | 11 表 + alembic_version 0817df993d8b + integrity ok | 通过 |
| 4 | 存量备份副本演练（只对副本） | verify 日志 legacy 段；脚本安全断言 | tempfile 隔离目录；源库 SHA-256 前后一致 `2f919b05…1a789`；复制体 copy_sha256 一致 | 通过（真实库未动） |
| 5 | 唯一约束实际生效 | 单测 + 脚本 | users.username、devices.serial_number UNIQUE constraint failed | 通过 |
| 6 | 非法外键写入必须失败 | 单测 + 脚本 | FOREIGN KEY constraint failed | 通过 |
| 7 | 37 项校验 | migration-summary.json | `failed=0`，37/37 ok | 通过 |
| 8 | **回滚恢复原结构且保留原数据（DoD 第2条 / R20）** | verify 日志 legacy downgrade；migration-summary `legacy.data_preserved_on_rollback` | 初始迁移 `downgrade()` 直接删表：存量副本回滚后 test_tasks/test_records 由 10/98 → 0/0（after_reupgrade 0/0），结构恢复但**数据丢失** | **不通过（见 P-T02-1）** |
| 9 | 独立重跑 T-02 定向 | pytest test_migration_contract.py（并入 87 passed 定向跑） | 6 passed | 通过 |
| 10 | 全量回归证据 | T-02/regression-full-20261112.log；评审方独立严格全量 | 236 passed（11:57 时间点）；评审方独立 `pytest tests` **310 passed**（12:25） | 通过 |
| 11 | 增补：真实库严禁 downgrade base 边界 | 读 `result-addendum-RR-T02.md` §1；verify_migrations.py 安全断言:398-400 | 明确禁止真实/存量库 downgrade base，仅隔离副本演练；源库 SHA256 前后一致 | 通过 |
| 12 | 增补：备份副本 SHA-256 + 从备份恢复演练（运维路径，非 alembic 证据） | 读 `restore_drill.py` + `restore-drill-20261112.log` | **9/9 PASS**，日志明确"不能替代 alembic 数据保留回滚证据（R20 另行判定）" | 通过（仅运维恢复，不改 R20） |
| 13 | 增补：干净空库首次启动 FK 崩溃修复 | 读 seed_data.py diff（`user_id = user.id if user else None`）；独立跑回归用例 | 修复真实；`test_clean_empty_db_startup_seeding_survives_foreign_keys_on` 独立跑 **1 passed**；T-18 矩阵 fresh-empty-db /health=200 | 通过（修复） |
| 14 | 原 result.md/migration-summary.json 是否被覆盖伪造 | 读目录时间与内容 | 原 result.md 仅追加"评审不通过"指针章节；migration-summary.json known_limitations 仍如实 met=false；未伪造通过 | 通过（如实） |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-T02-1 | **DoD 第2条+R20「回滚恢复原结构且保留原数据」不成立**：初始迁移 `0817df993d8b` 的 `downgrade()` 直接 drop 表，存量备份副本 downgrade base 后 10/98 行 → 0/0，历史数据在回滚时被删除 | `docs/verification/tasks/T-02/migration-summary.json` `legacy.before={10,98}` / `after_downgrade` / `after_reupgrade={0,0}`、`known_limitations[0] met=false`；design §5「回滚恢复原结构且保留原数据」；verification §6「执行回滚后恢复原结构和数据」 | R20 数据保留项不通过；taskboard T-02 DoD 第2条未满足；task-3 标 completed 站不住 | **高** | T-02 / 需 reopen task-3 或正式修订 DoD |
| P-T02-2 | 「从备份恢复」路径不能替代 alembic 回滚证据：备份副本可重新从源库复制恢复数据，但这不是 `alembic downgrade` 路径的数据保留能力，不能作为"回滚保留数据"的合规证据 | verify_migrations.py 逻辑（复制源库→演练）；design §5 区分"回滚"与"备份恢复" | 若用"备份副本可恢复"充当回滚证据即属伪造 R20 通过 | 高 | 记录性/评审判定 |
| P-T02-3 | 初始迁移数据保留可能在本轮不可达（首个迁移必然建/删全部表），需后续迁移设计"回滚前归档表/导出"或修订 downgrade 语义；不应擅改迁移历史 | result.md §6.1 | 修复路径需产品/架构决策，非纯实现 | 中 | 架构/后续任务 |
| P-T02-4 | **（T-02 引入的可靠性回归，已修复）** foreign_keys=ON 后 `seed_data.py` 空库无用户时用虚构 `created_by=1` → 干净空库首次启动 `FOREIGN KEY constraint failed` 崩溃（影响 Docker 空数据卷部署） | T-02 增补 §5；seed_data.py diff；test_clean_empty_db_startup_seeding_survives_foreign_keys_on | 修复前干净空库首次启动崩溃；已改 `created_by=None`（列 nullable）+ 回归测试；T-18 矩阵 fresh-empty-db /health=200 证实修复 | 高（已修复） | T-02（rev6）/已修复并回归 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | PostgreSQL 分支迁移与外键 | 仅覆盖 SQLite | 多库支持未验证 |
| L2 | 独立全量回归当前 2 failed（test_judgement_engine） | T-06 并行编辑 judgement_engine 等文件，与 T-02 无关；T-02 定向 6 passed；T-02 证据全量 236 passed 为 11:57 时间点 | 最终全量由 Lead 在 T-06 完成后统一重跑 |
| L3 | **真实库禁止执行 `alembic downgrade base`** | downgrade base 会删表丢数据 | 任何对 `backend/test_platform.db`（唯一业务库）执行 downgrade base 将造成不可恢复数据丢失；只能在临时副本演练 |

## 4. 待用户确认项 / 处置建议

| # | 事项 | 建议 |
|---|---|---|
| U-T02-1 | T-02 DoD 与 R20 处置 | 建议 **reopen task-3**：将 DoD 第2条/R20「回滚保留数据」明确为未满足；或由用户/架构正式修订：初始迁移允许结构级回滚、数据保留靠"备份恢复 SOP"并据此修订 design §5 措辞（须留变更记录）。在裁决前 R20 = 不通过 |
| U-T02-2 | 数据保留实现路径 | 后续迁移引入回滚前归档表/导出，或拆分首个迁移；不在 T-02 内擅改迁移历史 |

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/unit/test_migration_contract.py`（并入定向跑） | 6 passed | 0 | `evidence/test-rerun-20261112/backend-targeted-t01-t02-t19-reviewer.log` |
| `pytest tests/unit/test_migration_contract.py::test_clean_empty_db_startup_seeding_survives_foreign_keys_on`（增补修复后独立单跑） | **1 passed** | 0 | `evidence/test-rerun-20261112/t02-seedfix-single-reviewer.log` |
| 严格全量 `pytest tests -q -W error::...`（增补+seed 修复后，评审方独立） | **310 passed / 0 failed** | 0 | `evidence/test-rerun-20261112/backend-final-full-regression-reviewer.log` |
| Lead 最终全量日志 | 310 passed（135.09s） | 0 | `docs/verification/tasks/FULL-REGRESSION-final-20261112.log` |
| 证据对照 verify_migrations.py / restore_drill.py | 37/37 ok；restore 9/9 PASS | 0 | `docs/verification/tasks/T-02/` |

## 6. 最终结论（含增补复核后，2026-11-12）

**不通过（就 task-board T-02 DoD 第2条与 R20 回滚数据保留项）——增补复核后维持。** 迁移基础设施本身正确并获独立复核：新装/存量副本 upgrade 到 head（0817df993d8b）、SQLite 每连接 foreign_keys=ON、唯一/FK 由数据库实际拒绝、源库 SHA-256 前后一致（真实库未动）、37/37 校验、6 契约单测通过、评审方独立严格全量 **310 passed**。

增补复核确认：
1. **R20 仍不通过**：初始迁移 downgrade base 删表，存量副本 10/98 → 0/0，不满足 design§5/verification§6「回滚恢复原结构且保留原数据」；`migration-summary.json` known_limitations `met=false` 保持如实未改。
2. **「备份副本 SHA-256 + 从备份恢复」不能替代 alembic 数据保留回滚证据**：`restore_drill.py` 9/9 PASS 仅为**运维恢复路径**证据，增补 §2 已明确声明不改 R20。
3. **干净空库首次启动 FK 崩溃已修复**：seed_data.py 虚构 `created_by=1` → `created_by=None`（列 nullable）+ 回归用例 `test_clean_empty_db_startup_seeding_survives_foreign_keys_on`，评审方独立单跑 1 passed，T-18 矩阵 fresh-empty-db /health=200。该修复为 T-02 引入问题（FK=ON）的可靠性回归修复，已回归。
4. task-3 已 reopen（rev6）保持 in_progress，不再次 complete；补做路径 = T-11 可逆 additive 迁移/归档导出 或 用户修订 design§5 并留变更记录后重判。

**R20 状态：不通过（回滚数据保留项）**，其余 R20 子项（新装、存量升级、FK/唯一、完整性、源库保护）通过。**限制：真实库严禁执行 `downgrade base`（会丢数据），只能在隔离副本演练。** 在上述补做完成前，R20 维持不通过，不得以备份恢复演练伪造通过。

## 7. 签名

reviewer，2026-11-12；本记录基于 migration-summary.json 原始结果、verify 日志与独立重跑作出，未替开发修改任何代码。
