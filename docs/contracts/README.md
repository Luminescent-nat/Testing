# 后端接口与状态契约索引

- 契约版本：v1.1
- 日期：2026-11-09
- 确认日期：2026-11-12（v1.0）；2026-11-13（v1.1 变更经用户授权确认）
- 状态：已确认；是当前后续实现的唯一接口事实来源，不代表实现已完成
- 唯一上游：`docs/requirements/requirements-v2.3.md` R1～R31

## 1. 契约文件

| 文件 | 范围 | 需求 |
|---|---|---|
| [device-authorization-v1.0.md](device-authorization-v1.0.md) | 设备列表、详情、发现、归属改派 | R5、R6、R18、R21 |
| [task-execution-v1.0.md](task-execution-v1.0.md) | 任务创建、查询、取消、重跑、删除、WS | R5、R7～R19、R31 |
| [user-administration-v1.0.md](user-administration-v1.0.md) | 首管理员、登录、管理员建号、禁用 | R7、R28 |
| [reporting-v1.0.md](reporting-v1.0.md) | 报告、导出、Dashboard、趋势与模块统计 | R3、R7、R10～R12、R22、R29 |
| [knowledge-rules-v1.0.md](knowledge-rules-v1.0.md) | 知识预览、转换与可执行条件规则 | R8、R15 |
| [execution-state-machine.md](../design/execution-state-machine.md) | 判定优先级、终态、stop、进度与通过率 | R8～R12、R15、R31 |
| [scheduler-and-data.md](../design/scheduler-and-data.md) | daily 幂等、恢复、迁移、设备状态与部署 | R16～R20、R27、R29 |

## 2. 通用传输约定

- REST 根路径为 `/api/v1`；资源路径使用小写复数名词。非基本 CRUD 的业务动作采用 POST 创建对应名词子资源，并在各契约注明原因。
- 鉴权使用 `Authorization: Bearer <JWT>`。未认证为 401；已认证但角色、owner、PC 分组或 active 状态不满足为 403。
- 时间字段均为 ISO 8601 UTC 字符串，例如 `2026-11-09T08:00:00Z`；数据库可以用 UTC aware datetime 实现。
- `pass_rate` 是 0～100 的 number 或 null，不带 `%`，最多一位小数；分母为零必须为 null。
- 列表响应固定包含 `items`、`total`、`page`、`page_size`；`page>=1`，`1<=page_size<=100`，默认 20。
- 所有写接口先校验输入与授权，再进入业务写入；校验失败不得留下任务、实例、账号或设备归属变化。
- 错误响应不得包含堆栈、SQL、服务器绝对路径、密钥或命令行细节。

### 成功响应外层

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| code | integer | 是 | 与 HTTP 成功状态码一致 |
| message | string | 是 | 稳定的人类可读摘要 |
| data | object | 是 | 各契约定义的数据对象；无内容时使用空对象 |

### 错误响应外层

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| code | string | 是 | 稳定机器码，仅取契约错误码表 |
| message | string | 是 | 不泄露内部信息的中文摘要 |
| details | object | 是 | 定位信息；无字段级信息时为 `{}` |

`details` 可选键为 `field`（JSON 请求字段路径或 query 参数名）、`item_id`（正整数）、`reason`（安全摘要）。字段路径示例：`custom_parameters.12.count`；数组下标使用点号。

### 通用错误码

| code | HTTP | 触发条件 |
|---|---:|---|
| VALIDATION_ERROR | 400 | 字段类型、结构、枚举、数值或跨字段约束不合法 |
| UNAUTHENTICATED | 401 | token 缺失、无效、过期或用户不存在 |
| FORBIDDEN | 403 | 角色、归属、PC 分组或 active 状态不允许 |
| NOT_FOUND | 404 | 指定资源不存在 |
| CONFLICT | 409 | 状态冲突、唯一约束或幂等键对应不同请求 |
| INTERNAL_ERROR | 500 | 未预期服务端异常；仅返回通用摘要 |
| SERVICE_UNAVAILABLE | 503 | ADB 或必需外部能力调用失败，不得伪装为空结果 |

## 3. 写操作幂等约定

- 任务创建和失败重跑：请求头 `Idempotency-Key` 必填，长度 8～128 的可打印 ASCII；服务端保存 `(user_id,key,request_sha256,response)`，唯一约束防并发重复。相同用户、相同键、相同请求体重放返回首次响应且不再次执行；不同请求体复用键返回 409。
- daily 触发：使用 `(template_id,scheduled_for)` 唯一约束，不使用客户端幂等键。
- 取消、禁用、软删除：条件更新至目标状态，重复请求返回相同当前状态，不重复终止进程或删除数据。
- 设备改派：使用版本条件更新；已完成相同目标状态的完全重放返回当前设备，不同目标使用旧版本返回 409。

## 4. 兼容与迁移

当前代码存在 `/devices/refresh`、`/tasks/{id}/cancel`、`/tasks/{id}/rerun-failed`、`/auth/register`、`/auth/login` 和报告 `export` 等动作路径，也存在 `{"detail":...}` 或 `errors` 错误结构。它们均为 legacy，不代表本契约已实施。

目标实现先提供本契约路径和统一错误格式，再同步前端；legacy 路径只作短期适配，必须标注弃用并覆盖相同授权与语义，完成联调回归后才可移除。不得为兼容而保留普通用户认领、默认 pass 或错误统计口径。

任何已确认契约变更须前后端双方确认，版本号增加 0.1，并在本节下方追加变更记录；不得直接覆盖已确认含义。

## 5. 变更记录

| 版本 | 日期 | 状态 | 内容 |
|---|---|---|---|
| v1.0 | 2026-11-12 | 已确认 | 首版整改目标契约获用户确认，语义未变，后续变更须升级至 v1.1 |
| v1.1 | 2026-11-13 | 已确认 | ① 工具清单显式声明语义收严（scheduler-and-data §6.1 新增 A1～A5：host/shared sha256 必填、空 tools 段视为声明缺口、`{host_tool_dir}` 引用必须显式声明并废除 undeclared 降级、非法路径硬失败、空 TEST_TOOLS_PATH 拒绝启动）② AI 任务入口授权顺序：设备授权先于知识读取与 LLM 调用，403/409 时两类调用计数为零，任务写入收口统一创建服务（task-execution §10 追加） |

## 6. 确认边界

本版没有以“视情况而定”保留 P0 口径。HTTP 字段约束、目标路径和幂等策略均在本组文档给出，并已于 2026-11-12 获用户确认。当前无 ADB 设备、完整 Playwright、Docker 和存量迁移证据，均不得因契约确认而标为实现或通过验收。
