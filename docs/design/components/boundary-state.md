# 组件规格：BoundaryState

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-components-v1.0-review.md`

## 结构

```text
BoundaryState容器
├─ 图标区（icon插槽）
├─ 标题
├─ 描述（default插槽）
└─ 操作区（actions插槽或重试按钮）
```

## 变体

| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | secondary / danger | loading/empty用secondary，error用danger；不引入primary/ghost变体 |
| 尺寸 | sm / md / lg | sm用于卡片局部，md用于页面区块，lg用于整页空态；间距取space-3/4/6 |

## 状态

| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-text、color-text-secondary、color-bg | 按kind显示完整标题和说明 |
| hover | 重试按钮使用color-primary与color-text-inverse | 仅可操作按钮有反馈 |
| active | 重试按钮保持color-primary并显示按下语义 | 不重复触发请求 |
| focus | color-primary焦点环、space-1偏移 | 焦点完整可见 |
| disabled | color-text-disabled、color-bg-disabled | 请求中重试按钮禁用 |
| loading | color-text-secondary、加载图标、color-bg | aria-busy，显示“正在加载” |
| empty | color-text-secondary、空态图标、color-bg | 显示明确空原因和可用下一步 |
| error | color-error标题、color-text正文 | 显示安全摘要，retryable时提供重试 |
| readonly | 与default一致，无操作区 | 只读信息不显示重试 |

## 交互

| 触发 | 反馈 |
|---|---|
| kind改变 | 更新图标、标题、说明、role和操作区 |
| 点击/Enter/Space重试 | 触发一次onRetry，父组件进入loading后按钮disabled |
| 网络错误详情 | 仅显示安全message，不显示堆栈或绝对路径 |

## 响应式断点

| 断点 | 行为 |
|---|---|
| <768px | 内容纵向排列，操作区占满可用宽度，长描述自动换行 |
| 768~1024px | 内容居中，图标/文字/操作按space-4纵向排列 |
| >1024px | 保持内容最大可读宽度，不拉宽长文本或按钮 |

## 可访问性

| 项 | 约定 |
|---|---|
| role/aria | loading/empty使用role=status；error使用role=alert；加载容器aria-busy=true |
| 键盘 | 重试按钮按Tab顺序聚焦，Enter/Space激活；无键盘陷阱 |
| 对比度 | 正文使用color-text或color-text-secondary；error使用color-error，均与color-bg满足正文门槛 |
