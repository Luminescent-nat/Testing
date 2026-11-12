# T-02 增补记录 — RR-T02 评审不通过回应与补充验证

- 任务编号：T-02（task-3，已由 Lead 按 RR-T02 reopen，当前 in_progress，**不再标 complete**）
- 本文件为**增补记录（新文件）**，不覆盖原 `result.md`；原 `migration-summary.json` / `known_limitations` 保持如实未改动（不伪造通过）。
- 日期：2026-11-12（Asia/Shanghai）

## 0. 评审结论（RR-T02）

**不通过（DoD 第 2 条 / R20 回滚数据保留项）**：初始迁移 `0817df993d8b` 的 `downgrade base`
删表，存量副本 test_tasks/test_records 由 10/98 → 0/0；「从备份恢复」不能作为 alembic
数据保留回滚的证据；验证规则 §6 规定没有实际回滚日志则 R20 不通过。本增补记录完全接受该结论。

## 1. ① downgrade base 在真实/存量库的执行边界（明确禁止）

- **真实库（`backend/test_platform.db`）严禁执行 `alembic downgrade base`**，也不得对任何
  存量生产库执行会删表的 downgrade；迁移操作只允许在隔离临时目录内的副本上演练
  （`verify_migrations.py` 内置安全断言：真实库路径不得传入任何 alembic 子进程）。
- 本次全部 downgrade/upgrade 演练均发生在 `%TEMP%\t02_migrations_*` 隔离目录，源库前后
  SHA-256 一致（`2f919b05…1a789`，含 sidecar），原始日志见 `verify-migrations-20261112.log`。
- 生产存量库升级/回滚操作规程（供运维执行，非本会话执行）：先备份并计算 SHA-256 →
  仅对副本演练 → 确认 schema 后再对目标库执行 → 出现异常从备份恢复并保留失败日志。

## 2. ② 合规回滚路径演练：备份副本 SHA-256 + 从备份恢复（运维层，非 alembic 证据）

新增演练脚本 `docs/verification/tasks/T-02/restore_drill.py`，原始日志
`docs/verification/tasks/T-02/restore-drill-20261112.log`（退出码 0，9/9 PASS）：

```
[source] backend/test_platform.db sha256=2f919b05…1a789（只读）
[backup]  只读备份副本 sha256 与源一致；counts={test_tasks:10, test_records:98, users:5, devices:26}
[live]    模拟误操作：stamp head + upgrade head（exit 0/0，文件哈希改变）
[restored] 用只读备份副本整体覆盖 live → sha256 恢复一致、行数全部保留、integrity_check=ok
[source]  前后 SHA-256 一致（全程只读）
```

**定位声明（按 RR-T02）**：该演练仅证明「备份→哈希→异常后从备份恢复→数据完整」这一
**运维恢复路径**可用；它**不能替代** alembic 回滚保留原数据的证据，R20 判定不受其影响。

## 3. ③ R20 当前结论与后续补做路径

- **R20 当前结论：不通过**（回滚数据保留未达成；迁移演练本体通过但不足以覆盖 DoD 第 2 条）。
- 补做路径（择一，均不在 T-02 范围内擅自实施）：
  1. **T-11（后续可逆 additive 迁移）**：新增单步可逆 additive 迁移（加列/加索引），
     对含数据副本执行 upgrade→downgrade→upgrade，验证 downgrade 仅回退结构、行数与
     内容全保留，并留存原始回滚日志；
  2. 或由用户修订 `docs/design/scheduler-and-data.md` §5（如确认「回滚以备份恢复为准」），
     留设计变更记录后，R20 按「备份恢复即合规回滚」重新判定（本增补第 2 节演练可直接引用）。
- 在上述任一完成前，R20 维持不通过，不得以本增补伪造通过。

## 4. ④ 任务状态

task-3 已由 Lead reopen（revision 6，in_progress）；保持 in_progress，**不再次 complete**，
等待可逆 additive 迁移补做或设计修订后再评。

## 5. 新发现与已修复：干净空库首次启动 FK 崩溃（T-02 引入）

T-18 真实启动矩阵（fresh 空库 + 合法密钥）暴露：`PRAGMA foreign_keys=ON` 后
`app/seed_data.py` 在无用户时使用虚构 `created_by=1`（`user_id = user.id if user else 1`），
`TestModule.created_by=1` 外键失败 → **干净空库首次启动直接崩溃**
（`sqlite3.IntegrityError: FOREIGN KEY constraint failed` @ seed_data.py:409 flush；影响
Docker 空数据卷部署与 T-17 干净部署契约；存量库不受影响）。

修复（经 Lead 授权，task-3 rev6 加入 `app/seed_data.py` scope）：
- `user_id = user.id if user else None`（`created_by`/`owner_id` 均 nullable，已核对 models）；
- `_seed_default_modules_and_items(db, user_id: Optional[int])` 类型标注（业务逻辑不变）；
- 新增回归测试 `tests/unit/test_migration_contract.py::test_clean_empty_db_startup_seeding_survives_foreign_keys_on`：
  临时空库 + 每连接 FK=ON 下 `create_all + seed_default_data` 成功、模块 created_by 全为 NULL、
  `PRAGMA foreign_key_check` 空、integrity_check=ok；
- 端到端证据：T-18 启动矩阵 `fresh-empty-db` 用例 /health=200（修复前同一场景 uvicorn exit≠0 且命中 FK 错误，
  修复前原始日志保留在 `docs/verification/tasks/T-18/` 首次运行记录与消息存档中）。

## 6. 证据索引（增补部分）

- `docs/verification/tasks/T-02/restore_drill.py` + `restore-drill-20261112.log`（9/9 PASS，退出码 0）
- `docs/verification/tasks/T-02/pytest-T02-seedfix-green-20261112.log`
  （`python -m pytest tests/unit/test_migration_contract.py tests/unit/test_secret_strength.py tests/unit/test_tool_manifest.py -q` → 35 passed，退出码 0）
- `docs/verification/tasks/T-18/startup-matrix-20261112.log` / `startup-matrix.json`（fresh 空库启动成功证据）
- `docs/verification/tasks/T-17/regression-full-20261112.log`（全量 310 passed，含 seed 修复）
- 原 `result.md` / `verify-migrations-20261112.log` / `migration-summary.json` 保持不变（如实）。

## 7. 增补的回退说明

- `app/seed_data.py`：恢复 `user_id = user.id if user else 1` 与 `user_id: int` 标注（**不建议**：
  会使干净空库首次启动在 FK=ON 下崩溃）。
- 删除 `tests/unit/test_migration_contract.py` 中新增的
  `test_clean_empty_db_startup_seeding_survives_foreign_keys_on` 用例与
  `docs/verification/tasks/T-02/restore_drill.py`、`restore-drill-20261112.log`、本增补文件。
- 原 `result.md` 中追加的「评审不通过」指针章节可一并移除。
