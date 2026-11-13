# 独立评审记录索引与统一模板

- 维护人：reviewer（独立评审方，Team teammate）
- 创建日期：2026-11-12
- 职责：对批次 G 各任务（T-01/T-02/T-06/T-17/T-18/T-19/T-20/T-21）及评审范围内的计划/契约/设计文档做独立评审；不修改任何业务代码、测试、docs/plan、Dockerfile。
- 可写范围：仅本目录（`docs/verification/reviews/`，含 `evidence/` 子目录）。
- 原则：所有结论可追溯到原始证据；未执行项只能写"未执行/无法核验"，不得写通过。

## 1. 评审记录清单

| 编号 | 评审对象 | 日期 | 结论 | 记录文件 |
|---|---|---|---|---|
| RR-000 | 计划/契约/设计文档疑问项清单（阶段一） | 2026-11-12 | 待用户确认项 6 项，其余为记录在案风险 | [RR-000-plan-questions.md](RR-000-plan-questions.md) |
| RR-ADB-001 | ADB 真机（A133P, serial 5c000c2834414751c9d）只读兼容性/可靠性审计（阶段一） | 2026-11-12 | 有条件通过（记录 2 项高风险画像偏差，实机执行项不在本轮） | [RR-ADB-001-device-compatibility.md](RR-ADB-001-device-compatibility.md) |
| RR-T01 | T-01 统一错误外层与目标路由适配 | 2026-11-12 | 通过（DoD 达成；503 生产触发待 T-13、500 生产路径/501 归类/reason 语言为遗留限制） | [RR-T01-unified-errors.md](RR-T01-unified-errors.md) |
| RR-T02 | T-02 Alembic 与外键迁移基础 | 2026-11-12 | **不通过（增补后维持）**：R20 回滚数据保留不成立；备份恢复不能替代 alembic 回滚证据；干净库 FK 启动回归已修复；task-3 reopen | [RR-T02-migration-fk.md](RR-T02-migration-fk.md) |
| RR-T06 | T-06 失败关闭与原生 SKIP 判定 | 2026-11-12 | 通过（状态机行3-11 逐条落地；2 条旧单测为更严契约变更；报告/WS 贯通限代码+record 层；最终严格全量 310 passed） | [RR-T06-failure-closed-skip.md](RR-T06-failure-closed-skip.md) |
| RR-T17 | T-17 干净镜像工具 | 2026-11-12 | 有条件通过 / Docker 运行时无法核验（静态 10/10+7 单测通过；R27 未核验） | [RR-T17-clean-image-tools.md](RR-T17-clean-image-tools.md) |
| RR-T18 | T-18 弱密钥拒绝 | 2026-11-12 | 通过（host 启动矩阵 8 弱拒绝/合法+fresh healthy；容器内 compose 展开未核验） | [RR-T18-weak-secret.md](RR-T18-weak-secret.md) |
| RR-T19 | T-19 ADB runner 去 shell 拼接 | 2026-11-12 | 通过（shell=False 全参数化；shell(str) 兼容；真机只读 7/7；25 单测 pass） | [RR-T19-adb-runner.md](RR-T19-adb-runner.md) |
| RR-T20 | T-20 前端契约客户端与 mock | 2026-11-12 | 有条件通过（P-T20-2/3 已修复并增量复核通过；唯一剩余条件为 mock-api 偏差 U1，待用户最终确认） | [RR-T20-frontend-client-mock.md](RR-T20-frontend-client-mock.md) |
| RR-T21 | T-21 UI token 映射 | 2026-11-12 | 通过（静态 token 范围；页面级视觉留 T-22+） | [RR-T21-ui-tokens.md](RR-T21-ui-tokens.md) |
| RR-FINAL-batch-G | 批次 G 整体评审 | 2026-11-12 | **整体验收不通过**（阻塞：T-02/R20 不通过、T-17/R27 无法核验；T-20 mock 偏差待确认；实机仅 Android10/32 位） | [RR-FINAL-batch-G.md](RR-FINAL-batch-G.md) |
| RR-V1-PLAN-20261112 | V1 readiness 修订阶段一（基线复现+修复映射） | 2026-11-12 | 基线确证：6 项反例在当前 HEAD 全部 FAILED；修复映射建立；诚实边界已列 | [RR-V1-PLAN-20261112.md](RR-V1-PLAN-20261112.md) |
| RR-V1-FIX-T20 | V1-10 前端 2xx 判定与 pc_identifier（task-14） | 2026-11-12 | 通过（残留 0、43 用例、lint 1037w/0e、pc_identifier 仅注入；前端最终门禁属 V1-11） | [RR-V1-FIX-T20.md](RR-V1-FIX-T20.md) |
| RR-V1-FIX-T06T07 | V1-02/03/07 判定/stop/执行器异常（task-10） | 2026-11-12 | 通过（R3/R4/R5 转 PASS；67 passed；写入侧 400 与统一聚合属后续/V1-06） | [RR-V1-FIX-T06T07.md](RR-V1-FIX-T06T07.md) |
| RR-V1-FIX-T03T04T05 | V1-01/07 设备与 WS 统一授权（task-9） | 2026-11-12 | 通过（R1 转 PASS；17 passed；设备发现/改派未做→V1-01 部分未闭环） | [RR-V1-FIX-T03T04T05.md](RR-V1-FIX-T03T04T05.md) |
| RR-V1-FIX-T02 | V1-04/05 幂等模型与迁移闭环基础（task-11） | 2026-11-12 | 通过（新装仅 alembic 幂等；002 可逆回滚 10/98 保留→R20 revision 级通过；真实库漂移需用户对账） | [RR-V1-FIX-T02.md](RR-V1-FIX-T02.md) |
| RR-V1-FIX-T10 | V1-04 幂等+201 入口（task-12） | 2026-11-12 | 有条件通过（R2 转 PASS、9 用例；缺失键/offline 400→409 偏差，后者阻塞完全闭环） | [RR-V1-FIX-T10.md](RR-V1-FIX-T10.md) |
| RR-V1-FIX-T15 | V1-09a 知识规则写前校验（task-18） | 2026-11-12 | 通过（400 零写入/details.field 精确；V1-09 残余：目标 404、DB 唯一、test_item list 透传） | [RR-V1-FIX-T15.md](RR-V1-FIX-T15.md) |
| RR-V1-FIX-T08 | V1-06 统一统计口径（task-16） | 2026-11-12 | 通过（单一 statistics.py 复用；9 用例；Dashboard today 形状待 task-20、前端待 task-21） | [RR-V1-FIX-T08.md](RR-V1-FIX-T08.md) |
| RR-V1-FIX-T19V1-01 | V1-01 补全：发现/改派/Device.version+003（task-19） | 2026-11-12 | 通过（14 用例+003 演练 16/16；V1-01 主体闭环；真机发现/真实库迁移无法核验） | [RR-V1-FIX-T19V1-01.md](RR-V1-FIX-T19V1-01.md) |
| RR-V1-FIX-T08B | V1-06 收口：Dashboard 分列+前端统计显示（task-20/21） | 2026-11-12 | 通过（today 10 键+零态；前端自算残留 0；lint 994w 未关规则；联调/浏览器属 T-38/T-35） | [RR-V1-FIX-T08B.md](RR-V1-FIX-T08B.md) |
| RR-V1-FIX-T14 | V1-09b 删除边界/item_ids/D2 409（task-17） | 2026-11-12 | 通过（42 passed；004 软删除 downgrade 保护；D2 全闭环含 AI 409） | [RR-V1-FIX-T14.md](RR-V1-FIX-T14.md) |
| RR-V1-FIX-T17 | V1-08 显式工具清单/哈希（task-13） | 2026-11-12 | **有条件通过**（R6 基线语义更新后 v2 7/7；缺陷类别闭合；待用户确认基线变更；Docker 运行时无法核验） | [RR-V1-FIX-T17.md](RR-V1-FIX-T17.md) |
| RR-V1-FIX-T22 | V1 followup 契约收口（task-22） | 2026-11-12 | 通过（AI 409/PATCH owner_id/discovery 空体/分页/DeviceStatus/004 74·74；审计转永久回归） | [RR-V1-FIX-T22.md](RR-V1-FIX-T22.md) |
| RR-V1-FINAL-20261112 | V1 修订轮最终评审与上线结论 | 2026-11-12 | **不通过/受控开发基线（收口）**：v2 反例基线 7/7 全过（R6 语义更新待用户确认）+ STRICT-3 448 passed/0 failed + 前端 56/0e/exit0；V1-11/12/13、R27、真实库对账、真机端到端未闭环 | [RR-V1-FINAL-20261112.md](RR-V1-FINAL-20261112.md) |
| RR-V11-PLAN-20261113 | 契约 v1.1 实施轮阶段一（落地核验+门禁清单） | 2026-11-13 | 通过（HEAD 387279e；契约 diff 空；A1~A5/授权顺序与草案逐字一致；G1~G9 门禁与任务断言映射建立） | [RR-V11-PLAN-20261113.md](RR-V11-PLAN-20261113.md) |
| RR-V11-FIX-A | 契约 v1.1 变更包 1：工具清单 A1~A5（task-23） | 2026-11-13 | 通过（红 8F→绿 23P；F1~F4 销项 9/9 CLOSED 独立复核；真实仓库 ok=true；ddr/ABI 待用户） | [RR-V11-FIX-A.md](RR-V11-FIX-A.md) |
| RR-V11-FIX-B | 契约 v1.1 变更包 2：AI 授权顺序+创建收口（task-24） | 2026-11-13 | 通过（B1/B2 计数=0、B3 差分独立 12 passed；授权顺序代码级核对；缺失键策略待用户确认） | [RR-V11-FIX-B.md](RR-V11-FIX-B.md) |
| RR-V11-FIX-C | 竞态治理：C2 export 收口（task-26）+ C1 cancel 续节（task-25，G7 达成） | 2026-11-13 | 通过（C1：五层根因红→绿、20 连跑双路径+并发 10 独立 7 passed、两项范围扩展为测试域无放宽） | [RR-V11-FIX-C.md](RR-V11-FIX-C.md) |
| RR-V11-FINAL-20261113 | 契约 v1.1 实施轮最终门禁验收 | 2026-11-13 | **实施轮通过（G1~G9 全达成）**：v2 基线 7/7、严格全量 467×2、A/B/C 独立验收；总体上线结论沿用不通过/受控基线（R27/对账/V1-11~13/U 项/T-38 未闭环） | [RR-V11-FINAL-20261113.md](RR-V11-FINAL-20261113.md) |
| RR-V11-REVIEW-20261113 | 契约 v1.1 实施轮独立复核（含 §4 修复闭环 task-28） | 2026-11-13 | **本轮最终签收：通过**（§2 P1 前端同步缺陷经 task-28 修复闭环：导航 id/plan 降级/65 用例/992w-0e/build；范围外维持项单列） | [RR-V11-REVIEW-20261113.md](RR-V11-REVIEW-20261113.md) |

