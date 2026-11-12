# 页面规格：DevicesPage

- 状态：评审版，待用户确认

## 结构

```text
设备管理
├─ 标题、状态筛选、明确发现按钮
├─ 设备列表/卡片（owner、PC、画像、状态）
├─ 分页
├─ 详情/管理员改派对话框
└─ BoundaryState与DeviceSelect复用区
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary / danger | primary发现/改派，secondary筛选，danger仅破坏性操作 |
| 尺寸 | sm / md / lg | sm表格标签，md表单，lg详情标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-text、color-control-border | 只显示授权设备，owner/PC清晰 |
| hover | color-primary、shadow-sm | 行/按钮有操作反馈 |
| active | color-primary、color-text-inverse | 当前筛选/选中设备明确 |
| focus | color-primary焦点环 | 行操作、筛选、发现可键盘到达 |
| disabled | color-text-disabled、color-bg-disabled | 普通用户改派禁用且不请求 |
| loading | BoundaryState加载、aria-busy | 发现与列表加载分别显示 |
| empty | BoundaryState空态 | 无授权设备显示待管理员分配，不自动扫描 |
| error | BoundaryState错误态、color-error | ADB失败不显示为空成功 |
| readonly | color-text、color-bg-disabled | 画像可读，不显示改派写操作 |

## 交互
| 触发 | 反馈 |
|---|---|
| 点击发现 | discovering=true并调用发现一次，失败保留原列表和错误 |
| 管理员改派 | 使用当前version提交，冲突提示重新读取 |
| 筛选/分页 | 更新列表，不修改owner |
| 详情打开/关闭 | 显示画像并正确恢复焦点 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 设备卡片单列，画像折叠展示，操作占满宽度 |
| 768~1024px | 卡片/表格混合布局，长serial换行 |
| >1024px | 表格完整列展示，详情对话框不超出视口 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | 表格/列表名称、对话框aria-modal、状态文字和错误关联 |
| 键盘 | 筛选→发现→列表→分页顺序，对话框焦点圈定/返回 |
| 对比度 | 正文color-text，辅助color-text-secondary，状态用文字和图标 |
