# 接口契约：报告、导出与统计

- 版本：v1.0
- 状态：2026-11-12 用户已确认
- 鉴权：JWT Bearer；任务创建者或 active 管理员
- 需求：R3、R7、R10～R12、R22、R29

## 1. Report 数据对象

| 字段 | 类型 | 说明 |
|---|---|---|
| report_version | string | 本契约报告结构版本 2.0 |
| report_id | string | 稳定报告 ID |
| task_id | integer | 独立执行实例 ID |
| task_name | string | 任务名 |
| task_status | string | 五种任务状态 |
| task_result | string/null | passed/failed/null |
| created_at | string | 任务创建 UTC 时间 |
| completed_at | string/null | 任务收尾 UTC 时间 |
| total_duration_seconds | number/null | 数值耗时，0 保留 |
| executor | object | user_id、username、role，始终为任务创建者而非当前查看者 |
| device | object | serial_number、model、brand、android_version、cpu_abi、board |
| summary | ReportSummary | 五类终态与 null 通过率 |
| results | array[ReportResult] | 按 item_id 和记录 ID 稳定排序 |
| execution_context | EvidenceContext | commit、环境和实机证据元数据 |
| coverage | Coverage | 静态与实机覆盖分列 |

### ReportSummary

| 字段 | 类型 | 说明 |
|---|---|---|
| total_items | integer | 当前报告记录总数 |
| pass | integer | pass 数 |
| fail | integer | fail 数，不含 error/timeout |
| skip | integer | skip 数 |
| error | integer | error 数 |
| timeout | integer | timeout 数，不并入 fail |
| pass_rate | number/null | pass/(pass+fail+error+timeout)*100，分母 0 为 null |

### ReportResult

| 字段 | 类型 | 说明 |
|---|---|---|
| item_id | integer | 稳定对比键 |
| item_name | string | 名称仅显示，不作对比键 |
| module_name | string | 模块名 |
| status | string | 五类终态；进行中报告也允许 pending/running 并明确展示 |
| execution_time | number/null | 0 不得转为缺失 |
| reason | string/null | 失败或跳过原因 |
| extracted_data | object/null | 数值 0 保留 |
| output_summary | string/null | 截断日志摘要，空串与 null 不混为通过 |
| actual_result | object/string/null | 结构化结果优先 |
| verdict_basis | string | 判定或跳过依据 |
| suggested_fix | string/null | 可选修复建议 |

### EvidenceContext

| 字段 | 类型 | 说明 |
|---|---|---|
| evidence_status | string | current/legacy；缺元数据历史报告只能 legacy |
| commit | string/null | 当前代码完整 commit；未知为 null |
| environment | string/null | OS、Python/运行时等可复核环境标识 |
| execution_mode | string | mock/adb_readonly/adb_full/unknown |
| device_serial | string/null | 实机序列号 |
| board | string/null | 实际板型 |
| captured_at | string/null | 证据生成 UTC 时间 |

### Coverage

| 字段 | 类型 | 说明 |
|---|---|---|
| static_item_ids | array[string] | 静态覆盖的 T1 项，例如 T1-01 |
| real_item_ids | array[string] | 实际执行且有证据的项，不包含纯静态映射 |
| skips | array[object] | 每项含 item_id、reason；外设/APK/烧录/重启/人工条件如实列出 |

静态 27 项映射不得写入 real_item_ids；没有当前设备时 execution_mode 不得伪写 adb_readonly/adb_full。

## 2. GET /api/v1/reports/{task_id}

无请求体；path task_id 为正整数。缓存文件存在也必须先校验任务归属和 active 状态。

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | success |
| data | Report | 字段见 Report 及嵌套表 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 任务ID不合法 | task_id 非正整数 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 无权限查看报告 | 非创建者/管理员或 disabled |
| NOT_FOUND | 404 | 任务报告不存在 | 任务不存在 |
| INTERNAL_ERROR | 500 | 报告生成失败 | 文件损坏或生成异常；不泄露路径/堆栈 |

