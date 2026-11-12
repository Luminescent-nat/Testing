# 阶段 1 到开发委派交接检查单

- 日期：2026-11-12
- 交接：阶段 1 契约/设计定稿 → 后续开发委派
- 范围：仅文档与任务交接，不代表业务实现、测试回归或最终验收完成
- 上游确认：R1～R31、后端接口/状态契约 v1.0、ADR-001～008、双主题 token v1.0 已获用户确认
- 新增评审物：前端组件/页面四表契约及六段规格已形成，尚待用户确认

## H01 后端、基础设施与 UPFM 开发分包

### 1. 产出物核对

| 必须产出物 | 有/无 | 路径 | 核对结论 |
|---|---|---|---|
| 需求条目清单与用户确认验收标准 | 有 | [requirements-v2.3.md](../requirements/requirements-v2.3.md) | R1～R31 已确认 |
| 架构方案与范围权衡 | 有 | [solution-comparison.md](../design/solution-comparison.md) | 采用方案 C，边界明确 |
| 架构决策 | 有 | [ADR 索引](../adr/README.md) | ADR-001～008 均 accepted |
| 接口定义 | 有 | [后端契约索引](../contracts/README.md) | v1.0 已确认 |
| 设备/任务/用户/报告/知识分契约 | 有 | [设备](../contracts/device-authorization-v1.0.md)、[任务](../contracts/task-execution-v1.0.md)、[用户](../contracts/user-administration-v1.0.md)、[报告](../contracts/reporting-v1.0.md)、[知识](../contracts/knowledge-rules-v1.0.md) | 路径、方法、请求、响应、错误码、示例按分契约执行 |
| 执行状态模型 | 有 | [execution-state-machine.md](../design/execution-state-machine.md) | 判定、SKIP、stop、终态、进度、通过率明确 |
| 数据模型与部署约束 | 有 | [scheduler-and-data.md](../design/scheduler-and-data.md) | daily、锁、迁移、Docker、证据生命周期明确 |
| 双主题 token | 有 | [ui-tokens.md](../design/ui-tokens.md) | v1.0 含扩展 token，已确认 |
| 开发实施方案 | 有 | [implementation-plan-v1.0.md](../plan/implementation-plan-v1.0.md) | 批次、并行和回退边界明确 |
| 独立任务清单 | 有 | [task-board-v1.0.md](../plan/task-board-v1.0.md) | 38 个任务均有依赖、DoD、验证、回退和状态 |
| 验证规则 | 有 | [verification-rules-v1.0.md](verification-rules-v1.0.md) | 自测与独立验收共用，禁止未运行报通过 |
| 需求追踪矩阵 | 有 | [traceability-matrix.md](traceability-matrix.md) | R1～R31 均有目标实现、验证和真实状态 |
| 架构风险与去向 | 有 | [stage1-review.md](stage1-review.md) | ARC-01～07 保留到对应任务，不视为已关闭 |
| 阶段 0/1 实际测试证据 | 有 | [B01](baseline/B01-stage0-isolation-and-baseline.md)、[C01](C01-stage1-contracts-and-design.md) | 189 个既有后端用例是回归基线，不是新契约验收 |

### 2. 下一阶段工作依据核对

| 依据 | 明确性 | 结论 |
|---|---|---|
| R1～R31 验收口径 | 明确 | 逐条按追踪矩阵和验证规则核验 |
| 后端路径/方法/请求/响应/错误码/示例 | 明确 | 以契约 v1.0 为唯一事实来源 |
| owner/PC/disabled/WS 授权 | 明确 | 服务端共享策略，不只隐藏前端按钮 |
| 五类终态、任务 status/result、stop 与统计 | 明确 | 以状态机真值表为准 |
| daily 模板/实例、幂等、恢复和设备锁 | 明确 | 单实例 scheduler/SQLite，不直接多副本扩容 |
| 参数写前校验、知识规则、账号生命周期 | 明确 | 非法输入不得产生部分写入 |
| 迁移、Docker、弱密钥、ADB 参数数组 | 明确 | 只在隔离副本/干净环境验证并保存日志 |
| UPFM 静态与实机边界 | 明确 | 静态/实机覆盖分列，无设备不得冒充实机通过 |
| 回退边界 | 明确 | 每任务独立变更集；迁移只在备份副本演练 |

### 3. 交接结论

**结论：放行。**

放行范围为 T-01～T-19 按任务依赖实施、T-36 在其依赖满足后实施；T-37/T-38 仍须等待全部前置任务及证据。放行不代表这些任务已完成，开发执行者仍须确认接收本交接单及全部链接产物。

