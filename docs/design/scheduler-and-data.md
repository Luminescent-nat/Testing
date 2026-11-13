# 调度、设备状态、数据与部署契约

- 版本：v1.0
- 状态：2026-11-12 用户已确认
- 需求：R16～R20、R27、R29

## 1. 调度数据模型

| 字段/约束 | 类型 | 规则 |
|---|---|---|
| task_kind | string | instance/daily_template；模板不执行、不进入 Dashboard 执行统计 |
| template_id | integer/null | daily 实例指向模板；普通 immediate/once 为 null |
| scheduled_for | datetime/null | 实例对应的 UTC 计划时刻，不用实际扫描时刻替代 |
| next_run_at | datetime/null | 模板或 once 任务下次触发时刻 |
| scheduled_time | string/null | daily 为 HH:MM，once 为 YYYY-MM-DD HH:MM，服务器本地时间输入 |
| deleted_at | datetime/null | 软删除标记，终态删除不破坏证据引用 |
| item_snapshot | object/null | 创建时测试项执行配置快照 |
| item_snapshot_status | string | complete/legacy；历史无快照只能 legacy |
| UNIQUE(template_id,scheduled_for) | constraint | template_id 非 null 时同一计划时刻至多一个实例 |
| UNIQUE(user_id,idempotency_key) | constraint | 用户范围内客户端写重试去重 |

模板修改只影响修改后创建的实例；实例使用创建时快照。历史任务没有快照时显示“历史任务，无配置快照”，不得用当前测试项反填冒充原配置。

## 2. daily 触发算法

1. 在事务中选择 `task_kind=daily_template`、`status=pending`、`deleted_at IS NULL` 且 `next_run_at<=now` 的模板。
2. 根据 scheduled_time 和 now 计算“不晚于 now 的最近一次计划时刻”，转换为 UTC 作为 scheduled_for。
3. 以 `(template_id,scheduled_for)` 插入独立 pending 实例；唯一冲突表示其他扫描已创建，当前扫描不启动任何实例。
4. 仅成功插入实例的事务提交后才启动该实例；前实例仍 running 时新实例 pending 等锁。
5. 将模板 next_run_at 推进到严格晚于 now 的下一计划时刻。跨天未扫描至多创建上述最近一次实例，不逐日补跑。
6. 重启重复扫描同一 scheduled_for 时唯一约束保证至多一个实例；已 cancelled/deleted 模板不再触发。

once 任务到期后只启动原任务并清 next_run_at；未到期 pending 不受启动恢复影响。immediate 不经过调度器。

## 3. 调度验收输入

| 场景 | 必须结果 |
|---|---|
| 同一 scheduled_for 并发扫描 10 次 | 恰好一个实例、一个执行启动；其余唯一冲突分支无副作用 |
| 首个实例 completed 后下一计划时刻到达 | 新 ID、新记录、新报告；模板仍 active |
| 前一实例 running 时下一时刻到达 | 新实例 pending，不并行使用同一设备 |
| 服务停机跨多个日期 | 恢复至多一个最近计划实例，不逐日补跑 |
| `24:00`、`9:60`、空串、非法 once 过去时间 | 400，数据库无模板或任务新增 |

## 4. 设备锁与状态推进

- 只有当前 DeviceLock 持有者可以把设备置 testing，并在释放时推进到有效探活确定的 online/offline。
- 排队任务保持 pending，不得因排队抢先覆盖设备状态；旧任务收尾不能释放新持有者 B 的锁。
- 心跳和手动刷新不得覆盖 testing；testing 的离开由持有者收尾或明确的恢复流程处理。
- ADB 可执行失败、超时、非零退出属于“探测失败”，不是空设备列表；保持现有状态并记录安全错误，不批量 offline。
- 只有成功且可信的空扫描才可处理非 testing 的消失设备；持有者释放时若探活失败，不伪造 online。
- 普通用户发现不能写 owner；管理员改派使用 Device.version 条件更新。

## 5. 迁移契约

### 新装与存量

- 新装空库执行 `alembic upgrade head`；生产初始化不再依赖 create_all 后 stamp。
- 存量库先备份并计算 SHA-256，只对备份副本演练；确认 schema 后才在目标库执行升级。
- `alembic stamp head` 只可用于已独立核对“结构与 head 完全一致”的库，不是新装默认命令。
- SQLite 每个连接启用 `PRAGMA foreign_keys=ON`，保留 WAL；迁移事务中按 SQLite 要求管理外键与表重建。

### 约束

