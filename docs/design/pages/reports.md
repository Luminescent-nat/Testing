# 页面规格：ReportsPage

- 状态：评审版，待用户确认

## 结构

```text
测试报告
├─ 任务选择与导出格式
├─ ReportSummary
├─ 按item_id对齐的报告/对比表
├─ 证据上下文与静态/实机覆盖
├─ 导出反馈
└─ BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary / danger | primary导出，secondary选择/对比，danger仅失败统计 |
| 尺寸 | sm / md / lg | sm状态标签，md表格/表单，lg报告标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 五类终态、0/null、证据字段完整 |
| hover | color-primary、shadow-sm | 任务选择/导出有反馈 |
| active | color-primary、color-text-inverse | 当前主报告/对比报告明确 |
| focus | color-primary焦点环 | 选择、表格和导出菜单可见 |
| disabled | color-text-disabled、color-bg-disabled | exporting或无报告时禁用导出 |
| loading | BoundaryState加载 | 报告和导出分别展示，不预填0% |
| empty | BoundaryState空态 | 无报告/无对应项分别说明 |
| error | color-error、BoundaryState错误态 | 加载/导出失败分开，不泄露路径 |
| readonly | 与default一致，无导出操作 | 报告与证据可读 |

## 交互
| 触发 | 反馈 |
|---|---|
| 选择主/对比任务 | 按task_id读取，按item_id对齐，无对应项标不可对比 |
| 导出 | onExport(format)后生成文件，失败显示错误且防重复 |
| 全skip/零值 | null显示无有效结果，0显示0 |
| 查看覆盖 | 静态与实机分列，skip原因可展开阅读 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 汇总/对比/导出单列，报告表格转卡片或区域内滚动 |
| 768~1024px | 选择与导出可并排，主/对比报告纵向排列 |
| >1024px | 主报告与对比可并列，长字段不截断 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | 表格标题/表头、导出菜单语义、覆盖区region和错误提示 |
| 键盘 | 任务→对比→报告→导出顺序，菜单Escape返回触发按钮 |
| 对比度 | 正文color-text，辅助color-text-secondary，语义色同时配状态文字 |
