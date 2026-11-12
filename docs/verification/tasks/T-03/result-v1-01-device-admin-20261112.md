# V1-01 补全（设备发现与改派）— 结果记录

- 任务编号：task-19（V1-01 补全：POST /device-discoveries 与 PATCH /devices/{serial} 版本条件改派，含 legacy refresh 委托）
- 执行人：infra-tools（Agent Team）
- 日期：2026-11-12（Asia/Shanghai）
- 契约依据：`docs/contracts/device-authorization-v1.0.md` §2/§4/§5/§6/§7；真值表 §1
- 说明：本文件为 T-03 目录的**追加结果文件**（不覆盖既有 `result.md`）。

## 1. 变更文件

| 文件 | 变更 |
|---|---|
| `app/services/device.py` | 新增 `ADBDiscoveryError`；`ADBService.get_device_list()` 显式区分「adb 失败（rc≠0/超时/内部异常）」与「有效空扫描」（返回 `(devices, error)`），`get_devices()` 保留旧语义（失败返回 []）；`DeviceService.discover_devices` 重写：ADB 失败抛 `ADBDiscoveryError`（不触碰 DB），既有设备**不改 owner/pc/version**、testing/maintenance 不被发现覆盖、状态仅在非 testing/maintenance 时 online/offline 推进；新设备 owner=None、pc=""（普通用户不认领）；`_list_adb_devices()` 兼容回退（真实用 `get_device_list`，Mock/旧调用回退 `get_devices`） |
| `app/api/devices.py` | 新增 `discovery_router`（无 prefix）：`POST /device-discoveries` 成功 201 + items/total/owner_unchanged=true，ADB 失败 503 SERVICE_UNAVAILABLE；`POST /devices/refresh` 标 deprecated 并委托同一 `discover_devices`（保留 found_devices，补 items/total/owner_unchanged，失败 503）；新增 `PATCH /devices/{serial}`（active 管理员；owner_id 可空/目标用户存在且 active；pc 1～255 去空白非空；version 必填；条件更新 WHERE version=? 递增；完全重放幂等；不同目标旧 version 409；未知字段/缺字段 400；设备/目标用户 404；disabled/普通用户 403）；`GET /devices/{serial}` 403 时 details.field=serial；既有授权过滤保留未回退 |
| `app/main.py` | 仅注册路由区新增一行 `app.include_router(devices.discovery_router, prefix="/api/v1")`（未改 lifespan/errors/其它路由） |
| `app/models/__init__.py` | Device 新增 `version = Column(Integer, nullable=False, default=1, server_default="1")`（lead 批准 A） |
| `alembic/versions/003_device_version.py` | 新增 additive 迁移：`ALTER TABLE devices ADD COLUMN version INTEGER NOT NULL DEFAULT '1'`；downgrade `ALTER TABLE devices DROP COLUMN version`（原生 ADD/DROP COLUMN，非 batch 影子表重建，避免 devices 被 test_tasks 外键引用时 FK 失败；行数据完整保留） |
| `tests/integration/test_v1_device_admin.py` | 新增 14 用例（发现/失败 503/owner 不变/普通用户不认领/空扫描不误离线/legacy 委托；PATCH 成功/409/完全重放/普通用户 403/disabled 403/404/pc 空白 400/未知字段 400/目标未激活 400；GET 403 details.field=serial） |
| `tests/unit/test_v1_migration.py`（跨任务机械更新） | 因新增授权 additive revision 003，`HEAD_REVISION` 常量由 `"002_idempotency"` 更新为 `"003_device_version"`（仅此一行；断言逻辑未放宽）——已报 Lead |
| `docs/verification/tasks/T-03/` | 本结果文件 + 迁移演练脚本/日志 + 全量回归日志 |

未触碰：tasks.py、judgement/execution/task_executor、websocket/reports/dashboard、frontend；devices.py 既有授权过滤未回退；device.py 的 T-19/异常分类改动保持原样（仅新增发现相关方法/异常）。

## 2. 环境

- Windows 10；Python 3.12.10（venv）；pytest 7.4.4 / pytest-asyncio 0.23.3；SQLAlchemy 2.0.25
- SQLite 3.49.1（支持原生 DROP COLUMN）；真实库 `backend/test_platform.db` 只读（SHA-256 前后一致 `2f919b05…1a789`）
- ADB：主机存在但本轮发现真值表使用 conftest Mock ADB（隔离、不触设备）；未做真机写操作

## 3. 命令、起止时间与退出码

