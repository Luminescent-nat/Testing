# RR-V1-FIX-T15：V1-09a 知识规则写前校验（task-18）

- 评审编号：RR-V1-FIX-T15
- 评审对象/任务编号：task-18（V1-09a 知识规则部分；对应 T-15）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/knowledge-rules-v1.0.md` v1.0 §1/§3/§4、`docs/design/execution-state-machine.md` v1.0 §2 行11、`RR-V1-READINESS-20261112.md` V1-09
- 环境与 commit/变更集：Windows 10；Python 3.12.10；git HEAD `fa70d3b` + 工作区（task-18 未提交）。变更：`app/services/knowledge_converter.py`（新增 validate_conditional_rules/canonical_rule_hash/_split_existing_rules，RULE_SCHEMA object，删除对象包 list）、`app/api/knowledge.py`（预览/转换 400 契约外层+details.field）、新增 `tests/integration/test_v1_knowledge_rules.py`(17)
- 证据路径：`docs/verification/tasks/T-15/`（result.md、pytest-focused.log、pytest-full-run-01.log）；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t15-knowledge-reviewer.log`（35 passed）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | ① list 根/标量根/空 conditions→400 零写入且 details.field 精确 | 读 validate_conditional_rules（非 dict→RuleValidationError field）；knowledge.py _rule_validation_response（400 build_error_body details.field/reason） | 独立 35 passed；用例矩阵 [0]-[5] 覆盖 list/"not-an-object"/123/None/空conditions/非数组 conditions，均断言 TestItem/TestModule 计数不变、目标项 conditional_rules 未改 | 通过 |
| 2 | ① 未知操作符/非法正则/缺 source/缺 target/零目标→400 | 读 validate 逐条件校验 | 用例 [6]-[10] + 未知字段用例，field 精确到 `...conditions.N.operator/source/target` | 通过 |
| 3 | ② 合法 conditions 预览与转换一致、确定 pass/fail | 读 convert 复用同一 validate；测试 output 150→pass / 50→fail | 合法对象（符号操作符 `>=`→gte 规范化）预览/转换一致；pass/fail 双断言 | 通过 |
| 4 | ② 重复转换幂等 | canonical_rule_hash 比较（相同规范化对象不重复附加） | rules_count 保持 1 | 通过 |
| 5 | ③ 对象包成 list 已删除 | 读 _normalize_preview（删除 `[dict]` 包装，仅 validate 或保留原值交 API 校验） | 代码确认；落库为 dict 对象 | 通过 |
| 6 | ③ 写前与执行期同一事实（judgement_engine 运行时 error 兜底仍在） | 读 knowledge_converter VALID_OPERATORS 与 judgement_engine VALID_OPERATORS；judgement_engine 未改 | 两处操作符集合相同（eq/gt/gte/lt/lte/approx_ratio/contains）；运行时 error 兜底保持 | 通过（见 P-V1T15-1 低风险：常量未抽公共） |
| 7 | 零资产写入 | 测试每非法用例断言 DB 计数不变 | 通过 | 通过 |
| 8 | 未越界 | git status/diff | 仅 knowledge_converter.py / api/knowledge.py / 新测试；未改 schemas/tasks/judgement/execution/models/frontend | 通过 |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/integration/test_v1_knowledge_rules.py tests/unit/test_knowledge_converter.py tests/integration/test_knowledge_api.py` | **35 passed**（17 新 + 4 既有单测 + 14 知识 API） | 0 | `evidence/v1-fix-20261112/v1-fix-t15-knowledge-reviewer.log` |
| 开发证据：全量 | 404 passed | 0 | `docs/verification/tasks/T-15/pytest-full-run-01.log` |
| 最终严格全量 | 待 Lead 最终日志，届时补记 | — | — |

## 3. 遗留偏差的如实性与判定

| # | 遗留 | 是否如实记录 | 判定 | 去向 |
|---|---|---|---|---|
| E1 | 目标测试项不存在：`_attach_rule` 抛 ValueError→API 400，契约 §3 期望 **404 NOT_FOUND** | 如实（result §5.1） | **不阻塞 V1-09a 写前校验核心**；属契约错误码偏差 | 记 V1-09 遗留/后续统一 |
| E2 | `(target_item_id, 规则规范化SHA-256)` DB 唯一约束未加，当前仅服务层哈希判重幂等 | 如实（result §5.2） | **不阻塞单实例**；并发极端需 DB 唯一约束兜底 | 记 V1-09/T-11 后续迁移 |
| E3 | test_item 路径对 legacy list 规则**原样透传**（仅 dict 规则校验，为不破坏既有单测） | 如实（result §5.3） | **V1-09 部分未闭环**：test_item 写路径未强制对象 schema，list 可漏过；不影响 rule 预览/转换主路径 | 记 V1-09 遗留（待 test_knowledge_converter 单测迁移后统一） |
| E4 | 执行期非法配置仍由 judgement_engine error 兜底（与写前 400 互补） | 如实（result §5.4） | 正确（失败关闭双层） | 记录 |

## 4. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T15-1 | VALID_OPERATORS 在 knowledge_converter 与 judgement_engine 各定义一份（同值未抽公共常量） | 两文件 | 未来可能漂移；建议抽公共常量 | 低 | 记录性 |
| P-V1T15-2 | 目标测试项不存在返回 400，契约期望 404 | result §5.1；knowledge-rules §3 | 错误码偏差 | 中 | V1-09 后续 |
| P-V1T15-3 | test_item legacy list 透传，未强制对象 schema | result §5.3 | V1-09 未完全闭环 | 中 | V1-09 后续 |
| P-V1T15-4 | 规则 DB 唯一约束待迁移 | result §5.2 | 并发幂等仅服务层保证 | 低-中 | T-11 后续 |

## 5. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 与 LLM 真实转换联调（真实规则生成） | 测试用构造数据；LLM 真实输出未联调 | 真实提取质量未验证（属 T-15/LLM 范围） |
| L2 | 全量 404 passed 为自报 | 以 Lead 最终严格全量日志为准 | 独立重跑 35 passed；全量待补记 |

## 6. 最终结论

**通过（V1-09a 知识规则写前校验范围；V1-09 全量部分未闭环）。** list/标量/空/零目标/未知操作符/非法正则/缺失字段均写前 400 且零资产写入、`details.field` 精确到条件路径（独立 35 passed，17 新用例矩阵 + DB 计数不变断言）；合法 conditions 预览与转换一致、pass/fail 确定、重复转换幂等；「对象包成 list」已删除、RULE_SCHEMA 改为对象、执行期判定引擎 error 兜底仍在（写前 400 与运行时失败关闭双层）。遗留如实：E1 目标不存在 400 vs 契约 404、E2 规则 DB 唯一约束待迁移、E3 test_item legacy list 透传（**V1-09 部分未闭环**）、E4 执行期兜底正确——记入 RR-V1-FINAL。全量以 Lead 最终严格日志为准。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、契约与独立定向测试作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
