# 契约 v1.1 实施轮汇总（2026-11-13）

- 依据：[RR-V1-REFINAL-20261112](../reviews/RR-V1-REFINAL-20261112.md)（独立复核，指出 tool_manifest F1~F4 fail-open 与 AI 入口授权顺序/收口未闭合、全量回归不稳定）与用户确认的契约 v1.1（[CHANGES-DRAFT-v1.1-20261113](../../contracts/CHANGES-DRAFT-v1.1-20261113.md) 已落地：scheduler-and-data §6.1 A1~A5、task-execution §10 AI 授权顺序、contracts README v1.1）
- 交付方式：Agent Team 四路并行，每项严格「先反例（红）后实现（绿）」，独立评审逐项验收（[RR-V11-PLAN](../reviews/RR-V11-PLAN-20261113.md)、RR-V11-FIX-A/B/C、[RR-V11-FINAL-20261113](../reviews/RR-V11-FINAL-20261113.md)）

## 1. 最终回归（门禁基线）

| 项 | 结果 | 日志 |
|---|---|---|
| 全量连续 2 轮（execution-engine，task-25 收口） | **467 passed / 0 failed ×2**（224.83s / 255.66s，无排除项） | tasks/T-14/v1.1-pytest-full-r1.log、r2.log |
| Lead 独立验证轮 | 见 [V11-FINAL-STRICT-LEAD-20261113.log](tasks/V11-FINAL-STRICT-LEAD-20261113.log) | 同左 |
| v2 反例永久基线 | 7/7 passed（[RR-V11-FIX-A](../reviews/RR-V11-FIX-A.md) 独立复核） | reviews/evidence |
| manifest-failopen F1~F4 销项 | **9/9 ALL CLOSED**（修复后全项抛错） | tasks/T-17/manifest-failopen-repro-v2-20261113.log |
| cancel 稳定性 | 模块级 20 连跑×双路径 + 并发 10×2 多轮全绿 | tasks/T-14/v1.1-green-stability-run1~4.log |
| export 稳定性 | 20 连跑（混合缓存/现算）+ 并发重写 20 轮全绿 | tasks/T-08/ |

## 2. 逐项闭环（对照实施方案）

| 方案项 | 缺陷 | 修复 | 验收 |
|---|---|---|---|
| task-A（P0） | F1 sha256 可选、F2 tools:{} 绕过缺口、F3 undeclared 降级无校验/无闭包、F4 非法路径静默丢弃 | [tool_manifest.py](../../test-platform/backend/app/services/tool_manifest.py)：A1 host/shared sha256 必填；A2 空段判 declaration_gaps；A3 未声明 `{host_tool_dir}` 引用硬失败并废除降级；A4 非法路径抛错含原始值；A5 空 tools 根拒绝启动 | GWT A1~A7 逐条 + 真实仓库 ok=true（零迁移成本）；[RR-V11-FIX-A](../reviews/RR-V11-FIX-A.md) 通过 |
| task-B（P0） | AI 入口授权前读知识/调 LLM；未复用统一创建服务（自写落库/设备状态推进） | NLTaskPlanner 拆 resolve_device / plan_for_device；ai_tasks 改「授权 403→状态 409→知识/LLM→统一服务」；新建 [task_creation.py](../../test-platform/backend/app/services/task_creation.py) 手动/AI 共用（幂等独立 operation、201、plan 快照）；B1/B2 计数=0、B3 差分逐字段 | GWT B1~B3 逐条；[RR-V11-FIX-B](../reviews/RR-V11-FIX-B.md) 通过 |
| task-C（P1） | test_export_report_html 偶发空响应；test_cancel_running_task_keeps_cancelled 偶发 running | export：根因=写时截断+后台重写竞窗，临时文件+fsync+os.replace 原子替换+读侧重试（缓存契约 TC-RPT-011 未放宽）；cancel：状态推进全条件更新（输掉竞态零写入、不调度报告/记忆体）、cancel 端点预检后条件更新+幂等保持、收尾移出异常作用域（根治 CancelledError 钉帧致收尾 BUSY）、cancel_task 单次投递、conftest WAL+busy_timeout（Lead 授权） | export 20 连跑+并发重写 20 轮；cancel 20 连跑双路径+并发 10；[RR-V11-FIX-C](../reviews/RR-V11-FIX-C.md) 通过 |
| task-D（P1） | build 与 compose 验证镜像分裂 | docker-compose.yml app 补 `image: test-platform:v1-08-check` 与 check_image_tools --tag 对齐（静态 15/15 PASS；docker 运行时仍 UNVERIFIABLE 如实） | 同 task-A 记录 |