### 示例

```json
{"code":200,"message":"success","data":{"report_version":"2.0","report_id":"RPT-20261109-101","task_id":101,"task_name":"基础测试","task_status":"completed","task_result":"passed","created_at":"2026-11-09T08:00:00Z","completed_at":"2026-11-09T08:01:00Z","total_duration_seconds":0,"executor":{"user_id":2,"username":"operator","role":"user"},"device":{"serial_number":"A133P-01","model":"A133P","brand":"allwinner","android_version":"10.1","cpu_abi":"arm64-v8a","board":"a133p"},"summary":{"total_items":2,"pass":1,"fail":0,"skip":1,"error":0,"timeout":0,"pass_rate":100.0},"results":[{"item_id":12,"item_name":"网络","module_name":"WIFI","status":"pass","execution_time":0,"reason":null,"extracted_data":{"latency":0},"output_summary":"ok","actual_result":{"latency":0},"verdict_basis":"断言满足","suggested_fix":null}],"execution_context":{"evidence_status":"current","commit":"627e5f28a16772816d474694f5a96c0a79b4a611","environment":"test","execution_mode":"mock","device_serial":null,"board":null,"captured_at":"2026-11-09T08:01:00Z"},"coverage":{"static_item_ids":[],"real_item_ids":[],"skips":[{"item_id":"T1-06","reason":"无外设，未执行实机项"}]}}}
```

```json
{"code":"FORBIDDEN","message":"无权限查看报告","details":{}}
```

## 3. POST /api/v1/reports/{task_id}/exports

导出不是基本 CRUD，以 POST 创建导出文件资源。

### 请求体

| 字段 | 类型 | 必填 | 默认 | 约束 | 示例 |
|---|---|---|---|---|---|
| format | string | 否 | html | json/html/markdown/excel/word；pdf 不在本轮范围 | excel |

### 成功响应 201

响应体为文件字节，不使用 JSON 外层。

| 响应项 | 类型 | 说明 |
|---|---|---|
| Content-Type | header | 与格式匹配的 MIME；文本显式 UTF-8 |
| Content-Disposition | header | attachment，文件名含 task_id 和正确扩展名 |
| body | bytes | 与 GET Report 完全相同的五类计数、null 通过率、零值和证据字段 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 导出格式不合法 | format 非五种支持值，包括 pdf |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 无权限导出报告 | 非创建者/管理员或 disabled |
| NOT_FOUND | 404 | 任务报告不存在 | 任务不存在 |
| INTERNAL_ERROR | 500 | 报告导出失败 | 渲染/依赖/文件失败 |

### 示例

请求：`{"format":"excel"}`；正常返回 `.xlsx`。错误：

```json
{"code":"VALIDATION_ERROR","message":"导出格式不合法","details":{"field":"format","reason":"仅支持json/html/markdown/excel/word"}}
```

## 4. POST /api/v1/report-exports

批量导出创建聚合报告资源。请求体：

| 字段 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| task_ids | array[integer] | 是 | 1～100 个正整数，无重复 | [101,102] |
| format | string | 否 | 同单任务导出，默认 html | html |

成功 201 返回文件字节和上述响应头；聚合 summary 逐项累加五类状态，再以总 pass 和总有效分母计算 pass_rate，不能平均各任务百分比。任一 task_id 不存在或无权限，整个请求失败，不静默跳过并生成误导性部分报告。

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 批量导出参数不合法 | 空/重复/超限 ID 或格式非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 含无权访问的任务 | 任一任务归属不满足或 disabled |
| NOT_FOUND | 404 | 部分任务不存在 | 任一 ID 不存在 |
| INTERNAL_ERROR | 500 | 批量导出失败 | 聚合或渲染失败 |

```json
{"code":"VALIDATION_ERROR","message":"批量导出参数不合法","details":{"field":"task_ids","reason":"至少一个不重复任务ID"}}
```

