# 组件规格：ReportSummary

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-components-v1.0-review.md`

## 结构

```text
ReportSummary容器
├─ 总项数与五类终态计数
├─ 通过率（number或null）
├─ 对比区（comparison插槽）
└─ 导出操作区（actions插槽）
```

## 变体

| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | secondary / danger | 有fail/error/timeout时使用danger提示，其余secondary；统计值不随类型改变 |
| 尺寸 | md / lg | md用于报告页，lg用于导出预览；计数font-size-title-md，标题font-size-title-sm |

## 状态

| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-elevated、color-text、语义色计数、radius-md | fail/error/timeout分列，skip不进通过率 |
| hover | 导出按钮使用color-primary/color-text-inverse | 统计数字无hover |
| active | 导出菜单项显示激活反馈并只触发一次onExport | 不重复下载 |
| focus | color-primary焦点环 | 导出按钮和菜单项焦点可见 |
| disabled | color-text-disabled、color-bg-disabled | exporting时禁用导出，统计数据仍可读 |
| loading | color-text-secondary、aria-busy | 显示加载，不先填0% |
| empty | BoundaryState空态 | 无报告显示无执行记录，pass_rate=null |
| error | color-error、BoundaryState错误态 | 导出失败与报告加载失败分开描述 |
| readonly | 与default一致，无导出操作区 | 可查看全部统计，不触发下载 |

## 交互

| 触发 | 反馈 |
|---|---|
| summary更新 | 五类计数与pass_rate同步，0和null分别展示 |
| 选择对比 | comparison插槽展示按item_id关联的差值，无对应项标不可对比 |
| 选择导出格式 | 触发onExport(format)，exporting时禁用操作 |
| 全skip/零分母 | 显示“无有效结果”，不显示0%或100% |

## 响应式断点

| 断点 | 行为 |
|---|---|
| <768px | 计数卡片单列/换行，导出操作占满宽度，长报告名换行 |
| 768~1024px | 计数多列网格，对比区在下方排列 |
| >1024px | 汇总与对比可并列，表格不截断item_id和状态 |

## 可访问性

| 项 | 约定 |
|---|---|
| role/aria | 使用region和可读标题；统计表有表头；导出菜单有aria-label和展开状态 |
| 键盘 | 导出按钮Enter/Space打开，方向键导航，Escape关闭并返回触发按钮 |
| 对比度 | 数值color-text，语义色使用已确认success/warning/error/text-secondary；状态同时有文字 |
