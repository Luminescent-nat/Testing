# 阶段 1 契约、ADR 与设计评审报告（C01）

- 初评日期：2026-11-09
- 更新日期：2026-11-12
- 范围：阶段 1 文档、追踪、评审、开发委派包；另修复本轮回归暴露的测试 lifespan 隔离缺口
- 业务代码：未修改
- 阶段结论：核心契约/ADR/token已确认，后端与基础设施分包可委派；新增前端组件/页面评审稿待确认，相关实现不放行

## 1. 交付物

| 类别 | 产物 | 状态 |
|---|---|---|
| 需求 | R1～R31 v2.3 | 已确认，未在本轮另造口径 |
| 方案 | `docs/design/solution-comparison.md`，A/B/C 五维 1/3/5 矩阵 | 方案 C 已定案 |
| ADR | ADR-001～008 与索引 | 五段齐全，全部 accepted，2026-11-12确认 |
| 后端契约 | 通用、设备、任务、用户、报告、知识规则共 6 份 | v1.0，2026-11-12确认 |
| 状态设计 | 执行状态机、调度/数据/部署契约 | 已随核心契约确认，作为实现依据 |
| UI token | 双主题核心色、扩展色与实测对比度 | v1.0及扩展项已于2026-11-12确认 |
| 前端评审契约 | 6个共享组件、MainLayout+14个路由页面的四表 | 评审稿齐全，待用户确认 |
| 前端六段规格 | 6份共享组件、15份页面/布局规格 | 评审稿齐全，待用户确认 |
| 开发委派 | 实施方案、38个任务、DoD、依赖、验证和回退 | 已形成，未开始实施 |
| 交接 | 后端/基础设施、前端基础、组件/页面三个分包门禁 | 前两类放行；组件/页面不放行 |
| 追踪 | R1～R31 到设计、ADR、实现、验证和状态 | v1.0，未将计划写成通过 |
| 架构评审 | 可扩展性/一致性/风险/成本及整改去向 | 有条件通过 |

## 2. 实际验证结果

| 核验 | 实际结果 | 证据 |
|---|---|---|
| 文档结构回归 | 8 ADR、6 契约文档、45 个 JSON 示例、31 条追踪、90 个相对链接；全部通过，无 emoji | `stage1-doc-validation-20261109.log` |
| 最终扩展文档复核 | 首次校验命令误用 POSIX 路径而失败，日志保留；改用 `D:/MCTEST` 后 23 个文件、45 个 JSON、90 链接、31 条追踪全部通过 | `stage1-doc-validation-final-20261109.log`、`stage1-doc-validation-final-rerun-20261109.log` |
| 首次阶段 1 全量后端 | 189 passed、1 条子进程 transport 清理警告，112.15 秒 | `stage1-backend-regression-20261109.log` |
| 执行/日志定向复现 | 18 passed，未在该小集合复现；未据此忽略全量警告 | `stage1-transport-repro-20261109.log` |
| lifespan 隔离断言（修复前） | 按预期 1 failed；直接证明 `main.ADBService()` 不是当前 mock | `stage1-lifespan-isolation-red-20261109.log` |
| WS 修复后定向 | 连续 3 轮均 3 passed，资源警告按 error 处理 | `stage1-lifespan-isolation-green-20261109.log` |
| 最终全量后端 | **189 passed，105.02 秒**；`PytestUnraisableExceptionWarning` 按 error 处理，无警告汇总 | `stage1-backend-regression-final-20261109.log` |
| 开发委派文档首次执行 | 内联命令因Bash引号解析失败未进入校验；独立脚本首跑暴露DoD缩进匹配、并行说明误解析和日志编码问题，失败记录均保留 | [内联失败](stage1-delegation-doc-validation-inline-failure-20261112.log)、[首跑失败](stage1-delegation-doc-validation-20261112.log) |
| 开发委派文档最终回归 | 52个Markdown、45个JSON、162个相对链接、8篇ADR、6份组件规格、15份页面规格、84张四表、38个任务、R1～R31检查通过，退出码0 | [最终日志](stage1-delegation-doc-validation-rerun-20261112.log)、[校验脚本](validate_stage1_docs.py) |

