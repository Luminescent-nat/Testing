# 页面规格：KnowledgePage

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-pages-v1.0-review.md`

## 结构

```text
知识库
├─ 关键词/条目类型/状态筛选与分页
├─ 知识条目列表与详情
├─ 规则预览入口
├─ conditional_rules预览/转换反馈
└─ BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary | primary预览/转换，secondary筛选与查看 |
| 尺寸 | sm / md / lg | sm状态标签，md筛选与列表，lg页面标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 知识条目、预览和转换状态清晰 |
| hover | color-primary、shadow-sm | 条目与预览操作有反馈 |
| active | color-primary、color-text-inverse | 当前条目、筛选和预览状态明确 |
| focus | color-primary焦点环 | 筛选、条目、预览与转换操作可见 |
| disabled | color-text-disabled、color-bg-disabled | 预览/转换中或输入不完整时禁止重复提交 |
| loading | BoundaryState加载、aria-busy | 列表、预览、转换分别显示 |
| empty | BoundaryState空态 | 无条目/搜索无结果/空预览分别说明；空规则不转换 |
| error | BoundaryState错误态、color-error | list/标量根、未知操作符、非法正则等按契约展示字段路径 |
| readonly | color-bg-disabled、color-text | 条目与预览可读，不触发转换写入 |

## 交互
| 触发 | 反馈 |
|---|---|
| 修改筛选/分页 | 更新知识列表与total，失败保留筛选且不伪装空态 |
| 打开规则预览 | 请求conversion-previews，展示固定对象结构和逐项条件 |
| 执行转换 | 仅对合法预览提交conversions，成功后失效并刷新列表 |
| 非法规则/转换失败 | 显示安全字段错误，不写知识或测试资产，保留可修正上下文 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 筛选、列表、详情、预览单列，长文档和正则自动换行 |
| 768~1024px | 列表与详情可切换，预览保持可读宽度 |
| >1024px | 列表与详情/预览可并列，长预览不造成页面横向滚动 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | 筛选有label，预览区有标题，错误aria-describedby，转换结果role=status |
| 键盘 | 筛选→条目→预览→转换顺序；长文档内部滚动不困住Tab |
| 对比度 | 正文color-text，辅助color-text-secondary，错误color-error |
