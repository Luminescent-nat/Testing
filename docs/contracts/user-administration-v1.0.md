# 接口契约：用户开通与禁用

- 版本：v1.0
- 状态：2026-11-12 用户已确认
- 鉴权：首管理员注册公开；登录公开；其余仅 active 管理员
- 需求：R7、R28

## 1. User 数据对象

| 字段 | 类型 | 说明 |
|---|---|---|
| id | integer | 用户 ID |
| username | string | 唯一用户名，3～50 字符 |
| role | string | admin/user |
| status | string | active/disabled |
| pc_identifier | string/null | PC 分组，不是授权凭证 |
| last_login_at | string/null | 最近成功登录 UTC 时间 |
| created_at | string | 创建 UTC 时间 |

密码和 password_hash 永不出现在响应中。

## 2. POST /api/v1/auth/registrations

首管理员初始化属于注册资源创建。仅数据库无任何用户时允许公开创建，服务端强制 role=admin；已有用户后无论请求角色如何均返回 403，由管理员走 `/users`。

### 请求体

| 字段 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| username | string | 是 | 3～50 字符，首尾无空白 | first-admin |
| password | string | 是 | 6～32 字符；响应不回显 | change-me-now |
| pc_identifier | string | 是 | 1～255 字符 | pc-admin |

请求不接受 role/status，防止首管理员之外自助提权。

### 成功响应 201

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 201 |
| message | string | 首管理员创建成功 |
| data | User | 实际落库用户，role=admin、status=active |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 注册参数不合法 | 字段缺失、长度非法或含 role/status |
| UNAUTHENTICATED | 401 | 认证凭据无效 | 本公开接口不主动返回；供通用鉴权链使用 |
| FORBIDDEN | 403 | 系统已完成初始化 | 已存在任何用户 |
| NOT_FOUND | 404 | 资源不存在 | 保留统一码；本创建接口不以 404 代替初始化冲突 |
| CONFLICT | 409 | 系统正在并发初始化 | 唯一/事务约束发现并发首管理员 |

### 幂等

以“系统仅一个首管理员”的事务条件与用户名唯一约束防并发双管理员；重复提交在已有用户后返回 403，不创建第二个账号。

### 示例

```json
{"username":"first-admin","password":"change-me-now","pc_identifier":"pc-admin"}
```

```json
{"code":201,"message":"首管理员创建成功","data":{"id":1,"username":"first-admin","role":"admin","status":"active","pc_identifier":"pc-admin","last_login_at":null,"created_at":"2026-11-09T08:00:00Z"}}
```

```json
{"code":"FORBIDDEN","message":"系统已完成初始化","details":{}}
```

## 3. POST /api/v1/auth/sessions

登录不是基本 CRUD，使用 POST 创建会话资源并签发 JWT。

### 请求体

| 字段 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| username | string | 是 | 3～50 字符 | operator |
| password | string | 是 | 6～32 字符 | user-pass |
| pc_identifier | string | 是 | 1～255 字符；用于更新本人 PC 分组 | pc-a |

### 成功响应 201

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 201 |
| message | string | 登录成功 |
| data.access_token | string | JWT |
| data.token_type | string | bearer |
| data.expires_in | integer | 有效期秒数 |
| data.user | User | 当前 active 用户 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 登录参数不合法 | 字段缺失或长度非法 |
| UNAUTHENTICATED | 401 | 用户名或密码错误 | 凭据不匹配或用户不存在，不区分泄露 |
| FORBIDDEN | 403 | 用户已被禁用 | disabled 用户不得签发新 token |
| NOT_FOUND | 404 | 会话不存在 | 保留给会话查询/撤销扩展；登录用户不存在统一返回 401 |
| CONFLICT | 409 | 登录状态冲突 | 账号状态并发变更导致无法完成签发 |

### 幂等

登录写 last_login_at 使用同一用户条件更新，不创建业务任务；每次合法登录可签发新会话，不属于重复业务写。禁用检查与密码校验先于 last_login_at 写入。

### 示例

```json
{"username":"operator","password":"user-pass","pc_identifier":"pc-a"}
```

```json
{"code":201,"message":"登录成功","data":{"access_token":"eyJhbGciOiJIUzI1NiJ9.example","token_type":"bearer","expires_in":86400,"user":{"id":2,"username":"operator","role":"user","status":"active","pc_identifier":"pc-a","last_login_at":"2026-11-09T08:00:00Z","created_at":"2026-11-09T07:00:00Z"}}}
```

```json
{"code":"FORBIDDEN","message":"用户已被禁用","details":{}}
```

## 4. POST /api/v1/users

管理员创建后续账号，是唯一正常开通入口。

