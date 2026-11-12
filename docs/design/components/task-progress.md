# 组件规格：TaskProgress

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-components-v1.0-review.md`

## 结构

```text
TaskProgress容器
├─ 任务状态与连接状态
├─ 进度条（completedItems/totalItems）
├─ 五类终态计数
├─ 通过率与业务结果
├─ 当前执行项（current-item插槽）
└─ 操作区（actions插槽）
```

## 变体

| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | secondary / danger | 正常执行用secondary；result=failed或平台failed用danger；不新增业务类型prop |
| 尺寸 | md / lg | md用于列表摘要，lg用于监控详情；正文font-size-body，关键进度font-size-title-md |

## 状态

| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-elevated、color-text、color-primary进度、radius-md | 100%不暗示通过，五类计数完整 |
| hover | 操作按钮使用color-primary/color-text-inverse | 进度条本身无hover |
| active | 操作按钮显示按下反馈并防重复触发 | 不影响任务执行 |
| focus | color-primary焦点环 | 重连/关闭操作焦点可见 |
| disabled | color-text-disabled、color-bg-disabled | 连接中或终态时禁止无效重连 |
| loading | color-text-secondary、aria-busy | 初始数据加载，不伪造0%进度 |
| empty | BoundaryState空态、color-text-secondary | totalItems=0显示无执行记录 |
| error | color-error、BoundaryState错误态 | 保留最后有效数据并明确其时间，不冒充实时 |
| readonly | 与default一致，无操作区 | 可查看进度，不能重连/关闭 |

## 交互

| 触发 | 反馈 |
|---|---|
| 收到新props | 更新C、五类计数、进度、result和passRate；currentItem不计C |
| 点击重连 | 触发onReconnect，由父组件管理WS；连接中禁用重复操作 |
| 点击关闭 | 触发onClose，由父组件关闭连接并取消timer |
| totalItems=0 | 显示无执行记录，passRate保持null |

## 响应式断点

| 断点 | 行为 |
|---|---|
| <768px | 状态、进度、计数和操作纵向排列，五类计数可换行，长日志名不横向滚动 |
| 768~1024px | 进度与状态双列，计数在下方换行 |
| >1024px | 主进度与当前项并列，操作区保持可读宽度 |

## 可访问性

| 项 | 约定 |
|---|---|
| role/aria | 进度使用role=progressbar及aria-valuemin/max/now；连接状态role=status；错误role=alert |
| 键盘 | 重连和关闭按Tab顺序，Enter/Space激活；无自动焦点跳转 |
| 对比度 | 正文/计数用color-text，辅助信息用color-text-secondary，错误用color-error；进度颜色同时配文字数值 |
