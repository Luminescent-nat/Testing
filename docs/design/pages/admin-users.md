# 页面规格：AdminUsersPage

- 状态：评审版，待用户确认

## 结构

```text
用户管理
├─ 用户搜索与创建入口（管理员）
├─ 用户表格（用户名、角色、状态、创建时间）
├─ 创建/编辑对话框
├─ 启停/角色调整操作
└─ BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary / danger | primary创建/保存，secondary查看，danger禁用 |
| 尺寸 | sm / md / lg | sm角色状态标签，md表格/表单，lg页面标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 角色与active/disabled状态明确 |
| hover | color-primary、shadow-sm | 用户操作有反馈 |
| active | color-primary、color-text-inverse | 当前对话框/筛选状态明确 |
| focus | color-primary焦点环 | 表格、表单、确认操作可见 |
| disabled | color-text-disabled、color-bg-disabled | 保存中及最后管理员保护场景禁用冲突操作 |
| loading | BoundaryState加载、aria-busy | 列表与写操作分别显示 |
| empty | BoundaryState空态 | 搜索无结果提供清除条件，不掩盖加载错误 |
| error | BoundaryState错误态、color-error | 权限、重名、最后管理员冲突安全展示 |
| readonly | color-bg-disabled、color-text | 非管理员仅可查看授权范围，不显示管理操作 |

## 交互
| 触发 | 反馈 |
|---|---|
| 创建用户 | 管理员提交用户名/初始密码/角色，成功仅显示必要结果 |
| 启停或改角色 | 二次确认后提交，409最后管理员冲突保留原状态 |
| 禁用当前登录用户 | 成功后会话失效并返回登录，不继续发送管理请求 |
| 表单校验失败 | 按字段定位，密码等敏感输入不回显到日志或错误详情 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 用户表格转卡片，管理操作进入可键盘菜单，对话框单列 |
| 768~1024px | 保留关键列，次要信息进入详情/编辑 |
| >1024px | 完整表格与对话框展示，长用户名不挤压操作区 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | 表格表头、表单label、dialog标题/描述、错误role=alert |
| 键盘 | 搜索→创建→用户→操作顺序；对话框焦点锁定，关闭返回触发按钮 |
| 对比度 | 正文color-text，辅助color-text-secondary，禁用/错误不只靠颜色 |
