# T-14 任务删除边界、item_ids 写前校验与设备不可用 409（V1-09b）验证记录

- 任务：task-17（V1-09b，对应 T-14；rev5→rev6，含 D2 追加与三项前置裁决）
- 状态：实现完成；聚焦 **42 passed / exit 0**；全量（最终轮）**443 passed / 0 failed / exit 0**（详见第 5 节关于另一成员在途审计文件的处理）
- 日期：2026-11-12；基线 HEAD fa70d3b（含 task-12 幂等/201、task-16 stats、task-19 device.version）；未 commit（Lead 统一提交）
- 环境：Windows + D:\MCTEST\test-platform\.venv\Scripts\python.exe（Python 3.12.10，pytest 7.4.4，fastapi 0.109.0，alembic）

## 1. 变更文件
| 文件 | 变更 |
|---|---|
| test-platform/backend/app/models/__init__.py | `TestTask.deleted_at = Column(DateTime(timezone=True), nullable=True)`（契约 task-execution §8 软删除；经 Lead 批准加入 models scope） |
| test-platform/backend/alembic/versions/004_task_deleted_at.py | **新增**：`down_revision='003_device_version'`；原生 `ALTER TABLE test_tasks ADD COLUMN deleted_at DATETIME NULL`（不重建表、不触发 FK）；**downgrade 数据保护**：存在 deleted_at 非空行时抛 RuntimeError 拒绝降级，无软删除数据才 DROP COLUMN |
| test-platform/backend/app/schemas.py | `TestTaskCreate._validate_item_ids`：空/非正整数/重复 → ValueError → 400 `details.field=item_ids`（存在性/禁用由 API 层 `item_ids.<下标>`） |
| test-platform/backend/app/api/tasks.py | ①create：offline/maintenance **400→409 CONFLICT**（D2/V1-04）；不存在/禁用 item 由 404 改 **400 `item_ids.<下标>`**（R14，写前零写入，`_ItemValidationError`+`_validation_error_response` 契约外层）；②rerun：offline/maintenance 同改 **409**（契约 §7）；③`list_tasks` 默认排除 `deleted_at` 非空；④`get_task` 排除已删除（404）；⑤`delete_task` 改软删除：pending/running→409、终态写 deleted_at、重复删除幂等 200（不 500、不重复改写）、`data={id,deleted:true,artifacts:"retained"}`、非管理员 403（get_current_admin） |
| test-platform/backend/tests/integration/test_v1_task_delete.py | **新增** 18 用例（软删除/幂等/409/越权/引用保留/排除、item_ids 六类非法、创建与重跑设备不可用 409） |
| test-platform/backend/tests/integration/test_tasks_api.py | TC-TASK-002 离线 400→**409 CONFLICT**；TC-TASK-004 不存在 item 404→**400 details.field=item_ids.0** |
| test-platform/backend/tests/integration/test_contract_errors.py | 离线设备创建 400 VALIDATION_ERROR → **409 CONFLICT**（test_business_409_offline_device，更严） |
| test-platform/backend/tests/unit/test_v1_migration.py | **跨任务同步**（Lead 授权，先例第 2 次）：`HEAD_REVISION` 由 `"003_device_version"` 等价更新为 `"004_task_deleted_at"`（跟随真实迁移 head，断言逻辑不变，非放宽；004 合入后原值使 5 处 `assert _version==HEAD` 失败） |

未改：judgement/execution/task_executor、reports、websocket、frontend、database.py、device.py。**AI 路径 offline/maintenance 仍 400**（按 Lead 裁决，AI 不在本 scope，记录见第 6 节遗留 2）。

## 2. 删除边界与 item_ids 用例矩阵（test_v1_task_delete.py，18 用例）
| 场景 | 期望 | 断言要点 |
|---|---|---|
| 管理员删 completed | 200 `{id,deleted:true,artifacts:"retained"}` | deleted_at 非空；TestRecord 保留；默认列表不含该 id；GET 详情 404 |
| 重复删除 | 200 幂等 | 不 500；deleted_at 值不变 |
| 删 pending / running（参数化） | 409 CONFLICT | deleted_at 仍 None |
| 普通用户删除 | 403 FORBIDDEN | 零写入 |
| 删不存在 | 404 | — |
| item_ids `[]`/`[0]`/`[-1]`/`[1,1]` | 400 | details.field=item_ids；零任务写入 |
| item_ids `["abc"]` | 400 | details.field=item_ids.0 |
| 不存在 item（合法+99999） | 400 | details.field=item_ids.1；零任务写入 |
| 禁用 item（enabled=False） | 400 | details.field=item_ids.0，reason 含“禁用” |
| 创建 offline / maintenance（参数化） | 409 CONFLICT | 零任务写入 |
| 重跑设备 offline | 409 CONFLICT | 零新增任务 |

## 3. 迁移演练（隔离临时库，未触碰真实库；日志 alembic-004-drill.log + 辅助脚本 alembic_004_drill.py）
| 步骤 | 退出码 | 结果 |
|---|---:|---|
| `alembic upgrade head`（004 在 003 之后） | 0 | head=004_task_deleted_at |
| 播种 2 行任务（1 行 deleted_at 非空） | 0 | rows(total=2, soft-deleted=1) |
| `downgrade 003_device_version`（有软删除数据） | **1（拒绝）** | RuntimeError“存在 1 行已软删除任务…降级将丢失删除标记”；数据仍在（rows=2,1） |
| 清空软删除数据后 downgrade | 0 | 行数据保留 |
| 重新 `upgrade head` | 0 | 恢复全部表 |

