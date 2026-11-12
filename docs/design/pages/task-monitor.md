# 页面规格：TaskMonitorPage

- 状态：评审版，待用户确认

## 结构

```text
任务监控
├─ 任务摘要与StatusTag
├─ TaskProgress
├─ 当前项/五类记录
├─ 实时日志（暂停视图控制）
├─ 重连/关闭操作
└─ BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | secondary / danger | secondary正常监控，danger失败/连接错误 |
| 尺寸 | md / lg | md记录列表，lg任务主进度 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 进度/结果/连接状态一致 |
| hover | color-primary | 重连、关闭、日志控制有反馈 |
| active | color-primary、color-text-inverse | 暂停视图状态明确，不暂停后端任务 |
| focus | color-primary焦点环 | 操作与日志控制可见 |
| disabled | color-text-disabled、color-bg-disabled | 终态或连接中禁止无效重连 |
| loading | BoundaryState加载 | 初始加载与WS重连分别显示 |
| empty | BoundaryState空态 | 无记录/无日志显示真实原因，不伪造skip |
| error | color-error、BoundaryState错误态 | 认证失败/断线明确，最后数据标非实时 |
| readonly | 与default一致，无重连操作 | 可查看日志和记录 |

## 交互
| 触发 | 反馈 |
|---|---|
| 进入页面 | 请求任务后建立一个认证WS，发送首消息token |
| 收到progress/log | 更新统一模型和日志，不重复追加 |
| 卸载/任务结束/认证失败 | 关闭连接、取消timer和监听，禁止无效重连 |
| 暂停日志视图 | 仅停止自动滚动，数据接收语义明确 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 进度/记录/日志单列，长日志在区域内部换行 |
| 768~1024px | 进度与记录纵向排列，日志保持可读高度 |
| >1024px | 记录与日志可并列，状态摘要保持完整 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | TaskProgress语义，连接状态role=status，错误role=alert，日志有可读标签 |
| 键盘 | 重连→记录→日志控制→关闭顺序，无自动焦点跳转或日志播报轰炸 |
| 对比度 | 正文/日志color-text，辅助color-text-secondary，状态同时文字表达 |
