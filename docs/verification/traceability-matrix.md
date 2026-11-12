# R1～R31 全链路追踪矩阵

- 版本：v1.0
- 日期：2026-11-12
- 需求基线：[requirements-v2.3.md](../requirements/requirements-v2.3.md)
- 说明：“计划测试”是尚待实现的验证目标，不是已存在或通过；最终结论必须在阶段 5 用实际结果更新。

| 需求 | 契约/设计 | ADR | 目标实现模块 | 验证与证据 | 当前真实状态 |
|---|---|---|---|---|---|
| R1 | [需求基线](../requirements/requirements-v2.3.md)；[范围决策](../design/solution-comparison.md) | [001](../adr/adr-001-evolutionary-remediation.md) | 文档范围与验收报告生成/维护流程 | 阶段5核对现行引用和历史标识 | 需求已确认；范围验收未执行 |
| R2 | [证据生命周期](../design/scheduler-and-data.md#7-文件与证据生命周期) | [007](../adr/adr-007-evidence-storage-lifecycle.md) | UPFM manifest、seed、导入器、静态矩阵 | 计划核对27项、38源用例及重复/缺失 | 待阶段4；未形成闭环证据 |
| R3 | [报告覆盖字段](../contracts/reporting-v1.0.md#1-report-数据对象) | [007](../adr/adr-007-evidence-storage-lifecycle.md) | 报告构建器、UPFM实机记录 | 静态/实机矩阵及逐项skip原因 | 当前ADB无设备，实机无法核验 |
| R4 | [方案边界](../design/solution-comparison.md) | [001](../adr/adr-001-evolutionary-remediation.md) | 性能与并发验证报告 | 只有实际测量后才更新指标 | 历史指标未验证，不作门禁 |
| R5 | [设备授权](../contracts/device-authorization-v1.0.md)；[任务创建](../contracts/task-execution-v1.0.md) | [002](../adr/adr-002-server-owned-device-authorization.md) | device.py、tasks.py、ai_tasks.py、共享授权策略 | 计划他人/未分配/PC不一致的手动与AI异常用例及无落库核对 | P0待整改 |
| R6 | [发现与改派](../contracts/device-authorization-v1.0.md) | [002](../adr/adr-002-server-owned-device-authorization.md) | device.py、devices.py | 计划普通用户发现/认领/改派、既有owner不变测试 | P0待整改 |
| R7 | [任务归属](../contracts/task-execution-v1.0.md)；[报告授权](../contracts/reporting-v1.0.md) | [002](../adr/adr-002-server-owned-device-authorization.md) | websocket.py、reports.py、认证依赖 | 计划创建者/管理员/他人/disabled/无效token及WS1008 | P0待整改 |
| R8 | [判定优先级](../design/execution-state-machine.md#2-单项判定优先级) | [005](../adr/adr-005-unified-execution-result-model.md) | execution_engine.py、judgement_engine.py | 计划非零、无配置、双模式命中、异常、超时真值表 | P0待整改 |
| R9 | [原生SKIP](../design/execution-state-machine.md#2-单项判定优先级)；[WS](../contracts/task-execution-v1.0.md) | [005](../adr/adr-005-unified-execution-result-model.md) | 执行器、记录、WS、报告、前端状态标签 | 计划独立行/相似文本/rc!=0及全链路skip | P0待整改 |
| R10 | [任务聚合](../design/execution-state-machine.md#3-任务聚合真值表) | [005](../adr/adr-005-unified-execution-result-model.md) | task_executor.py、schemas.py、报告/详情 | 计划正常/失败/全skip/异常/取消/running残留 | P0待整改 |
| R11 | [统一统计](../design/execution-state-machine.md#5-进度与通过率)；[报告](../contracts/reporting-v1.0.md) | [005](../adr/adr-005-unified-execution-result-model.md) | WS、任务API、Dashboard、报告、导出、前端 | 计划2/1/1/2样例、全skip、首项stop及前端断言 | P0待整改 |
| R12 | [Dashboard](../contracts/reporting-v1.0.md#5-get-apiv1dashboardstats) | [005](../adr/adr-005-unified-execution-result-model.md) | dashboard.py、前端仪表盘 | 计划各任务状态分母和null边界 | P0待整改 |
| R13 | [参数规则](../contracts/task-execution-v1.0.md#2-post-apiv1tasks) | [003](../adr/adr-003-atomic-task-creation-contract.md) | tasks.py、task_executor.py、参数渲染器 | 计划0/false/空串、缺省、目标项隔离和实际命令核对 | P0待整改 |
| R14 | [写前校验](../contracts/task-execution-v1.0.md#2-post-apiv1tasks) | [003](../adr/adr-003-atomic-task-creation-contract.md) | tasks.py、schema校验、错误处理器 | 计划每字段非法值、字段路径、合法URL和无新增落库 | P0待整改 |
| R15 | [知识规则契约](../contracts/knowledge-rules-v1.0.md) | [005](../adr/adr-005-unified-execution-result-model.md) | knowledge_converter.py、judgement_engine.py | 计划合法conditions及list/标量/未知操作符/空规则 | P0待整改 |
| R16 | [daily算法](../design/scheduler-and-data.md#2-daily-触发算法) | [004](../adr/adr-004-daily-template-instances.md) | scheduler.py、models、迁移、报告 | 计划两个计划时刻、独立ID/记录/报告、前次running | P0待整改 |
| R17 | [幂等与恢复](../design/scheduler-and-data.md#3-调度验收输入) | [004](../adr/adr-004-daily-template-instances.md) | scheduler.py、唯一约束、启动恢复 | 计划并发10扫描、重启、跨天、非法时间 | P0待整改 |
| R18 | [设备锁状态](../design/scheduler-and-data.md#4-设备锁与状态推进) | [002](../adr/adr-002-server-owned-device-authorization.md) | device.py、task_executor.py、DeviceLock | 计划A执行B排队、旧收尾、ADB失败、刷新/心跳交错 | P0待整改 |
| R19 | [取消/删除](../contracts/task-execution-v1.0.md)；[数据生命周期](../design/scheduler-and-data.md) | [004](../adr/adr-004-daily-template-instances.md)、[007](../adr/adr-007-evidence-storage-lifecycle.md) | tasks.py、执行器、启动恢复、models | 计划各状态取消/删除、409、幂等、引用与孤儿检查 | P0待整改 |
| R20 | [迁移契约](../design/scheduler-and-data.md#5-迁移契约) | [006](../adr/adr-006-additive-verifiable-migrations.md) | database.py、Alembic迁移、备份脚本 | 存量副本升级/约束/回滚/异常及行数哈希 | 未执行迁移演练；P1待整改 |
| R21 | [设备画像字段](../contracts/device-authorization-v1.0.md#2-device-数据对象) | [002](../adr/adr-002-server-owned-device-authorization.md) | 前端兼容性、tasks.py | 计划Android9/10/10.1及各维度/空非法版本 | P1待整改 |
| R22 | [ReportResult](../contracts/reporting-v1.0.md#1-report-数据对象) | [005](../adr/adr-005-unified-execution-result-model.md) | reports.py、报告对比和格式化前端 | 计划重名不同ID、耗时0、值0、无对应项 | P1待整改 |
| R23 | [WS生命周期](../contracts/task-execution-v1.0.md#9-websocket-wstaskstask_id) | [007](../adr/adr-007-evidence-storage-lifecycle.md) | devices页面、monitor.vue、WS客户端 | 计划首屏不扫描、卸载、认证失败、进出5次资源计数 | P1待整改 |
| R24 | [UI token](../design/ui-tokens.md) | [008](../adr/adr-008-dual-theme-tokens-first.md) | theme.scss及后续组件样式 | token已实测核心颜色对比度；T-21做静态走查，页面另复测 | token及扩展项已于2026-11-12确认；实现未开始 |
| R25 | [组件契约](../contracts/frontend-components-v1.0-review.md)；[组件规格](../design/components/status-tag.md)；[验证规则](verification-rules-v1.0.md) | [008](../adr/adr-008-dual-theme-tokens-first.md) | 六个共享组件与各页面 | 组件六段规格、九状态、实际四边界态触发证据 | 6份组件规格已完成评审稿，待用户确认；未实施 |
| R26 | [页面契约](../contracts/frontend-pages-v1.0-review.md)；[页面规格](../design/pages/main-layout.md)；[UI token](../design/ui-tokens.md) | [008](../adr/adr-008-dual-theme-tokens-first.md) | 主布局、14个路由页面、响应式导航与焦点 | 亮暗6宽度截图、Tab、200%、reduced-motion和实测 | 15份页面/布局规格已完成评审稿，待用户确认；未走查 |
| R27 | [部署契约](../design/scheduler-and-data.md#6-干净部署契约) | [006](../adr/adr-006-additive-verifiable-migrations.md) | Dockerfile、.dockerignore、Compose、启动校验、manifest | 干净构建、工具发现、合法/弱密钥启动及缺失APK skip | 未执行Docker验证；P1待整改 |
| R28 | [用户管理](../contracts/user-administration-v1.0.md) | [002](../adr/adr-002-server-owned-device-authorization.md) | users.py、auth.py、前端用户管理、E2E脚本 | 计划首管理员、后续建号、禁用REST/WS；E2E隔离保护已有B01 | 阶段0保护已完成；生产建号闭环待整改 |
| R29 | [证据生命周期](../design/scheduler-and-data.md#7-文件与证据生命周期) | [007](../adr/adr-007-evidence-storage-lifecycle.md) | 清理流程、报告、文档与备份 | B01已有138文件哈希与副本恢复；后续清理逐项清单 | 基线保护有证据；完整治理未完成 |
| R30 | 本矩阵；[契约索引](../contracts/README.md)；[实施方案](../plan/implementation-plan-v1.0.md)；[交接单](stage1-handoff.md) | [ADR索引](../adr/README.md) | 文档、38个任务与交付记录 | 结构/链接检查及阶段5逐条状态更新 | 后端契约与ADR已确认；前端组件/页面评审稿待确认；业务实现未开始 |
| R31 | [stop真值表](../design/execution-state-machine.md#4-stop-on-failure) | [005](../adr/adr-005-unified-execution-result-model.md) | task_executor.py、WS、报告、前端 | 计划5项第2项stop+fail，核对未执行、3skip、50.0% | P0待整改 |

## 阶段 1 矩阵结论

31 项均有上游设计或明确的环境/阶段边界，但这只代表“可追踪”，不代表实现完成。后端接口/状态契约、ADR 和 token 已于 2026-11-12 确认；新增组件/页面契约及规格仍是评审稿。P0 业务缺陷仍全部待整改；R3 实机、R20 迁移、R27 部署、R24～R26 实现与页面走查没有当前通过证据。

开发委派按[实施方案](../plan/implementation-plan-v1.0.md)、[任务清单](../plan/task-board-v1.0.md)和[验证规则](verification-rules-v1.0.md)执行；分包门禁见[交接单](stage1-handoff.md)。
