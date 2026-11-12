# 接口契约：知识规则转换

- 版本：v1.0
- 状态：2026-11-12 用户已确认
- 鉴权：预览要求 active JWT；实际转换仅 active 管理员
- 需求：R8、R15

## 1. 可执行 conditional_rules 结构

唯一合法结构为对象，不接受数组或标量：

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| returncode_zero | boolean | 否 | true | true 时非零退出先 fail；全局非零失败规则仍不可关闭 |
| conditions | array[Condition] | 是 | 无 | 至少 1 项，禁止空数组 |

Condition：

| 字段 | 类型 | 必填 | 默认 | 约束 | 示例 |
|---|---|---|---|---|---|
| source | string | 是 | 无 | `regex:<有效正则>`，必须能提取确定标量 | regex:latency=([0-9.]+) |
| operator | string | 是 | 无 | eq/gt/gte/lt/lte/approx_ratio/contains；符号 =/==/>/>=/</<= 在写前规范化为内部名 | gte |
| target | string | 是 | 无 | 字面量或 `spec:<非空键>`；approx_ratio 的数值目标不得为 0 | 100 |
| tolerance | string | 否 | 0% | 非负百分比，仅 approx_ratio 使用 | 5% |
| on_fail | string | 否 | 条件不满足 | 最长 500，不含控制字符 | 延迟低于下限 |

空 conditions、list/标量根结构、非法正则、未知操作符、缺失字段、target 无法解析、approx_ratio 目标为 0 均返回 400。合法结构写入后由判定引擎逐条件执行，全部满足才 pass；任一不满足 fail；无法提取或执行时 error，不得默认 pass。

## 2. POST /api/v1/knowledge/{id}/conversion-previews

生成预览不是基本 CRUD，以 POST 创建预览资源；不得写测试资产。

### 请求体

| 字段 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| target_type | string | 是 | test_item/failure_pattern/baseline/rule | rule |
| extra_hint | string/null | 否 | 最长 1000，不得覆盖系统校验 | 提取网络延迟规则 |

### 成功响应 201

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 201 |
| message | string | 转换预览已生成 |
| data.target_type | string | 与请求一致 |
| data.preview_data | object | 规范化预览；含 conditional_rules 时符合第 1 节 |
| data.has_llm | boolean | 是否实际使用 LLM；false 时不得伪装 AI 成功 |
| data.validation | object | `valid:boolean`、`errors:array`，预览非法时不允许转换 |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 转换预览参数不合法 | target_type、extra_hint 或规则结构非法 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 用户已被禁用 | disabled |
| NOT_FOUND | 404 | 知识条目不存在 | id 不存在 |
| SERVICE_UNAVAILABLE | 503 | 预览服务不可用 | 必需模型调用失败且无有效规则降级结果 |

### 示例

```json
{"target_type":"rule","extra_hint":"提取网络延迟规则"}
```

```json
{"code":201,"message":"转换预览已生成","data":{"target_type":"rule","preview_data":{"target_item_name":"网络延迟","conditional_rules":{"conditions":[{"source":"regex:latency=([0-9.]+)","operator":"gte","target":"100","tolerance":"0%","on_fail":"延迟低于下限"}],"returncode_zero":true}},"has_llm":false,"validation":{"valid":true,"errors":[]}}}
```

```json
{"code":"VALIDATION_ERROR","message":"转换预览参数不合法","details":{"field":"preview_data.conditional_rules.conditions","reason":"至少一个条件且不能使用空规则"}}
```

## 3. POST /api/v1/knowledge/{id}/conversions

实际转换不是基本 CRUD，以 POST 创建转换结果。仅管理员，先完整校验再写库。

### 请求体

| 字段 | 类型 | 必填 | 约束 | 示例 |
|---|---|---|---|---|
| target_type | string | 是 | test_item/failure_pattern/baseline/rule | rule |
| preview_data | object | 是 | 与目标类型 schema 完全匹配；规则按第 1 节 | 见下方示例 |

### 成功响应 201

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 201 |
| message | string | 测试资产转换成功 |
| data.asset_type | string | 实际资产类型 |
| data.detail | object | 实际落库 ID、名称等；规则必须含 target_item_id 和 rules_count |

### 错误码表

| code | HTTP | message | 触发条件 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 转换数据不合法 | 任一字段或条件非法；无任何资产写入 |
| UNAUTHENTICATED | 401 | 认证凭据无效 | token 无效/过期 |
| FORBIDDEN | 403 | 需要管理员权限 | 非管理员或 disabled |
| NOT_FOUND | 404 | 知识条目或目标测试项不存在 | id 或目标项不存在 |
| CONFLICT | 409 | 转换结果冲突 | 唯一资产已存在或目标规则版本已变化 |
| INTERNAL_ERROR | 500 | 转换失败 | 事务异常，全部回滚 |

### 幂等与落库

规则附加使用 `(target_item_id,规则规范化SHA-256)` 唯一约束；相同规则重复转换返回已有结果，不重复附加。测试项/失败模式/基线使用各自业务唯一键约束；冲突不得先删除旧资产。写操作在单事务完成并核对实际落库。

### 示例

```json
{"target_type":"rule","preview_data":{"target_item_id":12,"conditional_rules":{"conditions":[{"source":"regex:latency=([0-9.]+)","operator":"gte","target":"100","tolerance":"0%","on_fail":"延迟低于下限"}],"returncode_zero":true}}}
```

```json
{"code":201,"message":"测试资产转换成功","data":{"asset_type":"rule","detail":{"target_item_id":12,"target_item_name":"网络延迟","rules_count":1}}}
```

```json
{"code":"VALIDATION_ERROR","message":"转换数据不合法","details":{"field":"preview_data.conditional_rules.conditions.0.operator","reason":"未知操作符"}}
```

## 4. Legacy 路径

`/knowledge/{id}/convert/preview`、`/knowledge/{id}/convert` 为 legacy。现有转换 schema 把 conditional_rules 声明为 array，与执行器的对象结构不一致；迁移时必须统一为第 1 节对象，不得继续把 dict 自动包成 list 后写入。