## 2. 统一评审记录模板

每份 RR 文件必须包含以下全部小节；不适用的小节写"不适用+理由"，不得删除。

```markdown
# RR-xxx：<标题>

- 评审编号：RR-xxx
- 评审对象/任务编号：<任务号或文档名>
- 评审日期：<YYYY-MM-DD>
- 评审人：reviewer（独立评审方）
- 依据文档与版本：<列出契约/设计/规则文件及版本号、确认状态>
- 环境与 commit/变更集：<git commit、分支、被评审 diff 的文件清单>
- 证据路径：<相对路径列表；原始日志必须逐条含命令、时间、退出码>

## 1. 检查项与结论
| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|

## 2. 问题与风险等级
| # | 问题 | 依据（文件:行/日志） | 影响 | 等级（高/中/低） | 责任任务 |

## 3. 限制/无法核验项
| # | 事项 | 原因 | 影响 |

## 4. 待用户确认项
| # | 事项 | 建议决定 |

## 5. 独立重跑记录
<命令、数量、退出码、日志路径；未重跑写"未执行">

## 6. 最终结论
<通过 / 有条件通过 / 不通过 / 无法核验 + 一句话理由>

## 7. 签名
reviewer，<日期>；本记录基于原始证据独立作出，未代开发修改任何代码。
```

## 3. 评审方法与红线

1. 只读评审业务代码：用 `git status`/`git diff` 核对改动是否越出任务声明 scope；发现越界立即 send_message lead 并记录。
2. 独立重跑关键测试：后端用 `D:\MCTEST\test-platform\.venv\Scripts\python.exe -m pytest`（独立临时库），前端 `npm test`；保留完整日志到 `evidence/`。
3. 核对 DoD 每一条与实际证据一一对应；失败日志必须保留且未被覆盖。
4. 检查是否放宽断言、skip 测试、伪造实机输出；ADB 相关改动在真机做只读抽查（禁止 push/install/reboot/setprop/写设备）。
5. 发现夸大、越界、缺证据、回归失败：结论为不通过或有条件通过，并立即 send_message lead 指出具体文件/行/证据缺口；评审方不得替开发改代码。

## 4. 证据目录

- `evidence/adb-a133p-20261112/`：真机只读审计原始输出（每条含命令、时间戳、退出码）。
- `evidence/test-rerun-*/`：评审方独立重跑的测试日志（阶段二产生）。