### 请求体

| 字段 | 类型 | 必填 | 默认 | 约束 | 示例 |
|---|---|---|---|---|---|
| username | string | 是 | 无 | 3～50 字符，唯一 | operator |
| password | string | 是 | 无 | 6～32 字符 | user-pass |
| role | string | 否 | user | admin/user | user |
| status | string | 否 | active | active/disabled | active |
| pc_identifier | string | 是 | 无 | 1～255 字符 | pc-a |

### 成功响应 201

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 201 |
| message | string | 用户创建成功 |
| data | User | 实际落库用户，不含密码 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 用户参数不合法 | 任一字段类型/长度/枚举非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效或过期 |
| FORBIDDEN | 403 | 需要管理员权限 | 非管理员或禁用用户 |
| NOT_FOUND | 404 | 资源不存在 | 保留给后续按 ID 查询；创建不使用 404 表示重名 |
| CONFLICT | 409 | 用户名已存在 | 唯一约束冲突 |

### 幂等与落库

采用用户名唯一约束。并发 10 次创建同名账号至多一行；重放返回 409，不得生成第二个账号或覆盖密码。成功后必须能按 ID 读出相同 role/status/pc_identifier。

### 示例

```json
{"username":"operator","password":"user-pass","role":"user","status":"active","pc_identifier":"pc-a"}
```

```json
{"code":201,"message":"用户创建成功","data":{"id":2,"username":"operator","role":"user","status":"active","pc_identifier":"pc-a","last_login_at":null,"created_at":"2026-11-09T08:00:00Z"}}
```

```json
{"code":"CONFLICT","message":"用户名已存在","details":{"field":"username","reason":"唯一约束冲突"}}
```

## 5. GET /api/v1/users

### 请求参数

| 字段 | 类型 | 必填 | 默认 | 约束 | 示例 |
|---|---|---|---|---|---|
| username | string | 否 | 不过滤 | 最长 50，包含匹配 | oper |
| role | string | 否 | 不过滤 | admin/user | user |
| status | string | 否 | 不过滤 | active/disabled | active |
| page | integer | 否 | 1 | >=1 | 1 |
| page_size | integer | 否 | 20 | 1～100 | 20 |

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | success |
| data.items | array[User] | 当前页用户 |
| data.total | integer | 过滤后的总数 |
| data.page | integer | 当前页 |
| data.page_size | integer | 页大小 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 查询参数不合法 | 枚举或分页非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效或过期 |
| FORBIDDEN | 403 | 需要管理员权限 | 非管理员或禁用用户 |
| NOT_FOUND | 404 | 用户不存在 | 列表不使用；空结果返回 items=[]、total=0 |

### 示例

```json
{"code":200,"message":"success","data":{"items":[],"total":0,"page":1,"page_size":20}}
```

```json
{"code":"FORBIDDEN","message":"需要管理员权限","details":{}}
```

## 6. PATCH /api/v1/users/{id}

管理员局部更新角色或状态，至少提供一个字段。

### 请求体

| 字段 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| role | string | 否 | admin/user | user |
| status | string | 否 | active/disabled | disabled |

### 成功响应 200

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 200 |
| message | string | 用户已更新 |
| data | User | 更新后的实际用户 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 用户参数不合法 | 空对象、未知字段或枚举非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效或过期 |
| FORBIDDEN | 403 | 需要管理员权限 | 非管理员或禁用用户 |
| NOT_FOUND | 404 | 用户不存在 | id 不存在 |
| CONFLICT | 409 | 管理员状态变更冲突 | 会禁用/降级最后一个 active 管理员 |

### 幂等与并发

采用目标状态条件更新；重复 PATCH 到相同 role/status 返回相同用户。事务内重新检查最后一个 active 管理员，防止并发禁用/降级破坏系统管理闭环。禁用后既有 token 的 REST 与新 WS 订阅均须再次检查 active。

### 示例

```json
{"status":"disabled"}
```

```json
{"code":200,"message":"用户已更新","data":{"id":2,"username":"operator","role":"user","status":"disabled","pc_identifier":"pc-a","last_login_at":"2026-11-09T08:00:00Z","created_at":"2026-11-09T07:00:00Z"}}
```

```json
{"code":"CONFLICT","message":"管理员状态变更冲突","details":{"reason":"不能禁用或降级最后一个active管理员"}}
```

## 7. Legacy 与 E2E 边界

`POST /api/v1/auth/register` 和 `/auth/login` 为 legacy，迁移期间必须委托相同初始化、禁用和错误语义。E2E 固定管理员只能由隔离环境脚本创建，不得作为生产默认账号或首管理员绕过路径。
