# 页面规格：TaskCreatePage

- 状态：评审版，待用户确认

## 结构

```text
创建任务步骤流
├─ DeviceSelect与兼容性
├─ 模块/测试项选择
├─ 按item_id参数表单与调度
├─ 字段错误摘要
└─ 上一步/下一步/提交
```

## 变体
| 维度 | 取值 | 说明 |
|---|---|---|
| 类型 | primary / secondary | primary下一步/提交，secondary上一步 |
| 尺寸 | md / lg | md表单项，lg步骤标题和摘要 |

## 状态
| 状态 | 视觉(token) | 说明 |
|---|---|---|
| default | color-bg-page、color-bg-elevated、color-text | 当前步骤与参数归属清晰 |
| hover | color-primary | 可选项/按钮有反馈 |
| active | color-primary、color-text-inverse | 当前步骤和选中项明确 |
| focus | color-primary焦点环 | 所有表单项和步骤操作可见 |
| disabled | color-text-disabled、color-bg-disabled | 不兼容/缺必填/提交中禁止继续或提交 |
| loading | BoundaryState加载、aria-busy | 设备/模块/提交分别显示 |
| empty | BoundaryState空态 | 无设备/测试项说明原因，不创建空任务 |
| error | color-error、字段错误摘要 | details定位到参数路径，合法输入保留 |
| readonly | color-bg-disabled、color-text | 提交中配置只读，不重复写 |

## 交互
| 触发 | 反馈 |
|---|---|
| 选择设备/测试项 | 重新计算兼容性和参数schema，不继承错误参数 |
| 下一步 | 先校验当前步骤，非法则定位首个错误 |
| 提交 | 使用稳定幂等键，成功导航真实任务，重试不重复建单 |
| daily/once切换 | 显示对应时间规则，非法时间在提交前提示 |

## 响应式断点
| 断点 | 行为 |
|---|---|
| <768px | 步骤与表单单列，参数操作占满宽度，长URL换行 |
| 768~1024px | 表单单列/双列自适应，错误摘要不遮挡字段 |
| >1024px | 配置与摘要可并列，步骤流保持可读宽度 |

## 可访问性
| 项 | 约定 |
|---|---|
| role/aria | form/步骤导航、字段label、aria-invalid/describedby、错误汇总role=alert |
| 键盘 | 按步骤Tab，错误定位不造成陷阱，Enter不意外重复提交 |
| 对比度 | 正文/输入color-text，辅助color-text-secondary，错误color-error |
