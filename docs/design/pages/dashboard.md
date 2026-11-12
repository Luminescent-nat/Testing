# 页面规格：DashboardPage

- 状态：评审版，待用户确认

## 结构

```text
仪表盘
├─ 页面标题与刷新/趋势范围
├─ MetricCard指标组
├─ 任务趋势图
├─ 模块统计
└─ BoundaryState边界反馈
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary / danger | 由指标语义选择，不改变统计值 |
| 尺寸 | md / lg | md指标组，lg首项与页面标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 各状态分列，pass_rate为number/null |
| hover | shadow-md、color-primary | 仅刷新/筛选和可点击图表有反馈 |
| active | color-primary、color-text-inverse | 范围选择有激活标识 |
| focus | color-primary焦点环 | 操作和图表数据点可键盘访问 |
| disabled | color-text-disabled、color-bg-disabled | 刷新中禁止重复请求 |
| loading | BoundaryState加载、aria-busy | 不预填0或100% |
| empty | BoundaryState空态 | 无任务时显示暂无数据与pass_rate=null |
| error | BoundaryState错误态、color-error | 部分统计失败明确标出，不混用旧值 |
| readonly | 与default一致 | 可查看统计，不显示写操作 |

## 交互
| 触发 | 反馈 |
|---|---|
| 修改趋势范围 | 重新请求对应days并保留连续日期 |
| 明确刷新 | 重新获取统计，loading防重复 |
| null通过率 | 显示“无有效结果”，不是0% |
| 图表键盘导航 | 显示日期、五类状态和null文本 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 指标单列、图表纵向排列，图例可换行，无页面横向滚动 |
| 768~1024px | 指标两列，趋势和模块统计分区排列 |
| >1024px | 指标多列，图表保持可读比例和完整标签 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | main/region标题，图表提供文本数据表，刷新有aria-label |
| 键盘 | 范围→刷新→图表数据表顺序，焦点可见 |
| 对比度 | 数值color-text、辅助color-text-secondary，语义色同时配文字和图例 |
