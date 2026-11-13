# 接口契约：任务创建、执行与订阅

- 版本：v1.0
- 状态：2026-11-12 用户已确认
- 鉴权：JWT Bearer；任务创建者或 active 管理员可访问任务；创建设备还须通过设备授权
- 需求：R5～R19、R31

## 1. 数据对象

### Task

| 字段 | 类型 | 说明 |
|---|---|---|
| id | integer | 任务或 daily 模板 ID |
| name | string | 名称 |
| device_serial | string | 目标设备序列号 |
| task_kind | string | instance/daily_template；模板不进入执行统计 |
| status | string | pending/running/completed/failed/cancelled |
| result | string/null | passed/failed/null |
| total_items | integer | N，选中项数 |
| completed_items | integer | C，仅五类终态 |
| counts | object | pass/fail/skip/error/timeout 五个 integer 键 |
| progress_percent | integer | 0～100，按统一公式 |
| pass_rate | number/null | 单项通过率，分母 0 为 null |
| schedule_type | string | immediate/once/daily |
| scheduled_time | string/null | 原始计划时间 |
| next_run_at | string/null | 下次 UTC 触发时刻 |
| template_id | integer/null | 实例所属 daily 模板 |
| scheduled_for | string/null | 实例对应的 UTC 计划时刻 |
| item_snapshot_status | string | complete/legacy；历史无快照为 legacy |
| started_at | string/null | 开始 UTC 时间 |
| completed_at | string/null | 收尾 UTC 时间 |
| created_at | string | 创建 UTC 时间 |

### TestRecord

| 字段 | 类型 | 说明 |
|---|---|---|
| id | integer | 记录 ID |
| task_id | integer | 所属独立执行实例 |
| item_id | integer | 稳定测试项 ID，对比不得使用名称 |
| item_name | string | 显示名称 |
| module_name | string | 模块名称 |
| status | string | pending/running/pass/fail/skip/error/timeout |
| reason | string/null | fail/error/timeout/skip 的真实原因 |
| extracted_data | object/null | 提取值，数值 0 必须保留 |
| execution_time | number/null | 秒，0 必须保留 |
| started_at | string/null | 开始 UTC 时间 |
| completed_at | string/null | 完成 UTC 时间 |

## 2. POST /api/v1/tasks

### 请求头

| 名称 | 必填 | 约束 |
|---|---|---|
| Authorization | 是 | Bearer JWT |
| Idempotency-Key | 是 | 8～128 可打印 ASCII，按 README 幂等规则 |

### 请求体

| 字段 | 类型 | 必填 | 默认 | 约束 | 示例 |
|---|---|---|---|---|---|
| device_serial | string | 是 | 无 | 已登记设备；owner/PC/状态校验 | A133P-01 |
| name | string/null | 否 | 服务端生成 | 去空白后 1～200；null/省略生成 | 每日基础测试 |
| item_ids | array[integer] | 是 | 无 | 至少 1 个、正整数、无重复、全部存在且 enabled | [12,13] |
| custom_parameters | object | 否 | {} | 外层键为已选 item_id 的十进制字符串；内层为扁平参数对象 | {"12":{"target":"8.8.8.8","count":0}} |
| schedule_type | string | 否 | immediate | immediate/once/daily | immediate |
| scheduled_time | string/null | 条件必填 | null | once=`YYYY-MM-DD HH:MM` 且未来；daily=`HH:MM`；immediate 必须 null | null |

### custom_parameters 精确规则

- 外层只能包含 item_ids 中的键；内层参数名必须存在于该项 `parameters_schema.properties`，缺 schema 时不接受自定义参数。
- 值只允许 string、有限 number、boolean；禁止 object、array、null。0、false、`""` 必须原样保存和渲染。
- 参数名匹配 `^[A-Za-z_][A-Za-z0-9_]{0,63}$`，字符串最长 1000，禁止 NUL、CR、LF。
- 非 URL 字符串拒绝 `;`、`|`、`>`、`<`、`$`、反引号等 shell 控制符。合法 http/https URL 经 URL 解析后允许路径、查询中的 `?`、`&`、`=`、`/`，但不得含凭据、控制符或上述 shell 控制符。
- 渲染必须使用参数数组或上下文安全转义；不能把整个 custom_parameters 字典字符串化入命令。缺省 `{}` 不覆盖测试项默认参数。

### 处理顺序

1. 校验请求结构、item_ids、参数和时间格式。
2. 校验 active 用户、设备存在、owner/PC 和设备可用状态。
3. 校验幂等键及请求摘要。
4. 单事务创建任务或 daily 模板，核对落库。
5. 仅 immediate 在事务提交后启动执行；offline/maintenance 拒绝，testing 允许 pending 排队。

