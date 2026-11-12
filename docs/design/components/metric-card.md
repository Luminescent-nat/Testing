# 组件规格：MetricCard

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-components-v1.0-review.md`

## 结构

```text
MetricCard容器
├─ 图标区（icon插槽）
├─ 指标标签
├─ 数值与单位
├─ 可选趋势
└─ 底部说明（footer插槽）
```

## 变体

| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary / danger | primary用于重点指标，secondary默认，danger用于失败/异常；类型不改变数值含义 |
| 尺寸 | md / lg | md用于指标组，lg用于首项关键指标；数值字号取font-size-title-md/display |

## 状态

| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-elevated、color-text、radius-md、shadow-sm | 0原样显示，null显示“无有效结果” |
| hover | shadow-md | 仅可点击卡片由父容器提供hover，纯展示不变 |
| active | 与default一致 | 无默认按下行为 |
| focus | 可交互父容器使用color-primary焦点环 | 纯展示卡片不聚焦 |
| disabled | color-text-disabled、color-bg-disabled | 保留真实值，不隐藏指标 |
| loading | color-text-secondary、color-bg-disabled | 显示加载骨架和aria-busy，不显示伪造0 |
| empty | color-text-secondary | 无统计数据时显示“暂无数据”，不同于0 |
| error | color-error、color-bg-elevated | 显示错误摘要，不保留过期成功值冒充当前值 |
| readonly | 与default一致，无hover/active | 数值可读，单位清晰 |

## 交互

| 触发 | 反馈 |
|---|---|
| value=0 | 显示0及合法unit |
| value=null | 显示“无有效结果”，不拼接unit或% |
| error非空 | 卡片进入error，错误文字可读 |
| 点击纯展示卡片 | 无动作 |

## 响应式断点

| 断点 | 行为 |
|---|---|
| <768px | 指标卡片单列，数值/单位不截断，长标签换行 |
| 768~1024px | 两列排列，间距使用space-4 |
| >1024px | 按页面网格多列排列，卡片等高，内容不拉伸数值 |

## 可访问性

| 项 | 约定 |
|---|---|
| role/aria | 使用role=group和可读aria-label；loading时aria-busy=true，null有文本替代 |
| 键盘 | 纯展示不进入Tab；如父组件附加操作，整个操作只有一个Tab入口 |
| 对比度 | 标签用color-text-secondary，数值用color-text，错误用color-error；背景color-bg-elevated需在实际页面复测 |
