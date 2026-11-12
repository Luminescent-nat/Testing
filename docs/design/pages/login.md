# 页面规格：LoginPage

- 状态：评审版，待用户确认

## 结构

```text
登录/首管理员卡片
├─ 平台标题与模式说明
├─ 用户名/密码/PC标识表单
├─ 错误提示
└─ 提交与模式切换操作
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary | primary提交，secondary模式说明 |
| 尺寸 | md / lg | md默认，lg用于首管理员初始化标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text、radius-md | 表单标签和输入完整 |
| hover | color-primary | 提交/切换操作可识别 |
| active | color-primary、color-text-inverse | 只提交一次 |
| focus | color-primary焦点环 | 输入和按钮均可见 |
| disabled | color-text-disabled、color-bg-disabled | 必填缺失或请求中禁用提交 |
| loading | color-text-secondary、aria-busy | 保留输入但密码不回显，防止重复提交 |
| empty | color-text-secondary | 空表单显示必填提示，不当作合法请求 |
| error | color-error、color-bg-elevated | 区分凭据/禁用/初始化关闭的安全摘要 |
| readonly | color-bg-disabled、color-text | 请求中字段只读，不能修改已提交内容 |

## 交互
| 触发 | 反馈 |
|---|---|
| 提交合法表单 | loading并调用对应会话/注册资源，成功导航 |
| 提交空/非法表单 | 字段级提示，不发请求 |
| disabled/错误凭据 | error且密码字段可安全重填，不泄露账号存在性 |
| Enter | 与点击提交一致，loading时不重复 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 卡片和按钮占满可用宽度，表单单列 |
| 768~1024px | 卡片居中，说明与表单纵向排列 |
| >1024px | 保持可读卡片宽度，不拉宽密码输入到全屏 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | form标签、autocomplete、aria-describedby错误关联，error使用role=alert |
| 键盘 | 用户名→密码→PC标识→提交顺序，Enter提交，焦点不跳转丢失 |
| 对比度 | 标签/输入使用color-text，辅助用color-text-secondary，错误用color-error |
