# 页面规格：MainLayout

- 状态：评审版，待用户确认

## 结构

```text
应用外壳
├─ 跳过导航链接
├─ 侧栏/移动抽屉（品牌、导航、折叠控制）
├─ 顶栏（面包屑、主题切换、用户菜单）
└─ 主内容（default插槽/router-view）
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | secondary | 专业控制台外壳，无其他类型 |
| 尺寸 | md / lg | md用于紧凑桌面，lg用于宽屏；间距只取token |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text、shadow-sm | 导航和主内容层级清晰 |
| hover | color-primary、color-text-secondary | 仅导航/按钮有反馈 |
| active | color-primary、color-text-inverse | 当前路由同时有文字/图标标识 |
| focus | color-primary焦点环 | 所有操作焦点可见 |
| disabled | color-text-disabled、color-bg-disabled | 不可用操作不触发导航 |
| loading | color-bg-page、BoundaryState局部加载 | 用户信息加载不阻塞公开布局 |
| empty | color-text-secondary | 无导航权限时说明原因并提供返回 |
| error | color-error、BoundaryState | 用户状态失败可重试，不显示空白壳 |
| readonly | 与default一致 | 仅隐藏写操作，不影响阅读导航 |

## 交互
| 触发 | 反馈 |
|---|---|
| 折叠/打开导航 | 更新navCollapsed/mobileDrawerOpen，焦点留在触发按钮 |
| 路由变化 | 移动抽屉关闭，主标题获得合理导航上下文 |
| 主题切换 | 亮暗token同步，无闪烁或裸色 |
| Escape | 关闭抽屉/菜单并返回触发按钮 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 侧栏改为抽屉，主内容单列，导航不造成横向滚动 |
| 768~1024px | 侧栏可折叠，顶栏操作换行而非溢出 |
| >1024px | 固定/可折叠侧栏与主内容并列，内容保持可读宽度 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | banner/nav/main语义，抽屉aria-modal与标签，当前页aria-current |
| 键盘 | 跳过链接为首个Tab，抽屉焦点圈定/返回，无键盘陷阱 |
| 对比度 | 正文/导航使用color-text及color-text-secondary，焦点使用color-primary，双主题实测 |