### 成功响应 201

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 201 |
| message | string | 任务创建成功或 daily 模板创建成功 |
| data | Task | 实际落库对象；daily 返回 task_kind=daily_template |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 任务参数不合法 | 空/重复/不存在 item_id、参数结构或值非法、时间非法；details 给字段路径 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期或用户不存在 |
| FORBIDDEN | 403 | 无权限使用此设备 | owner/PC 不满足或用户 disabled |
| NOT_FOUND | 404 | 设备不存在 | device_serial 不存在；item_id 非法按 R14 为 400 |
| CONFLICT | 409 | 任务创建冲突 | 设备 offline/maintenance，或幂等键对应不同请求 |
| INTERNAL_ERROR | 500 | 任务创建失败 | 提交异常；不得有部分落库 |

### 示例

请求：

```json
{"device_serial":"A133P-01","name":"基础测试","item_ids":[12,13],"custom_parameters":{"12":{"target":"8.8.8.8","count":0}},"schedule_type":"immediate","scheduled_time":null}
```

响应（省略的 Task 展示字段不得在实际响应省略）：

```json
{"code":201,"message":"任务创建成功","data":{"id":101,"name":"基础测试","device_serial":"A133P-01","task_kind":"instance","status":"pending","result":null,"total_items":2,"completed_items":0,"counts":{"pass":0,"fail":0,"skip":0,"error":0,"timeout":0},"progress_percent":0,"pass_rate":null,"schedule_type":"immediate","scheduled_time":null,"next_run_at":null,"template_id":null,"scheduled_for":null,"item_snapshot_status":"complete","started_at":null,"completed_at":null,"created_at":"2026-11-09T08:00:00Z"}}
```

错误：

```json
{"code":"VALIDATION_ERROR","message":"任务参数不合法","details":{"field":"custom_parameters.12.count","reason":"不允许嵌套对象、数组或null"}}
```

## 3. GET /api/v1/tasks

### 请求参数

| 字段 | 类型 | 必填 | 默认 | 约束 | 示例 |
|---|---|---|---|---|---|
| status | string | 否 | 不过滤 | 五种任务状态 | completed |
| search | string | 否 | 不过滤 | 去空白后最长 200 | 基础 |
| task_kind | string | 否 | instance | instance/daily_template/all | instance |
| page | integer | 否 | 1 | >=1 | 1 |
| page_size | integer | 否 | 20 | 1～100 | 20 |

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | success |
| data.items | array[Task] | 普通用户仅本人任务，管理员全部 |
| data.total | integer | 过滤后总数 |
| data.page | integer | 当前页 |
| data.page_size | integer | 页大小 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 查询参数不合法 | 状态、类型、分页非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 用户已被禁用 | disabled |
| NOT_FOUND | 404 | 任务不存在 | 列表不使用；无数据返回空列表 |

### 示例

```json
{"code":200,"message":"success","data":{"items":[],"total":0,"page":1,"page_size":20}}
```

```json
{"code":"VALIDATION_ERROR","message":"查询参数不合法","details":{"field":"status","reason":"不支持的任务状态"}}
```

## 4. GET /api/v1/tasks/{id}

无请求体，path id 为正整数。成功 200 的 `data` 为 Task，并增加下表字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| selected_items | array[integer] | 原始选中项顺序 |
| custom_parameters | object | 已校验的嵌套参数 |
| error_message | string/null | 平台异常安全摘要 |
| records | array[TestRecord] | 当前任务记录 |

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 任务ID不合法 | id 非正整数 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 无权限查看此任务 | 非创建者/管理员或 disabled |
| NOT_FOUND | 404 | 任务不存在 | id 不存在 |

```json
{"code":"FORBIDDEN","message":"无权限查看此任务","details":{}}
```

## 5. GET /api/v1/tasks/{id}/records

### 请求参数

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| page | integer | 否 | 1 | >=1 |
| page_size | integer | 否 | 20 | 1～100 |

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | success |
| data.items | array[TestRecord] | 按 selected_items 顺序与记录 ID 稳定排序 |
| data.total | integer | 当前任务记录总数 |
| data.page | integer | 当前页 |
| data.page_size | integer | 页大小 |

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 查询参数不合法 | id 或分页非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 无权限查看此任务 | 非创建者/管理员或 disabled |
| NOT_FOUND | 404 | 任务不存在 | id 不存在 |

```json
{"code":200,"message":"success","data":{"items":[],"total":0,"page":1,"page_size":20}}
```

## 6. POST /api/v1/tasks/{id}/cancellations

取消不是基本 CRUD，以 POST 创建取消结果。请求体固定 `{}`，仅创建者或 active 管理员可操作。

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | 任务已取消 |
| data | Task | status=cancelled、result=null；无 running 残留 |

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 取消请求不合法 | id 非法或正文非空 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 无权限取消此任务 | 非创建者/管理员或 disabled |
| NOT_FOUND | 404 | 任务不存在 | id 不存在 |
| CONFLICT | 409 | 当前状态不可取消 | completed/failed；已 cancelled 的相同操作幂等返回 200 |

