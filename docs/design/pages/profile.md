# 页面规格：ProfilePage

- 状态：评审版，待用户确认
- 契约：`docs/contracts/frontend-pages-v1.0-review.md`

## 结构

```text
个人中心
├─ 账号摘要（用户名、角色、状态）
├─ 修改密码入口
├─ 修改密码对话框（当前密码、新密码、确认密码）
├─ 操作反馈
└─ BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary | primary修改/确认密码，secondary取消 |
| 尺寸 | md / lg | md表单操作，lg页面标题与账号摘要 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 当前账号资料与修改密码入口明确 |
| hover | color-primary | 修改密码与对话框操作有反馈 |
| active | color-primary、color-text-inverse | 当前对话框与激活操作明确 |
| focus | color-primary焦点环 | 入口、密码输入与保存操作可见 |
| disabled | color-text-disabled、color-bg-disabled | 保存中或必填项不完整时禁用提交 |
| loading | BoundaryState加载、aria-busy | 资料读取与密码修改分别显示 |
| empty | BoundaryState空态 | 账号资料字段缺失显示无数据，不伪造默认值 |
| error | BoundaryState错误态、color-error | 当前密码错误/网络失败安全提示，不回显敏感值 |
| readonly | color-bg-disabled、color-text | 禁用用户或只读状态仅可查看，不允许修改密码 |

## 交互
| 触发 | 反馈 |
|---|---|
| 打开修改密码 | 显示对话框并聚焦当前密码字段 |
| 提交密码修改 | 校验当前密码、新密码和确认密码，成功清空敏感字段并关闭对话框 |
| 会话失效/账号禁用 | 清理会话并返回登录，显示安全原因 |
| 取消/关闭 | 非保存中关闭并清空敏感字段，焦点返回入口 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 摘要与密码对话框单列，操作占满可用宽度，长用户名换行 |
| 768~1024px | 摘要居中限制可读宽度，对话框操作可并排 |
| >1024px | 账号摘要与说明可并列，对话框保持可读宽度 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | dialog有标题/描述，密码输入有label和autocomplete，错误aria-describedby |
| 键盘 | 对话框焦点圈定，Escape在非保存中关闭，关闭后焦点返回入口 |
| 对比度 | 正文color-text，辅助color-text-secondary，错误color-error |
