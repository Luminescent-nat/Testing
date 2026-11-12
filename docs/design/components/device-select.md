# 组件规格：DeviceSelect

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-components-v1.0-review.md`

## 结构

```text
DeviceSelect容器
├─ 标签与当前选择
├─ 下拉列表
│  ├─ 过滤输入
│  └─ 设备选项（serial/型号/兼容性）
├─ loading/empty/error边界区
└─ 明确刷新按钮
```

## 变体

| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | 无变体 | 使用统一表单控件样式，错误/兼容状态由内容表达 |
| 尺寸 | sm / md / lg | sm用于紧凑筛选，md用于表单，lg用于主创建流程；字号取font-size-small/body/title-sm |

## 状态

| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg、color-text、color-control-border、radius-sm | 显示当前serial和兼容结论 |
| hover | color-primary边框与选项高亮 | 仅可选设备有hover |
| active | color-primary、color-text-inverse用于已选项 | 选择后触发onChange并关闭列表 |
| focus | color-primary焦点环 | 输入、选项和刷新均可见 |
| disabled | color-text-disabled、color-bg-disabled | 不打开列表、不刷新、不改值 |
| loading | color-text-secondary、加载图标 | 保留旧选择但标加载，不伪造设备列表 |
| empty | BoundaryState空态 | 显示emptyText和明确刷新，不自动扫描 |
| error | color-error、BoundaryState错误态 | 显示安全错误和重试，不能把失败当空设备 |
| readonly | color-bg-disabled、color-text | 可查看serial，不打开列表或刷新 |

## 交互

| 触发 | 反馈 |
|---|---|
| 打开列表/输入过滤 | 仅在当前devices内过滤，filterText不清空选择 |
| 选择可用设备 | 触发onChange(serial)，更新modelValue由父组件完成 |
| 点击刷新 | 触发onRefresh，父组件明确调用发现；loading时禁用重复刷新 |
| 兼容性未知/不匹配 | 显示原因并禁止提交不兼容项，仍可查看信息 |
| error重试 | 由父组件重新请求列表或发现，不自动认领设备 |

## 响应式断点

| 断点 | 行为 |
|---|---|
| <768px | 控件和刷新按钮占满宽度，选项serial/画像换行显示 |
| 768~1024px | 控件与刷新按space-2排列，下拉不超出视口 |
| >1024px | 保持表单网格宽度，长serial可完整查看，不造成页面横向滚动 |

## 可访问性

| 项 | 约定 |
|---|---|
| role/aria | 使用combobox/listbox/option语义，aria-expanded/controls/selected完整；错误aria-describedby关联 |
| 键盘 | 上下键移动、Enter选择、Escape关闭并还原因未确认选择、Tab顺序到刷新；无键盘陷阱 |
| 对比度 | 文字color-text、边界color-control-border、焦点color-primary；兼容性同时显示文字而非仅颜色 |