## 3. 交付门禁核对（reviewer 验收标准）

| 门禁 | 状态 |
|---|---|
| 先红后绿、禁止改旧断言造全绿 | 通过（A1~A5 红 8F/15P→绿 23P；B1/B2 红 3F→绿；C1/C2 红证留档；既有断言零放宽） |
| 严格全量连续 2 轮 0 failed | 通过（467×2，无排除项；Lead 另行独立验证轮） |
| v2 反例基线 7/7 | 通过（独立复核） |
| manifest-failopen 全项销项 | 通过（9/9 CLOSED，原审计文件原样留档） |
| B1/B2 计数断言输出 | 通过（knowledge/llm 计数=0 独立重跑） |
| B3 差分断言 | 通过（逐字段一致，plan 仅 AI 行） |
| cancel 20 连跑+并发 10 | 通过（双路径+混发，多轮） |
| export 20 连跑 | 通过（混合两路径+并发重写） |
| 契约 v1.1 文本实施中未被改动 | 通过（G9，每轮复核 git diff docs/contracts = 空） |

## 4. 仍不通过/待用户确认（延续项，不在本轮范围）

| 项 | 状态 |
|---|---|
| R27 Docker 干净构建/容器启动 | 主机无 docker，无法核验（静态对齐已 15/15） |
| 真实库结构漂移对账（A/B） | 需用户选择后方可真实库升级 |
| V1-11 mock-api 缺失（U1）、lint 994w、浏览器 console/页面走查（T-22～T-35） | 未闭环 |
| V1-12 A133P 画像口径与 32 位/ABI 矩阵 | 待用户确认 |
| V1-13 文档回归 26 errors | 未修 |
| U-D1 缺失 Idempotency-Key 不强幂等 | 待用户确认是否强制 400 |
| 配置导入 R32~R59/A32~A59 与 D1~D9 | 需求草案待用户逐项确认，未开发 |
| T-09 参数矩阵、T-11/T-12 daily、T-13 设备锁探活推进、T-16 账号闭环、T-36 画像实测、T-37/T-38 文档与最终验收 | 未实施 |

## 6. 交付后缺陷闭环（2026-11-13，RR-V11-REVIEW §2）

- 独立复核发现：task-B 将 AI 创建响应从旧 `{task_id,plan,device_serial}`/200 改为契约 Task 对象/201 后，前端 `ai-test/index.vue` 未同步——`res.data.task_id` 导致跳转 `/tasks/monitor/undefined`、预览面板读 `planResult.plan.*` 运行期 TypeError（前端无该视图测试覆盖，build/lint 检不出）。
- 修复（[task-28](../../docs/verification/tasks/T-04/)）：导航改 `extractCreatedTaskId(res.data)`（仅正整数 id，非法不跳转并提示）；预览面板按产品决策**保留**，改为创建成功后 `getTaskDetail(id)` 拉 `TestTaskDetail.plan` 渲染，plan 为 null/缺失显示「该任务无规划快照」，详情失败兜底不阻塞跳转；新增 `src/utils/aiTask.js` 纯函数 + 9 条 Vitest（id/plan 各边界）。
- 验证：npm test **65 用例全绿**、lint **992w/0e（较上轮 −2、零新增）**、build exit 0；独立评审闭环通过。
- **reviewer 本轮（契约 v1.1 实施轮）最终签收：通过**（[RR-V11-REVIEW §4](../reviews/RR-V11-REVIEW-20261113.md)）；范围外维持项单列，整体 V1.0 生产上线结论仍为「不通过/受控开发基线」。

## 7. 结论

- RR-V1-REFINAL 指出的两类 P0 未闭合项（tool_manifest F1~F4 机制层 fail-open、AI 入口授权顺序/创建收口）已按契约 v1.1 全部关闭，并通过先红后绿 + 独立评审 + 门禁基线验证。
- 全量回归不稳定（export/cancel 两类竞态）已根治并以稳定性回归固化；门禁可信度恢复（连续 2 轮 0 failed + Lead 独立验证轮）。
- **总体结论维持：不具备完整 V1.0 生产上线条件（受控开发基线）**——剩余阻塞为环境（Docker/真实库对账）、门禁（V1-11/12/13）与未实施任务清单，均为范围外或需用户确认项。
