# 接口契约：设备授权与发现

- 版本：v1.0
- 状态：2026-11-12 用户已确认
- 鉴权：JWT Bearer；禁用用户一律 403
- 需求：R5、R6、R18、R21

## 1. 授权真值表

| 当前用户 | owner_id | PC 分组 | 列表/详情 | 创建任务/AI | 发现/刷新 | 改派 |
|---|---|---|---|---|---|---|
| active 管理员 | 任意 | 任意 | 允许 | 允许，设备仍需可用 | 允许；不改 owner | 允许 |
| active 普通用户 | 本人 | 一致 | 允许 | 允许，设备仍需可用 | 允许；新设备 owner=null | 403 |
| active 普通用户 | 本人 | 不一致 | 403 | 403 | 不可借此改分组 | 403 |
| active 普通用户 | 他人或 null | 任意 | 403 | 403 | 不认领、不改派 | 403 |
| disabled/无效 token | 任意 | 任意 | 403/401 | 403/401 | 403/401 | 403/401 |

普通用户列表只返回本人 owner 且 PC 一致的设备；直接访问不在可见范围内的已存在设备返回 403，与 R5 一致。PC 只作分组防误操作，不代替 owner 授权。

## 2. Device 数据对象

| 字段 | 类型 | 说明 |
|---|---|---|
| id | integer | 设备内部 ID |
| serial_number | string | ADB 序列号 |
| model | string/null | 产品型号 |
| brand | string/null | 品牌 |
| android_version | string/null | 原始 Android 版本；数值化比较由兼容性逻辑处理 |
| sdk_version | string/null | SDK 版本 |
| cpu_abi | string/null | CPU 架构 |
| resolution | string/null | 分辨率 |
| battery_level | integer/null | 0～100 |
| board | string/null | 板型 |
| hardware | string/null | 硬件标识 |
| ddr_info | object/null | DDR 画像 |
| emmc_info | object/null | EMMC 画像 |
| wifi_chip | string/null | Wi-Fi 芯片 |
| bt_chip | string/null | 蓝牙芯片 |
| eth_interfaces | array[string]/null | 以太网接口 |
| features | array[string]/null | 能力特征 |
| status | string | online/offline/testing/maintenance |
| owner_id | integer/null | 服务端分配归属；null 表示待管理员分配 |
| pc_identifier | string | 分组标识，不是授权凭证 |
| version | integer | 乐观并发版本，从 1 开始 |
| last_seen_at | string/null | 最后一次有效探活 UTC 时间 |
| created_at | string | 创建 UTC 时间 |

## 3. GET /api/v1/devices

查询当前用户可见设备。

### 请求参数

| 字段 | 位置 | 类型 | 必填 | 默认 | 约束 | 示例 |
|---|---|---|---|---|---|---|
| status | query | string | 否 | 不过滤 | online/offline/testing/maintenance | online |
| page | query | integer | 否 | 1 | >=1 | 1 |
| page_size | query | integer | 否 | 20 | 1～100 | 20 |

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | success |
| data.items | array[Device] | 当前页设备，字段见 Device 表 |
| data.total | integer | 过滤后的总数 |
| data.page | integer | 当前页 |
| data.page_size | integer | 页大小 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 查询参数不合法 | 状态、页码或页大小非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效或过期 |
| FORBIDDEN | 403 | 用户已被禁用 | disabled 用户 |
| NOT_FOUND | 404 | 资源不存在 | 保留统一资源错误码；本列表正常无数据返回空列表而非 404 |

### 示例

请求：`GET /api/v1/devices?status=online&page=1&page_size=20`

```json
{"code":200,"message":"success","data":{"items":[{"id":1,"serial_number":"A133P-01","model":"A133P","brand":"allwinner","android_version":"10.1","sdk_version":"29","cpu_abi":"arm64-v8a","resolution":null,"battery_level":null,"board":"a133p","hardware":"sun50iw10","ddr_info":null,"emmc_info":null,"wifi_chip":null,"bt_chip":null,"eth_interfaces":[],"features":[],"status":"online","owner_id":2,"pc_identifier":"pc-a","version":1,"last_seen_at":"2026-11-09T08:00:00Z","created_at":"2026-11-09T07:00:00Z"}],"total":1,"page":1,"page_size":20}}
```

```json
{"code":"VALIDATION_ERROR","message":"查询参数不合法","details":{"field":"page_size","reason":"必须位于1～100"}}
```

## 4. GET /api/v1/devices/{serial}

### 请求