| # | 命令（WORKDIR） | 起 | 止 | 退出码 | 结果 |
|---|---|---|---|---|---|
| 1 | `python -m pytest tests/integration/test_v1_device_admin.py -q`（backend） | 17:20+ | 17:20+ | 0 | **14 passed**（真值表逐行，`pytest-v1-01-device-admin-green-20261112.log`） |
| 2 | `python docs/verification/tasks/T-03/verify_device_version_migration.py`（MCTEST） | 17:11:22 | 17:11:25 | 0 | **16/16 PASS**：空库 0817→002→003、version 默认 1、downgrade 003 删列且设备行保留、再 upgrade 恢复；存量副本（10/98/26/5 行）stamp 0817 后 upgrade 加列且行数全保留、downgrade 002 删列且行数全保留、再 upgrade 恢复；源库 SHA-256 前后一致 |
| 3 | fresh 空库 `init_db()` 生产初始化探针（MCTEST） | 17:11:26 | 17:11:26 | 0 | `init_db OK`（alembic upgrade head + 结构指纹与 app.models 一致，含 version 默认值） |
| 4 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`（backend，全量） | 17:16:12 | 17:19:46 | 0 | **427 passed, 0 failed** |

## 4. 原始日志与产物

- `docs/verification/tasks/T-03/pytest-v1-01-device-admin-green-20261112.log`
- `docs/verification/tasks/T-03/migration-003-20261112.log`（含每条 alembic 原始输出/退出码/行数）
- `docs/verification/tasks/T-03/migration-003-summary.json`（16 项检查 + 空库/存量各阶段行数）
- `docs/verification/tasks/T-03/verify_device_version_migration.py`（可复现演练脚本）
- `docs/verification/tasks/T-03/init-db-fresh-20261112.log`
- `docs/verification/tasks/T-03/regression-full-20261112.log`（427 passed）

关键原始结论：
- 迁移：`empty/upgrade-head exit=0`（0817→002→003）；`empty/downgrade-002 exit=0`（version 列移除、devices 行保留）；`empty/re-upgrade-head exit=0`。`legacy:copy-sha-matches-source`、`legacy:upgrade-adds-version-column`、`legacy:existing-devices-version-1 (n=26)`、`legacy:upgrade-preserves-row-counts {test_tasks:10,test_records:98,devices:26,users:5}`、`legacy:downgrade-drops-version-column`、`legacy:downgrade-preserves-row-counts`、`legacy:re-upgrade-*` 全 PASS。
- 发现失败：`POST /api/v1/device-discoveries` → 503 `SERVICE_UNAVAILABLE`，testing 设备保持 testing、online 保持 online（无批量误离线）；有效空扫描 201 且 `items=[]/total=0/owner_unchanged=true` 且不误离线。
- 改派：管理员成功 200 且 `version 1→2`、pc 去空白；旧 version 不同目标 409 `CONFLICT details.field=version`；完全重放（同 owner/pc）即使 version 旧返回 200 且 version 不变；普通用户/disabled 403；404/400 按契约。

## 5. DoD 逐条

| DoD | 状态 | 证据 |
|---|---|---|
| POST /device-discoveries 成功 201 + items/total/owner_unchanged=true | ✅ | test_discovery_success_201_owner_unchanged |
| 发现不改既有 owner/PC/version | ✅ | test_discovery_does_not_change_existing_owner_pc_version |
| 普通用户发现新设备 owner=null | ✅ | test_normal_user_discovery_new_device_owner_null |
| ADB 失败 503，不批量误离线/不动 testing | ✅ | test_discovery_adb_failure_503_does_not_offline_or_touch_testing + 空扫描用例 |
| legacy /devices/refresh 委托同一服务（deprecated） | ✅ | test_legacy_refresh_delegates_same_service（200 成功 / 503 失败） |
| PATCH 仅 active 管理员；version 条件更新递增；完全重放幂等；不同目标旧 version 409；普通/disabled 403；404/400 | ✅ | 7 个 PATCH 用例逐条真值表 |
| GET /devices/{serial} 403 details.field=serial | ✅ | test_get_device_forbidden_details_field_serial |
| 新增 tests/integration/test_v1_device_admin.py | ✅ | 14 passed |
| 003 迁移空库/存量副本成功且数据保留 | ✅ | migration drill 16/16 + init_db 探针 |
| 全量 pytest 通过 | ✅ | 427 passed, 0 failed |

## 6. 未验证项 / 说明

1. **真实设备发现**未执行：发现真值表使用 conftest Mock ADB（隔离、不做设备写操作）；真机 adb 仅此前 T-19 只读审计，未在本任务触发 discovery。
2. **GET/list 响应暂不含 version**：DeviceResponse 的 version 字段由 stats-unify 在 task-16 增补（lead 已同步）；本任务 PATCH 响应返回含 version 的 dict 已落实，GET/list 在 task-16 后自然包含。
3. **真实库迁移未执行**（仅只读副本演练）。观察：既有 `backend/test_platform.db` 结构与当前 models 存在历史漂移（如 knowledge_entries 默认值/索引、test_tasks.plan 类型），生产 `init_db` 会按 V1-05 指纹策略明确拒绝 stamp（属既有 V1-05 事项，非本任务引入）；003 本身对结构一致的存量副本可升级且数据保留。
4. Docker/容器内运行未涉及（主机无 docker）。
5. 一致性说明：`tests/unit/test_v1_migration.py` 的 `HEAD_REVISION` 常量随 003 机械更新（见第 1 节）；其余 task-11 断言未改。

## 7. 回退说明

1. `app/api/devices.py`：删除 `discovery_router` 与两个新路由（discoveries、PATCH），`refresh` 恢复旧实现；`GET` 403 details 恢复纯 HTTPException。
2. `app/main.py`：删除新增的 `app.include_router(devices.discovery_router, ...)` 一行。
3. `app/services/device.py`：删除 `ADBDiscoveryError`/`get_device_list`/`_list_adb_devices`；`discover_devices` 恢复旧实现（注意旧实现会改 owner/pc，回退将重新引入 V1-01 缺陷，不建议）。
4. `app/models/__init__.py`：删除 Device.version 列；删除 `alembic/versions/003_device_version.py`；`tests/unit/test_v1_migration.py` HEAD_REVISION 回退 002。
5. 删除 `tests/integration/test_v1_device_admin.py`、`docs/verification/tasks/T-03/{result-v1-01...,verify_device_version_migration.py,migration-003*,init-db-fresh*,pytest-v1-01*,regression-full-20261112.log}`。
6. 未 git commit；回退需手工反向编辑或经 Lead 确认后 `git restore`。
