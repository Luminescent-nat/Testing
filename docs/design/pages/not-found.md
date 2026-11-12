# 页面规格：NotFoundPage

- 状态：评审版，待用户确认

## 结构

```text
404页面
├─ 状态标题与说明
├─ 返回首页操作
├─ 返回上一页操作（有历史时）
└─ BoundaryState（可访问性语义）
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary | primary返回首页，secondary返回上一页 |
| 尺寸 | md / lg | md操作按钮，lg状态标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-text、color-bg-elevated | 明确页面不存在，不伪装系统错误 |
| hover | color-primary | 返回操作有反馈 |
| active | color-primary、color-text-inverse | 返回操作激活状态明确 |
| focus | color-primary焦点环 | 两个返回入口均可见 |
| disabled | color-text-disabled、color-bg-disabled | 无浏览历史时禁用返回上一页 |
| loading | 不适用 | 静态404页不显示无意义加载 |
| empty | color-text-secondary | 无可用目标路径时只保留返回首页 |
| error | color-error | 仅在导航失败时提示，仍保留首页入口 |
| readonly | 不适用 | 页面说明只读，返回操作保持可用 |

## 交互
| 触发 | 反馈 |
|---|---|
| 进入未知路由 | 展示404标题与说明，不自动重定向掩盖地址 |
| 返回首页 | 按登录状态导航有效首页，无权限页面不循环跳转 |
| 返回上一页 | 有站内历史时后退，否则禁用并使用首页入口 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 内容居中且操作纵向排列，长路径完整换行 |
| 768~1024px | 内容限制可读宽度，操作可并排 |
| >1024px | 保持居中布局，不放大空白内容或操作尺寸 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | main内唯一h1，说明文本关联标题，导航错误role=alert |
| 键盘 | 标题→返回首页→返回上一页顺序，无键盘陷阱 |
| 对比度 | 标题/正文color-text，说明color-text-secondary，操作满足已确认token要求 |