## 5. GET /api/v1/dashboard/stats

无请求体。普通用户只统计本人任务及本人 owner+PC 设备，管理员统计全平台；统计 UTC 今日创建任务。

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | success |
| data.today.tasks | integer | 今日创建实例数，不含 daily 模板 |
| data.today.completed | integer | completed 总数 |
| data.today.passed | integer | completed+result=passed |
| data.today.failed | integer | completed+result=failed，不含 cancelled/平台 failed |
| data.today.no_result | integer | completed+result=null，包括全 skip/零记录 |
| data.today.execution_failed | integer | status=failed |
| data.today.cancelled | integer | status=cancelled |
| data.today.pass_rate | number/null | passed/(passed+failed)，分母 0 为 null |
| data.running_tasks | integer | running 数 |
| data.pending_tasks | integer | pending 实例数，不含模板 |
| data.devices.total | integer | 当前授权范围设备数 |
| data.devices.online | integer | online+testing 数 |

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 统计请求不合法 | 含未知查询参数 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 用户已被禁用 | disabled |
| NOT_FOUND | 404 | 统计资源不存在 | 本端点不使用；无数据返回零值/null |
| INTERNAL_ERROR | 500 | 统计生成失败 | 查询异常 |

```json
{"code":200,"message":"success","data":{"today":{"tasks":0,"completed":0,"passed":0,"failed":0,"no_result":0,"execution_failed":0,"cancelled":0,"pass_rate":null},"running_tasks":0,"pending_tasks":0,"devices":{"total":0,"online":0}}}
```

## 6. GET /api/v1/reports/stats/trend

### 请求参数

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| days | integer | 否 | 30 | 1～365 |

成功 200：`data.days` 为 integer，`data.series` 为连续日期数组。每日对象字段为 `date:string`、`total:integer`、`passed:integer`、`failed:integer`、`no_result:integer`、`execution_failed:integer`、`cancelled:integer`、`pass_rate:number/null`。passed/failed 仅取 completed 的有效 result，total 不含模板，pass_rate 分母不含其他状态。

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 统计天数不合法 | days 超出 1～365 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 用户已被禁用 | disabled |
| NOT_FOUND | 404 | 趋势不存在 | 不使用；无数据返回连续零值日期和 null |
| INTERNAL_ERROR | 500 | 趋势生成失败 | 查询异常 |

```json
{"code":200,"message":"success","data":{"days":1,"series":[{"date":"2026-11-09","total":0,"passed":0,"failed":0,"no_result":0,"execution_failed":0,"cancelled":0,"pass_rate":null}]}}
```

## 7. GET /api/v1/reports/stats/by-module

无请求体。成功 200 的 `data.items` 为数组，每项字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| module_id | integer | 稳定模块 ID |
| module_name | string | 显示名 |
| pass | integer | pass 数 |
| fail | integer | fail 数 |
| skip | integer | skip 数，不进通过率分母 |
| error | integer | error 数 |
| timeout | integer | timeout 数 |
| pass_rate | number/null | 统一公式，分母 0 为 null |

排序使用 module_id 稳定升序；null 不参与数值升降比较，统一置后并保留模块。普通用户仅本人实例，管理员全部。

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 统计请求不合法 | 含未知参数 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 用户已被禁用 | disabled |
| NOT_FOUND | 404 | 模块不存在 | 列表不使用；无模块返回空数组 |
| INTERNAL_ERROR | 500 | 模块统计失败 | 查询异常 |

```json
{"code":200,"message":"success","data":{"items":[]}}
```

## 8. Legacy 路径

`/reports/{task_id}/export`、`/reports/batch/export` 和旧报告 summary 字段为 legacy。迁移期间必须委托同一构建器，禁止继续把 timeout 隐藏进 failed、把 skip 算入分母、把 0 显示为“-”或按名称对齐。报告删除默认 retained，不能让导出缓存绕过权限或形成孤儿引用。
