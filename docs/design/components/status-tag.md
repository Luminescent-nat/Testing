# 组件规格：StatusTag

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-components-v1.0-review.md`

## 结构

```text
StatusTag容器
├─ 语义图标（showIcon=true或icon插槽）
└─ 状态文字（default插槽或状态映射）
```

## 变体

| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary / ghost / danger | 由status语义推导，不新增prop；pass用primary，running/info用secondary，pending/skip用ghost，fail/error/timeout/failed用danger |
| 尺寸 | sm / md / lg | sm用于紧凑表格，md默认，lg用于详情主状态；字号取font-size-caption/small/body |

## 状态

| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | 语义色文字、color-bg-elevated、radius-full、space-2内间距 | 文字与图标同时表达状态 |
| hover | 与default一致 | 非交互标签不制造可点击错觉 |
| active | 与default一致 | 无按下动作 |
| focus | 自身不显示焦点环；交互父容器使用color-primary焦点 | 自身不进入Tab顺序 |
| disabled | color-text-disabled、color-bg-disabled | 仅表示父操作禁用，不改变业务状态文字 |
| loading | color-text-secondary、color-bg-disabled | 显示“状态加载中”和加载图标 |
| empty | color-text-secondary、ghost类型 | 显示“无状态”，不伪造pass或skip |
| error | color-error、danger类型 | 显示“状态不可用”，保留重试入口由父组件提供 |
| readonly | 与default一致，无hover反馈 | 可阅读但不触发任何动作 |

## 交互

| 触发 | 反馈 |
|---|---|
| status改变 | 更新图标、文字、语义色和可访问名称 |
| label非空 | 使用自定义文字，但保留状态语义图标 |
| 鼠标hover/按下 | 无视觉或业务动作 |

## 响应式断点

| 断点 | 行为 |
|---|---|
| <768px | 保持文字可见；在表格中允许换行，不用省略号隐藏关键状态 |
| 768~1024px | 使用sm/md，多个标签按space-2换行排列 |
| >1024px | 按内容自然排列，尺寸不随视口放大 |

## 可访问性

| 项 | 约定 |
|---|---|
| role/aria | 静态文字使用文本语义；动态任务状态容器可用role=status、aria-live=polite，避免多个标签同时播报 |
| 键盘 | 自身不可聚焦；无点击、Enter或Space行为 |
| 对比度 | 文字使用已实测color-text/success/warning/error与color-bg组合；disabled也不以透明度降低可读性 |
