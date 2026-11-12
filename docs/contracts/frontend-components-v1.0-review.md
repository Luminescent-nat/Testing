# 前端共享组件契约

- 版本：v1.0-review
- 日期：2026-11-12
- 状态：待用户确认；确认前不得实施这些组件
- 数据来源：除特别说明外均由父组件传入，组件不自行请求
- UI依据：`docs/design/ui-tokens.md` 及各组件六段规格

## StatusTag

职责：统一展示任务与测试项状态，使用文字和图标而非只靠颜色。

### props

| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| status | TaskStatus \| RecordStatus | 是 | 无 | 只接受契约状态枚举 |
| label | string | 否 | '' | 自定义文案；空串使用状态映射 |
| size | 'sm' \| 'md' \| 'lg' | 否 | 'md' | 标签尺寸 |
| showIcon | boolean | 否 | true | 是否显示语义图标 |

### state

| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| 无 | 无 | 无 | 显示全部由props推导 |

### events

| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 纯展示组件不触发事件 |

### 插槽

| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| default | { status, label } | 内置状态中文标签 |
| icon | { status } | 内置状态语义图标 |

## BoundaryState

职责：统一呈现loading/empty/error及可重试反馈，不承载业务数据请求。

### props

| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| kind | 'loading' \| 'empty' \| 'error' | 否 | 'empty' | 边界态类型 |
| title | string | 否 | '' | 主标题；空串使用类型默认文案 |
| description | string | 否 | '' | 安全说明，不接收堆栈 |
| retryable | boolean | 否 | false | 是否显示重试按钮 |
| retryText | string | 否 | '重试' | 重试按钮文案 |
| size | 'sm' \| 'md' \| 'lg' | 否 | 'md' | 容器尺寸 |

### state

| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| 无 | 无 | 无 | 展示由props推导 |

### events

| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| onRetry | void | kind=error且retryable时点击重试或键盘激活 |

### 插槽

| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| icon | { kind } | 内置边界态图标 |
| default | { kind } | 默认说明文本 |
| actions | 无 | retryable时显示默认重试按钮，否则无操作区 |

## MetricCard

职责：展示仪表盘指标并准确保留0与null。

### props

| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| label | string | 是 | 无 | 指标名称 |
| value | number \| string \| null | 是 | 无 | 数值0原样展示，null显示无有效结果 |
| unit | string | 否 | '' | 可选单位，不拼入null |
| trend | number \| null | 否 | null | 可选变化值，0保留 |
| tone | 'primary' \| 'secondary' \| 'danger' | 否 | 'secondary' | 视觉类型 |
| loading | boolean | 否 | false | 是否加载中 |
| error | string \| null | 否 | null | 安全错误摘要 |

### state

| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| 无 | 无 | 无 | 数值和状态由props推导 |

### events

| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 非交互卡片不触发事件 |

### 插槽

| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| icon | { tone } | 无图标 |
| footer | { value, trend } | 无额外底部内容 |

## TaskProgress

职责：统一展示任务进度、五类计数和当前项，不自行管理WS。

### props

| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| taskId | number | 是 | 无 | 正整数任务ID |
| totalItems | number | 是 | 无 | N，非负整数 |
| completedItems | number | 是 | 无 | C，0～totalItems |
| counts | TerminalCounts | 是 | 无 | pass/fail/skip/error/timeout五个非负整数 |
| progressPercent | number | 是 | 无 | 0～100整数 |
| taskStatus | TaskStatus | 是 | 无 | 任务生命周期 |
| result | 'passed' \| 'failed' \| null | 否 | null | 业务结果 |
| passRate | number \| null | 否 | null | 0～100或null |
| currentItem | TestRecord \| null | 否 | null | 当前running项，不计完成 |
| connectionState | 'connecting' \| 'open' \| 'closed' \| 'error' | 否 | 'closed' | WS连接状态 |

### state

| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| 无 | 无 | 无 | 进度完全由props推导 |

### events

| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| onReconnect | void | connectionState=closed/error且用户点击重连 |
| onClose | void | 用户明确关闭实时监控 |

### 插槽

| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| current-item | { item: TestRecord \| null } | 无当前项时显示无执行中项目 |
| actions | { taskId, connectionState } | 默认重连/关闭操作按状态显示 |

## DeviceSelect

职责：展示已授权设备并返回所选serial，不自行发现或认领设备。

### props

| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| devices | Device[] | 是 | 无 | 父组件已授权设备集合 |
| modelValue | string \| null | 是 | 无 | 当前serial，无选择为null |
| loading | boolean | 否 | false | 列表加载态 |
| error | string \| null | 否 | null | 安全错误摘要 |
| disabled | boolean | 否 | false | 禁止所有交互 |
| readonly | boolean | 否 | false | 仅查看当前选择 |
| emptyText | string | 否 | '暂无可操作设备' | 空态文案 |
| compatibilityMap | Record<string, CompatibilityResult> | 否 | {} | 按serial提供兼容结论 |

### state

| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| filterText | string | '' | 用户输入过滤文本；不清空modelValue |

### events

| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| onChange | string | 用户选择另一可用设备serial |
| onRefresh | void | 用户明确点击刷新或键盘激活 |

### 插槽

| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| device-option | { device, compatibility } | 默认serial、型号和兼容标签 |
| empty | 无 | BoundaryState空态 |
| error | { message: string } | BoundaryState错误态 |

## ReportSummary

职责：统一展示五类终态和通过率，不把skip或null误算为通过。

### props

| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| summary | ReportSummaryData | 是 | 无 | total_items与五类计数、pass_rate |
| loading | boolean | 否 | false | 报告加载态 |
| error | string \| null | 否 | null | 安全错误摘要 |
| comparison | ReportSummaryData \| null | 否 | null | 可选对比汇总 |
| showSkipped | boolean | 否 | true | 是否展示skip计数卡片 |

### state

| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| 无 | 无 | 无 | 统计和差值由props推导 |

### events

| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| onExport | 'json' \| 'html' \| 'markdown' \| 'excel' \| 'word' | 用户选择支持的导出格式 |

### 插槽

| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| actions | { formats: ExportFormat[] } | 默认导出格式菜单 |
| comparison | { comparison: ReportSummaryData \| null } | 无对比时显示未选择对比任务 |

## 共享类型约束

`TerminalCounts`、`CompatibilityResult`、`ReportSummaryData`、`ExportFormat` 必须按已确认后端契约定义精确 TypeScript 联合/接口，禁止 any。`Device`、`TestRecord` 使用契约字段，0、false、空串和null不得通过truthy判断丢失。

所有事件只列本表；实现不得新增契约外props/events/slots。可选props均有默认值，必填props无默认值。