## 4. 命令与退出码（原始日志）
| # | 命令 | 结果 | 日志 |
|---|---|---|---|
| 1 | `pytest tests/integration/test_v1_task_delete.py tests/integration/test_tasks_api.py tests/integration/test_contract_errors.py -q --tb=short -rA` | **42 passed，exit 0**（17:45 前后） | [pytest-focused.log](pytest-focused.log)（副本见 T-10/v1-09b-delete-itemids-409-focused.log） |
| 2 | 全量第 1 轮（HEAD_REVISION 未同步） | 438 passed / **5 failed**（均为 test_v1_migration.py 的 HEAD 常量），日志保留 | [pytest-full-run-01.log](pytest-full-run-01.log) |
| 3 | 全量第 2 轮（HEAD_REVISION 同步后，含他人在途文件） | 443 passed / **5 failed**（均为未跟踪新文件 test_v1_followup_audit.py，见第 5 节） | [pytest-full-run-02-final.log](pytest-full-run-02-final.log) |
| 4 | 全量第 3 轮（最终，`--ignore=tests/integration/test_v1_followup_audit.py`） | **443 passed，0 failed，exit 0**（226.0s） | [pytest-full-run-03-final-ignore-followup-audit.log](pytest-full-run-03-final-ignore-followup-audit.log) |
| 5 | `pytest tests/unit/test_v1_migration.py -q`（HEAD_REVISION 同步后） | 9 passed，exit 0 | 融入第 4 轮全量 |

## 5. 全量回归中他人在途文件的说明（如实记录）
`tests/integration/test_v1_followup_audit.py`（git 未跟踪，运行期间由其他成员新增，文件头注明“仅审计使用”）覆盖**尚未实现**的设备契约端点：PATCH /devices/{serial}（owner_id 必填/版本）、POST /device-discoveries（空体校验）、设备分页参数校验、AI 维护设备 409。5 个失败均与 task-17 改动无关（对应端点不存在或 AI 路径按裁决保持 400）。按“其它队友在途模块可临时 ignore 并在 result 说明”的规则，最终轮以 `--ignore` 执行得到 443 passed / exit 0；**未修改、未跳过、未删除该文件**，完整失败日志保留（第 4 节 #3 及其 T-10 副本）。该审计文件归属任务（疑为 T-03 设备契约完整实现）由 Lead 归口。

## 6. DoD 结论（T-14 / task-17 rev5）
- **DELETE：running/pending→409；终态软删除 deleted_at 幂等、重复删除不 500、越权 403；记录/报告引用一致** → 达成（第 2 节 + 迁移演练）。
- **默认任务列表排除 deleted_at 非空** → 达成（列表与详情均排除；报告引用保留可追溯）。
- **schemas item_ids 空与非正/重复→400；不存在/禁用→400 details.field=item_ids.<下标>** → 达成。
- **D2：创建 offline/maintenance 400→409；重跑同样 409** → 达成（test_tasks_api、test_contract_errors、test_v1_task_delete 三处覆盖，更严不放宽）。
- **禁止改 judgement/execution/task_executor、reports、websocket、frontend** → 已遵守。

## 7. 遗留 / 需评审
1. **AI 创建入口 offline/maintenance 仍 400**（Lead 裁决 AI 不在本 scope）；审计用例 `test_audit_ai_maintenance_device_cannot_start` 期望 409，需在 AI 接入统一创建服务的任务中一并改为 409（契约 §8 legacy 说明：AI 必须先转成同一创建对象）。
2. 设备 PATCH/discoveries/分页校验未实现（他人在途审计文件所指，非本任务）。
3. `scripts/verify_migrations.py` 的 `HEAD_REVISION` 常量仍为 002_idempotency（T-02 脚本，不在 scope）；003/004 落地后建议 infra 同步该常量并重跑迁移演练。
4. T-10 append：本任务聚焦与全量日志副本已放入 docs/verification/tasks/T-10/（v1-09b-*.log）。

## 8. 追加（task-22，2026-11-12）
- 经 Lead 授权（task-22 rev3），`app/schemas.py` 的 `DeviceStatus` 枚举补齐 `MAINTENANCE = "maintenance"`（契约 device §2 status 集合）。属既有缺口：PUT /devices/{serial}/status 本就允许管理员设置 maintenance，而响应序列化枚举缺项导致 maintenance 设备 GET 详情/列表 500（pydantic ValidationError）。仅新增枚举成员，未动 task-16 的统计聚合定义。
- `scripts/verify_migrations.py` 的 `HEAD_REVISION` 由 `002_idempotency` 同步为 `004_task_deleted_at`（跟随真实 head，断言不放宽），重跑演练 **RESULT: PASS (74/74 checks)**，日志 [verify-migrations-004-drill.log](verify-migrations-004-drill.log) + [migration-summary-v1followup.json](migration-summary-v1followup.json)。
- 关联全量：task-22 最终全量 448 passed / 0 failed / exit 0（见 [T-03/pytest-full-run-followup-final.log](../T-03/pytest-full-run-followup-final.log)）。
