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
