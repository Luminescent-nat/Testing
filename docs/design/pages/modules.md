# 页面规格：ModulesPage

- 状态：评审版，待用户确认

## 结构

```text
测试模块
├─ 标题与创建操作
├─ 模块导航/列表
├─ 测试项与执行配置摘要
├─ 创建/编辑对话框
└─ 分页与BoundaryState
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary / danger | primary保存，secondary查看，danger删除需权限 |
| 尺寸 | sm / md / lg | sm标签，md表单，lg页面/对话框标题 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-text、color-bg-elevated | 模块/测试项层次清晰 |
| hover | color-primary、shadow-sm | 可选模块和操作有反馈 |
| active | color-primary、color-text-inverse | 当前模块标识明确 |
| focus | color-primary焦点环 | 表单与列表操作可见 |
| disabled | color-text-disabled、color-bg-disabled | submitting或无权限时不写 |
| loading | BoundaryState加载 | 列表/提交分别展示 |
| empty | BoundaryState空态 | 无模块或无测试项分别说明 |
| error | BoundaryState错误态、color-error | 请求失败和字段错误分开 |
| readonly | color-text、color-bg-disabled | 配置可读，表单不写 |

## 交互
| 触发 | 反馈 |
|---|---|
| 选择模块 | 更新activeModuleId并加载测试项 |
| 保存合法表单 | submitting=true，成功后关闭并刷新 |
| 空/非法表单 | 字段提示，不发请求 |
| Escape | 关闭对话框并返回触发按钮 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 模块导航与测试项纵向排列，长名称换行 |
| 768~1024px | 模块导航可折叠，测试项单列 |
| >1024px | 模块导航与测试项并列，配置表格不溢出 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | 导航/列表/对话框语义，表单label和错误描述关联 |
| 键盘 | 模块→操作→测试项→分页顺序，对话框焦点管理 |
| 对比度 | 正文/标签color-text，辅助color-text-secondary，错误color-error |
