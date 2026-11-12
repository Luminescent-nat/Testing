# T-15 知识规则写入/转换边界（V1-09a）验证记录

- 任务：task-18（V1-09a 知识规则部分，对应 T-15）
- 状态：实现完成；新增规则边界 17 用例通过，全量回归 **404 passed / 0 failed（exit 0）**
- 日期：2026-11-12；基线 HEAD fa70d3b；未 commit（Lead 统一提交）
- 环境：Windows + D:\MCTEST\test-platform\.venv\Scripts\python.exe（Python 3.12.10，pytest 7.4.4，fastapi 0.109.0）

## 1. 变更文件
| 文件 | 变更 |
|---|---|
| test-platform/backend/app/services/knowledge_converter.py | 新增 `validate_conditional_rules`（唯一对象 schema + 逐条件校验 + 规范化）、`canonical_rule_hash`（规则规范化 SHA-256 幂等）、`_split_existing_rules`（兼容读取历史 legacy 结构并升级为对象）；`RULE_SCHEMA.conditional_rules` 改为 object；`_normalize_preview` **删除"对象包成 list"逻辑**；`convert` 对 rule（及 test_item 的 dict 规则）写前校验；`_attach_rule` 改为写入契约对象 `{returncode_zero, conditions:[...]}`，合并历史条件、相同规则对象幂等不重复附加，返回 `target_item_id/item_name/rules_count` |
| test-platform/backend/app/api/knowledge.py | 预览/转换入口接入写前校验：非法 `conditional_rules` 返回契约 **400 VALIDATION_ERROR**（`details.field` 精确到条件字段路径，如 `preview_data.conditional_rules.conditions.0.operator`），零资产写入；合法预览返回规范化对象；新增 `_rule_validation_response` 统一错误外层 |
| test-platform/backend/tests/integration/test_v1_knowledge_rules.py | **新增** 17 用例：各类非法结构 400 且零写入、字段路径精确、对象不被包 list、合法 conditions 判定 pass/fail、重复转换幂等、预览非法/合法、符号操作符规范化、未知条件字段 |

未改：schemas.py、tasks.py（task-17 负责）、judgement/execution/task_executor、reports、websocket、dashboard、frontend、models/alembic/database。

## 2. 唯一 conditional_rules schema（契约 knowledge-rules-v1.0 §1）校验矩阵
| 输入 | HTTP | details.field | 用例 |
|---|---:|---|---|
| `conditional_rules=[...]`（list 根） | 400 | preview_data.conditional_rules | test_invalid_rule_structure_returns_400_zero_write[0] |
| 标量根（"not-an-object"/123/None） | 400 | preview_data.conditional_rules | [1][2][3] |
| 空 conditions `[]` | 400 | preview_data.conditional_rules.conditions | [4] |
| conditions 非数组 | 400 | preview_data.conditional_rules.conditions | [5] |
| 未知操作符 | 400 | ...conditions.0.operator | [6] |
| 非法正则 | 400 | ...conditions.0.source | [7] |
| 缺失 source | 400 | ...conditions.0.source | [8] |
| 缺失 target | 400 | ...conditions.0.target | [9] |
| approx_ratio 目标 0 | 400 | ...conditions.0.target | [10] |
| 未知条件字段 | 400 | ...conditions.0 | test_operator_symbol_normalized_and_unknown_field_rejected |
| 合法对象（含符号操作符 `>=` 规范化 gte） | 200 | — | test_legal_conditions_produce_deterministic_pass_fail 等 |

每个非法用例同时断言：`TestItem`/`TestModule` 计数不变、目标测试项 `conditional_rules` 未被修改（零资产/零修改写入）。

合法条件判定确定性：同一合法规则写入后，
- `output="value=150"` → **pass**
- `output="value=50"` → **fail**
（`JudgementEngine().judge(...)` 直接验证，未改判定引擎代码）

## 3. 命令与退出码（原始日志）
| # | 命令 | 结果 | 日志 |
|---|---|---|---|
| 1 | `python -m pytest tests/integration/test_v1_knowledge_rules.py tests/unit/test_knowledge_converter.py tests/integration/test_knowledge_api.py -q --tb=short -rA` | **35 passed，exit 0**（17 新 + 4 既有单测 + 14 知识 API） | [pytest-focused.log](pytest-focused.log) |
| 2 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA`（全量） | **404 passed，0 failed，exit 0**（195.1s） | [pytest-full-run-01.log](pytest-full-run-01.log) |

## 4. DoD 结论（T-15）
- **`conditional_rules` 唯一结构为对象（conditions 数组），不得再把对象包成 list** → 达成：`_normalize_preview` 删除包装逻辑，写入统一对象，用例断言落库为 dict。
- **list/标量根、空 conditions、未知操作符、非法正则、缺失 source/target、approx_ratio 零目标均 400 且无资产写入** → 达成（第 2 节矩阵，details.field 精确）。
- **合法 conditions 确定 pass/fail（不得默认 pass）** → 达成（pass/fail 双断言）。
- **重复规则幂等** → 达成：服务层按规范化 SHA-256 比较，相同规则对象不重复附加（rules_count 保持 1）。
- **预览/转换共用同一校验** → 达成：预览与转换均调用同一 `validate_conditional_rules`；执行期判定引擎保持独立运行时兜底（未改 judgement_engine）。

## 5. 遗留 / 需评审
1. **目标测试项不存在**：`_attach_rule` 现抛 ValueError → API 返回 400；契约 §3 期望 404 NOT_FOUND。属既有语义，本次未改（避免扩大范围），建议后续统一。
2. **DB 级唯一约束**：契约的 `(target_item_id, 规则规范化SHA-256)` 唯一键需 models/alembic 支持（本任务禁止改），当前以服务层规范化哈希判重实现幂等；并发极端场景仍需数据库唯一约束兜底，建议迁移任务补充。
3. **test_item 的 conditional_rules legacy list**：既有单测 `tests/unit/test_knowledge_converter.py`（不在本任务 write scope）仍传入旧 list 结构，为不破坏既有回归，test_item 路径对 dict 规则严格校验并规范化、对 legacy list 保持原样透传（不包 list）；建议后续随单测迁移统一为对象。
4. 判定执行期（V1-02）仍以 error 兜底非法配置，与写前 400 互补；未改 judgement/execution/task_executor。