幂等采用状态条件更新；执行中取消必须等待子进程终止和记录收尾，再返回成功。未到期 once/daily 模板可取消且不得启动；取消 daily 模板不删除历史实例。

```json
{"code":"CONFLICT","message":"当前状态不可取消","details":{"field":"status","reason":"completed任务不可取消"}}
```

## 7. POST /api/v1/tasks/{id}/reruns

失败重跑创建新实例，请求头幂等规则同任务创建。

### 请求体

| 字段 | 类型 | 必填 | 默认 | 约束 | 示例 |
|---|---|---|---|---|---|
| name | string/null | 否 | 原名加“重跑” | 去空白后 1～200 | 基础测试重跑 |

仅选择原任务 fail/error/timeout 项，保留顺序和对应参数；skip/pass 不重跑。必须重新校验当前设备 owner/PC 与可用状态。

### 成功响应 201

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 201 |
| message | string | 重跑任务创建成功 |
| data | Task | 新 ID、新记录和新报告，不改原任务 |

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 重跑参数不合法 | id/name 非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 无权限重跑此任务 | 任务或设备授权不满足、disabled |
| NOT_FOUND | 404 | 任务或设备不存在 | 原任务/设备缺失 |
| CONFLICT | 409 | 当前任务不可重跑 | 无失败项、设备不可用或幂等键冲突 |

```json
{"code":"CONFLICT","message":"当前任务不可重跑","details":{"reason":"没有fail/error/timeout记录"}}
```

## 8. DELETE /api/v1/tasks/{id}

仅 active 管理员可软删除终态任务或已取消模板。软删除设置 `deleted_at`，默认列表不再返回，历史记录和报告引用保留且可追溯；不做不可恢复的文件整批删除。

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | 任务已删除 |
| data.id | integer | 被软删除任务 ID |
| data.deleted | boolean | true |
| data.artifacts | string | retained，表示证据保留且引用一致 |

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 任务ID不合法 | id 非正整数 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 需要管理员权限 | 非管理员或 disabled |
| NOT_FOUND | 404 | 任务不存在 | id 不存在；已删除任务重放返回 200 |
| CONFLICT | 409 | 当前状态不可删除 | pending/running，防止孤儿执行数据 |

采用 `deleted_at` 条件更新实现幂等。删除前没有 pending/running 记录，且任务、记录、日志与报告保留关系不变。

```json
{"code":200,"message":"任务已删除","data":{"id":101,"deleted":true,"artifacts":"retained"}}
```

## 9. WebSocket /ws/tasks/{task_id}

WS 不是 REST 写接口。accept 后 10 秒内首条文本消息必须为 `{"token":"<JWT>"}`；token 无效、用户不存在/disabled、任务不存在或非创建者/管理员均以 1008 关闭，不推送业务数据。

### 客户端消息

| type/动作 | 字段 | 说明 |
|---|---|---|
| 认证 | token:string | 仅首条；不得放 URL |
| 心跳 | action:"ping" | JSON 文本 |

### 服务端 test_progress

| 字段 | 类型 | 说明 |
|---|---|---|
| type | string | test_progress |
| task_id | integer | 任务 ID |
| device_serial | string/null | 设备序列号 |
| data.total_items | integer | N |
| data.completed_items | integer | C，不含 running |
| data.counts | object | 五类终态计数 |
| data.progress_percent | integer | 与 Task 一致 |
| data.pass_rate | number/null | 与 Task 一致 |
| data.task_status | string | 五种任务状态 |
| data.result | string/null | passed/failed/null |
| data.current_item | TestRecord/null | 当前 running 项，不计完成 |
| data.completed_results | array[TestRecord] | 仅五类终态 |
| timestamp | string | 消息 UTC 时间 |

### 其他消息

| type | 字段 | 说明 |
|---|---|---|
| log | task_id,record_id,line | 一条实时日志，不含认证信息 |
| pong | 无额外业务字段 | 回应 ping |
| error | code,message | 安全错误摘要；鉴权失败直接 1008 |

正常首条响应使用当前 Task 数据构造；卸载、认证失败、任务结束和服务端关闭都必须移除连接。前端卸载还须取消重连 timer，连续进出 5 次不得有重复日志或残留连接。

## 10. Legacy 路径

`/tasks/{id}/cancel`、`/tasks/{id}/rerun-failed` 为 legacy，迁移期间必须委托同一取消/重跑服务。AI 创建入口无论是否保留独立路径，都必须先转换为完全相同的任务创建对象，再调用同一校验、设备授权和幂等服务，不得自行写任务。

**授权顺序（v1.1 新增，2026-11-13 经用户确认）**：AI 入口在确定目标设备后，必须先完成与手动创建完全相同的设备授权校验；**校验通过后才允许读取该设备相关知识条目与调用 LLM**。授权拒绝（403）或设备不可用（409）时，本次请求的知识库读取次数与 LLM 调用次数必须为零。任务对象转换与写入仍统一收口到同一创建服务（v1.0 语义保持）。