### 测试隔离修正

`mock_adb` 原先替换了设备、执行引擎和画像模块，却遗漏 `app.main` 在导入时绑定的 `ADBService`。TestClient lifespan 心跳因此仍可能创建真实 ADB 子进程。本轮仅修改：

- `backend/tests/conftest.py`：同步 patch `app.main.ADBService`。
- `backend/tests/integration/test_websocket.py`：增加生命周期必须使用当前 mock 的回归断言，保留资源警告 error 门槛。

没有删除或放宽测试来掩盖警告，没有修改设备心跳、执行器、调度或 API 业务语义。

## 3. UI token 实测摘要

使用 WCAG 相对亮度公式实际计算：浅色正文/背景 17.85:1，次级文本 7.58:1，主色按钮文字 5.17:1；暗色分别为 17.06:1、12.02:1、7.02:1。语义色和扩展控件边界的全部组合见 `docs/design/ui-tokens.md`。

这些数值只覆盖列出的静态颜色组合，不代替实际页面、透明度叠加、图表、键盘和断点走查。token及扩展项已于2026-11-12确认；组件和页面规格已形成评审稿，但仍须独立确认，未进入实现。

## 4. 架构评审结论

评审为**有条件通过**：

- 单实例 scheduler/SQLite 是本轮明确部署约束，不得直接多副本扩容。
- legacy 路径只能委托同一服务，不能形成第二套权限或统计语义。
- 存量 owner=null、迁移回滚和证据保护是相关批次强制条件。
- 数据量×10、完整浏览器、Docker、迁移和实机均缺当前证据，保留到对应阶段，不计为通过。

完整整改项与责任角色见 `stage1-review.md`。

## 5. 未覆盖与下一阶段门禁

- 未运行完整 Playwright 正向流程；本阶段未改前端代码，也没有新增 Vitest/lint/build 结果。
- 当前无 ADB 设备，未进行实机识别或 UPFM 实机验收。
- 未执行 Docker 构建、存量库升级/回滚或页面视觉走查。
- 所有 P0 业务缺陷仍待整改，189 个既有测试通过不能证明这些新契约已实现。
- 后端、基础设施与UPFM开发分包以及前端T-20/T-21可按[交接单](stage1-handoff.md)和依赖启动；T-22～T-35仍受新组件/页面文档确认及任务依赖约束。
- 最终验收不由开发人员自签；R1～R31任一不通过或无法核验，总体不通过。

## 6. 2026-11-12 确认与开发委派包

用户已确认核心接口/状态契约、ADR 和 UI token 无异常，并要求输出后续规划、文档和验证规则，后续由本验收方负责独立验收。本轮新增：

| 产物 | 路径 | 当前门禁 |
|---|---|---|
| 开发实施方案 | [implementation-plan-v1.0.md](../plan/implementation-plan-v1.0.md) | 可用于委派 |
| 38个独立任务 | [task-board-v1.0.md](../plan/task-board-v1.0.md) | 全部未开始，逐任务留证据 |
| 开发/验收验证规则 | [verification-rules-v1.0.md](verification-rules-v1.0.md) | 共同执行标准 |
| 组件/页面四表契约 | [组件](../contracts/frontend-components-v1.0-review.md)、[页面](../contracts/frontend-pages-v1.0-review.md) | 待用户确认 |
| 组件/页面六段规格 | `docs/design/components/`、`docs/design/pages/` | 6+15份评审稿，待用户确认 |
| 分包交接单 | [stage1-handoff.md](stage1-handoff.md) | 后端/基础设施放行；组件/页面不放行 |

上述文档只定义后续实现和验收口径，没有修改任务业务代码，没有生成新的前端测试、Docker、迁移、实机或R1～R31通过结论。开发委派文档结构回归的实际结果见第2节；该结果只证明文档结构、契约表格、任务字段和链接检查通过，不替代业务测试与最终验收。