## H02 前端基础设施分包

### 1. 产出物与依据核对

| 项目 | 有/无 | 明确性 | 路径/结论 |
|---|---|---|---|
| API 与错误契约 | 有 | 明确 | [后端契约索引](../contracts/README.md)，v1.0 已确认 |
| UI token | 有 | 明确 | [ui-tokens.md](../design/ui-tokens.md)，含扩展 token，已确认 |
| 客户端/mock 任务与验证 | 有 | 明确 | T-20/T-21；mock 必须由 mock-api 按确认契约生成并明确标注 |
| 回退与联调边界 | 有 | 明确 | 客户端/token 可独立回退；真实联调执行契约一致性、错误和边界检查 |

**结论：放行。** 仅放行 T-20、T-21；不得借此提前启动 T-22～T-35。

## H03 共享组件与路由页面实现分包

### 1. 产出物核对

| 必须产出物 | 有/无 | 路径 | 核对结论 |
|---|---|---|---|
| 共享组件四表契约 | 有 | [frontend-components-v1.0-review.md](../contracts/frontend-components-v1.0-review.md) | 6 个组件，props/state/events/插槽齐全，待确认 |
| 页面四表契约 | 有 | [frontend-pages-v1.0-review.md](../contracts/frontend-pages-v1.0-review.md) | MainLayout+14 个路由页面，待确认 |
| 共享组件六段规格 | 有 | [StatusTag](../design/components/status-tag.md)、[BoundaryState](../design/components/boundary-state.md)、[MetricCard](../design/components/metric-card.md)、[TaskProgress](../design/components/task-progress.md)、[DeviceSelect](../design/components/device-select.md)、[ReportSummary](../design/components/report-summary.md) | 6 份均为评审版，待确认 |
| 页面/布局六段规格 | 有 | [MainLayout](../design/pages/main-layout.md)、[Login](../design/pages/login.md)、[Dashboard](../design/pages/dashboard.md)、[Devices](../design/pages/devices.md)、[Modules](../design/pages/modules.md)、[AITest](../design/pages/ai-test.md)、[Tasks](../design/pages/tasks.md)、[TaskCreate](../design/pages/task-create.md)、[TaskMonitor](../design/pages/task-monitor.md)、[Reports](../design/pages/reports.md)、[Memory](../design/pages/memory.md)、[Knowledge](../design/pages/knowledge.md)、[AdminUsers](../design/pages/admin-users.md)、[Profile](../design/pages/profile.md)、[NotFound](../design/pages/not-found.md) | 15份均为评审版，待确认 |
| UI token | 有 | [ui-tokens.md](../design/ui-tokens.md) | 已确认，可作为视觉唯一来源 |
| 页面验证规则 | 有 | [verification-rules-v1.0.md](verification-rules-v1.0.md) | 九状态、四边界态、三断点、键盘和对比度必须实测 |

### 2. 下一阶段工作依据核对

| 依据 | 明确性 | 结论 |
|---|---|---|
| 后端数据字段与状态语义 | 明确 | 已确认后端契约可直接引用 |
| 组件 props/state/events/插槽 | 未确认 | 表格已齐，但用户确认门禁未通过 |
| 页面 props/state/events/插槽与缓存 | 未确认 | 表格已齐，但用户确认门禁未通过 |
| 组件/页面六段视觉与交互规格 | 未确认 | 规格已齐，但用户确认门禁未通过 |
| 实施任务 DoD/验证/回退 | 明确 | T-22～T-35 已列出，但不能越过确认门禁 |

### 3. 交接结论

**结论：不放行。**

| 缺失项 | 责任方 | 解除条件 |
|---|---|---|
| 新组件/页面四表契约和六段规格的用户确认 | 用户确认；文档维护者记录确认状态 | 用户明确确认后，仅更新确认状态/日期和必要变更记录，再复核受影响的 T-22～T-35 |

在确认前，T-22～T-34 不得开始组件或页面实现，T-35 不得以前端工程完成为前提提前签结。允许继续进行不依赖这些文档的 T-20/T-21 和后端任务。

## 总体判定与接收要求

- 本交接为**分包放行**，不是全部 38 个任务的无条件放行。
- 开发执行者接收时必须回复任务编号、契约版本和本交接单路径；发现契约分歧立即暂停，双方确认后版本号增加 0.1 并追加变更记录。
- 每个任务完成后走实现→自测→回归交接，不得直接跳最终验收。
- 最终验收由独立验收方执行，R1～R31 任一不通过或无法核验，总体不通过。