- users.username、devices.serial_number 唯一。
- tasks/records/device owner/user/template 等关联建立外键；删除策略与软删除、证据保留一致。
- daily 计划时刻和用户幂等键唯一约束必须由数据库执行，不能只靠应用先查后写。
- 状态、结果和 task_kind 使用 CHECK 或等价数据库约束，应用层仍做友好校验。

### 回滚与异常

- 升级、回滚前后记录表结构、任务/记录/报告数量和数据库完整性检查。
- 回滚恢复原结构且保留原数据；新增列被移除前须验证没有需要保留的新业务写入。
- 任一迁移异常必须停止并非静默删记录；真实库出现异常时从备份恢复并保留失败日志。
- 没有实际运行存量副本升级/回滚，不得标 R20 通过。

## 6. 干净部署契约

- Docker 构建上下文和最终镜像必须包含 manifest 声明的 test-tools、runner 和对应架构二进制；启动时执行只读工具发现校验。
- 声明存在但镜像缺失的必需工具使启动失败并指出 manifest 路径；范围内缺失 APK、外设或人工条件按 R3 记 skip，不伪造工具结果。
- SECRET_KEY 必须显式配置，至少 32 个字符，且不得等于空串、`secret`、`change-me`、`your-secret-key`、Compose 示例占位值或仅重复单字符。开发/生产均不得在弱默认密钥下静默启动。
- 配置错误日志只指出配置项，不打印密钥值；文档命令路径与镜像实际工作目录一致。
- 当前未执行干净 Docker 构建与启动，R27 仍为未验证。

### 6.1 工具清单声明规则（v1.1 新增，2026-11-13 经用户确认）

每个模块目录的 `manifest.yaml` 必须显式声明 `tools` 段，结构如下：

```yaml
tools:
  host:                       # host runner
    - path: upfm/host/mc_props_check.py
      sha256: "<64 位十六进制>"   # 必填
      version: "<可选>"
  shared:                     # 共享 Python 依赖
    - path: common/adb_runner.py
      sha256: "<64 位十六进制>"   # 必填
  device:                     # 设备二进制
    - path: emmc/binaries/armeabi-v7a/fio
      abi: armeabi-v7a          # 必填
      sha256: "<64 位十六进制>"   # 必填
  assets:                     # 可选测试资源
    - path: upfm/assets/test_app.apk
      sha256: "<可选>"
```

- **A1**：`tools.host` 与 `tools.shared` 条目 `path`、`sha256` 必填；缺失即 manifest 加载失败（`ToolManifestError`，错误信息指出 manifest 路径与问题条目）。声明了 sha256 的条目必须哈希匹配，不匹配启动失败（v1.0 语义保持）。
- **A2**：`tools` 段存在但四段全空（如 `tools: {}`）且模块目录含 `host/*.py` 或 `binaries/*/*`，视为声明缺口，启动失败；完全无 `tools` 段同此处理（v1.0 语义保持）。
- **A3**：`items[].exec_command` 中 `{host_tool_dir}/X` 引用的文件 X 必须在某 manifest 的 `tools.host` 显式声明；**未声明即 manifest 加载失败，废除 undeclared_reference 降级条目**。已声明的 host runner 及其 `import common.*`、`from common import *`、同目录兄弟模块 import 的全部依赖必须在 `tools.shared`/`tools.host` 声明内（依赖闭包，v1.0 语义保持）。
- **A4**：声明 `path` 规范化后不得为空、为绝对路径或含 `..` 越界；违反即 manifest 加载失败，错误信息包含 manifest 路径与原始声明值。
- **A5**：`TEST_TOOLS_PATH` 存在但不含任何 `manifest.yaml` 时启动失败，禁止空工具目录静默启动。
- `tools.assets` 条目 `path` 必填、`sha256` 可选；缺失的已声明可选资源按 R3 记 skip，不伪造工具结果（v1.0 语义保持）。

## 7. 文件与证据生命周期

| 类别 | 默认策略 | 删除条件 |
|---|---|---|
| pytest/Vitest/Playwright 临时库与 storage | 每用例/每轮隔离 | 确认为本轮临时路径且证据已另存后可清理 |
| 正式数据库与备份 | 受保护 | 不作为普通缓存删除；迁移前哈希和恢复副本 |
| 上传、报告、执行日志 | 受保护并关联任务 | 仅按确认保留策略处理，软删除默认 retained |
| UPFM/archive 实机证据 | 逐项受保护 | 不得整目录删除；逐项证明可重建或有恢复副本 |
| 构建缓存 | 可重建 | 引用检查后按清单删除并回归 |

报告和实机记录必须绑定 commit、设备 serial、板型、环境、Mock/实机类型、静态/实机覆盖与 skip 原因。缺少这些字段的历史报告标 legacy/未验证，不补造元数据。