| 字段 | 位置 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|---|
| serial | path | string | 是 | 已登记 ADB 序列号 | A133P-01 |

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | success |
| data | Device | 字段见 Device 表 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 设备序列号不合法 | 空串或超长 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效或过期 |
| FORBIDDEN | 403 | 无权限访问此设备 | 非管理员且 owner/PC 不满足，或用户禁用 |
| NOT_FOUND | 404 | 设备不存在 | serial 未登记 |

### 示例

正常响应的 `data` 使用第 3 节同一 Device。错误：

```json
{"code":"FORBIDDEN","message":"无权限访问此设备","details":{"field":"serial","reason":"owner或PC分组不满足"}}
```

## 5. POST /api/v1/device-discoveries

这是一次同步 ADB 发现动作，不是五种基本 CRUD，故以 POST 创建发现结果资源。扫描失败不得返回空设备成功响应，不得把 testing 或排队设备置 offline。

### 请求体

| 字段 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| 无字段 | object | 是 | 固定空对象 | {} |

### 成功响应 201

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 201 |
| message | string | 设备发现完成 |
| data.items | array[Device] | 本次发现并完成只读同步的设备 |
| data.total | integer | items 数量 |
| data.owner_unchanged | boolean | 必须 true，表示发现不改既有归属 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 请求体不合法 | 非空对象或未知字段 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效或过期 |
| FORBIDDEN | 403 | 用户已被禁用 | disabled 用户 |
| NOT_FOUND | 404 | 发现结果不存在 | 仅用于按结果 ID 扩展查询；同步创建无结果时返回 201+空数组 |
| SERVICE_UNAVAILABLE | 503 | ADB 发现失败 | adb 不可执行、超时或返回错误 |

### 幂等与写入

发现结果不是执行实例，无需客户端幂等键；数据库 upsert 以 `serial_number` 唯一约束防重复。普通用户发现新设备时 owner 必须为 null；已有 owner、version 与 PC 不被普通用户发现改写。有效空扫描返回 `items=[]` 且仅对可证明消失且非 testing 的设备推进状态。

### 示例

请求：`POST /api/v1/device-discoveries`，正文 `{}`。

```json
{"code":201,"message":"设备发现完成","data":{"items":[],"total":0,"owner_unchanged":true}}
```

```json
{"code":"SERVICE_UNAVAILABLE","message":"ADB发现失败","details":{"reason":"ADB调用未成功，设备状态未批量变更"}}
```

## 6. PATCH /api/v1/devices/{serial}

仅 active 管理员改派 owner 或调整 PC 分组。

### 请求体

| 字段 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| owner_id | integer/null | 是 | 目标用户必须存在且 active；null 表示取消分配 | 2 |
| pc_identifier | string | 是 | 1～255 字符，去除首尾空白后非空 | pc-a |
| version | integer | 是 | 当前 Device.version | 1 |

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | 设备归属已更新 |
| data | Device | 更新后设备，version 增加 1 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 设备归属参数不合法 | 字段缺失、空 PC 或未知字段 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效或过期 |
| FORBIDDEN | 403 | 需要管理员权限 | 普通用户认领/改派或用户禁用 |
| NOT_FOUND | 404 | 设备或目标用户不存在 | serial/owner_id 无对应记录 |
| CONFLICT | 409 | 设备已被其他操作更新 | version 过期且目标状态并非完全相同 |

### 幂等与并发

采用条件更新：`WHERE id=? AND version=?` 并递增 version，防止并发覆盖。相同 owner_id、pc_identifier 的完全重放即使 version 已旧也返回当前 Device；不同目标携带旧 version 返回 409。

### 示例

```json
{"owner_id":2,"pc_identifier":"pc-a","version":1}
```

```json
{"code":200,"message":"设备归属已更新","data":{"id":1,"serial_number":"A133P-01","model":"A133P","brand":"allwinner","android_version":"10.1","sdk_version":"29","cpu_abi":"arm64-v8a","resolution":null,"battery_level":null,"board":"a133p","hardware":"sun50iw10","ddr_info":null,"emmc_info":null,"wifi_chip":null,"bt_chip":null,"eth_interfaces":[],"features":[],"status":"online","owner_id":2,"pc_identifier":"pc-a","version":2,"last_seen_at":"2026-11-09T08:00:00Z","created_at":"2026-11-09T07:00:00Z"}}
```

```json
{"code":"CONFLICT","message":"设备已被其他操作更新","details":{"field":"version","reason":"请重新读取后提交"}}
```

## 7. Legacy 路径

`POST /api/v1/devices/refresh` 和 `PUT /api/v1/devices/{serial}/status` 是 legacy。迁移期间前者必须委托同一发现服务，后者不得绕过设备锁或 owner 策略；本契约不新增普通用户修改状态的能力。
