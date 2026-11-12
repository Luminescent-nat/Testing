# 页面规格：TasksPage

- 状态：评审版，待用户确认

## 结构

```text
任务列表
├─ 标题与创建入口
├─ 状态/类型/搜索筛选
├─ 任务表格（StatusTag、进度、结果）
├─ 取消/重跑/删除操作
└─ 分页与BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary / danger | primary创建，secondary查看/重跑，danger删除 |
| 尺寸 | sm / md / lg | sm表格标签，md筛选操作，lg页面标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-text、color-bg-elevated | status/result分离，100%不等于pass |
| hover | color-primary、shadow-sm | 行入口和操作可识别 |
| active | color-primary、color-text-inverse | 筛选/操作状态明确 |
| focus | color-primary焦点环 | 行操作、筛选、分页可见 |
| disabled | color-text-disabled、color-bg-disabled | 不可取消/删除状态禁用且不请求 |
| loading | BoundaryState加载 | 列表与单项写操作分别展示 |
| empty | BoundaryState空态 | 无任务/筛选无结果提供清除筛选 |
| error | BoundaryState错误态、color-error | 保留筛选，允许重试 |
| readonly | color-text、color-bg-disabled | 只显示查看，不显示写操作 |

## 交互
| 触发 | 反馈 |
|---|---|
| 筛选/搜索/分页 | 更新查询并展示total，不混淆模板和实例 |
| 取消/重跑/删除 | 确认后只操作目标ID，成功后刷新实际状态 |
| 操作冲突 | 显示409原因并重新读取，不伪造成功 |
| 打开任务 | 导航详情/监控，保留返回筛选上下文 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 表格转任务卡片，操作折叠为可键盘菜单，长名称换行 |
| 768~1024px | 关键列保留，次要列进入详情 |
| >1024px | 完整表格和批量信息展示，无列内容互换 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | 表格表头、筛选label、操作确认对话框和状态文本 |
| 键盘 | 筛选→创建→任务→操作→分页顺序，菜单/对话框焦点管理 |
| 对比度 | 正文color-text，辅助color-text-secondary，状态同时文字表达 |
