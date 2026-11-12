# 页面规格：MemoryPage

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-pages-v1.0-review.md`

## 结构

```text
测试记忆
├─ 失败模式/基线/黄金案例页签
├─ 关键词筛选与分页
├─ 当前页签记忆列表
├─ 条目详情与来源摘要
└─ BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary | primary当前页签，secondary筛选与详情入口 |
| 尺寸 | sm / md / lg | sm来源标签，md筛选与列表，lg页面标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 展示当前页签真实记忆及来源，0值原样显示 |
| hover | color-primary、shadow-sm | 记忆条目与详情入口有反馈 |
| active | color-primary、color-text-inverse | 当前页签与选中记忆明确 |
| focus | color-primary焦点环 | 页签、筛选、条目与分页可见 |
| disabled | color-text-disabled、color-bg-disabled | 请求中禁用重复筛选/分页提交 |
| loading | BoundaryState加载、aria-busy | 仅当前页签数据区加载，不清空其他页签状态 |
| empty | BoundaryState空态 | 无记忆/筛选无结果分别说明，可清除筛选 |
| error | BoundaryState错误态、color-error | 保留页签和筛选，失败不误报为空 |
| readonly | 与default一致 | 页面仅查看，无新增、修改或删除操作 |

## 交互
| 触发 | 反馈 |
|---|---|
| 切换页签 | 更新activeTab并请求对应数据，各页签缓存按契约失效 |
| 修改筛选/分页 | 更新当前页签列表与total，查询失败不误报为空 |
| 打开条目 | 查看该页签详情与来源，长文本完整可读 |
| 清除筛选 | 恢复当前页签默认列表，不修改其他页签 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 页签可换行，筛选、记忆、详情单列，长文本自动换行 |
| 768~1024px | 筛选纵向排列，列表与详情可切换 |
| >1024px | 列表与详情可并列，来源长文本不造成页面横向滚动 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | 页签使用tablist/tab/tabpanel语义，筛选有label，详情区域有标题 |
| 键盘 | 页签支持方向键，Tab进入筛选→列表→详情→分页；焦点顺序可预测 |
| 对比度 | 正文color-text，辅助color-text-secondary，错误color-error |
