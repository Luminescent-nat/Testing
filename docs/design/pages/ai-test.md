# 页面规格：AITestPage

- 状态：评审版，待用户确认

## 结构

```text
AI测试
├─ 自然语言输入与示例
├─ 提交/清空操作
├─ 规划与降级说明
├─ 创建结果/任务链接
└─ BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary | primary提交，secondary清空/查看任务 |
| 尺寸 | md / lg | md表单操作，lg页面标题与输入区 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 输入和真实能力说明可见 |
| hover | color-primary | 操作有反馈 |
| active | color-primary、color-text-inverse | 只提交一次 |
| focus | color-primary焦点环 | 输入/按钮焦点可见 |
| disabled | color-text-disabled、color-bg-disabled | 空输入或请求中禁用提交 |
| loading | BoundaryState加载、aria-busy | 显示规划进行中，不伪造任务ID |
| empty | BoundaryState空态 | 无规划/空结果明确说明，可修改输入 |
| error | BoundaryState错误态、color-error | 授权/参数/模型错误安全显示 |
| readonly | color-bg-disabled、color-text | 请求中输入只读，防止重复变更 |

## 交互
| 触发 | 反馈 |
|---|---|
| 提交合法文本 | loading并创建，成功展示真实任务链接 |
| 无LLM降级 | 显示degradationMessage，不宣称AI成功 |
| 设备/参数拒绝 | error且无任务链接，保留输入供修改 |
| 清空 | 仅在非loading时清空输入和结果 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 输入、规划和操作单列，长文本自动换行 |
| 768~1024px | 输入与结果纵向排列，操作可并排 |
| >1024px | 输入与规划结果可并列，保持可读宽度 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | 输入有label和字数说明，降级role=status，错误role=alert |
| 键盘 | 输入→提交→清空→任务链接顺序，不自动跳焦 |
| 对比度 | 正文color-text，说明color-text-secondary，错误color-error |
