# RR-V11-FIX-B：契约 v1.1 变更包 2——AI 入口授权顺序与创建收口（task-24 / task-B）

- 评审编号：RR-V11-FIX-B
- 评审对象/任务编号：task-24（task-B；变更包 2 = task-execution §10 授权顺序）
- 评审日期：2026-11-13
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/task-execution-v1.0.md` §10 授权顺序（v1.1）、`CHANGES-DRAFT-v1.1` 变更包 2（GWT B1～B3）、`RR-V1-REFINAL-20261112.md` §3.2
- 环境与 commit/变更集：Windows 10；Python 3.12.10；**基线 HEAD `387279e`** + 工作区。变更：新增 `app/services/task_creation.py`（统一创建服务）、`app/services/nl_task_planner.py`（拆 resolve_device/plan_for_device）、`app/api/ai_tasks.py`（重写：授权→状态→知识/LLM→统一服务，删自写 TestTask/commit/设备推进）、`app/api/tasks.py`（薄委托）、`tests/integration/test_v1_followup_audit.py`（B1/B2/B3 永久回归）、`tests/integration/test_ai_tasks_api.py`（201/形状/plan 断言更严）
- 证据路径：`docs/verification/tasks/T-04/result.md` §B-1～B-5、`red-b1-b2-20261113.log`、`pytest-full-v1.1-taskB-green.log`；评审方独立重跑 `reviews/evidence/v11-fix-20261113/v11-fix-b-b123-reviewer.log`（12 passed）

## 1. 门禁与检查项

| # | 门禁/检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | G9 契约 diff 空（本轮复核） | `git diff HEAD -- docs/contracts` | 0 行 | 通过 |
| 2 | G1 红：B1 实际 400≠403 且 llm 计数 1；B2 409 但 knowledge/llm 计数各 1；B3 plan_for_device 缺失 | 读红测日志 | `red-b1-b2-20261113.log`：3 failed / exit 1 | 通过 |
| 3 | ① GWT B1：普通用户对他人设备 AI 文本 → 403 且 knowledge/LLM 计数=0 | **独立重跑** test_v1_followup_audit（monkeypatch 计数器） | B1 用例通过（knowledge=0、llm=0、任务计数 0） | 通过 |
| 4 | ① GWT B2：maintenance/offline AI 入口 → 409 且两计数=0 | 同上 | B2 用例通过 | 通过 |
| 5 | ② 授权顺序代码级核对 | 读 ai_tasks.py：1) resolve_device（仅设备表匹配，不触知识/LLM）→ 2) ensure_can_create_task_on_device(403) → 2.5) 幂等重放预检 → 3) testing/offline/maintenance(409) → 4) plan_for_device（知识/LLM） | `_get_llm_client` 亦在授权后才初始化；plan_for_device 仅在授权+状态检查后调用 | 通过 |
| 6 | ③ GWT B3 差分：AI 与手动落库逐字段一致 | 读 test_b3_ai_and_manual_creation_parity | user_id/device_id/selected_items/custom_parameters/status/schedule_type/next_run_at 逐字段相等；设备推进一致（testing）；plan 仅 AI 行持有（manual.plan is None） | 通过 |
| 7 | ③ 幂等语义：AI 同键同文本重放同 ID、同键不同文本 409；重放预检先于状态检查（不被 testing-409 掩盖） | 读 find_idempotent_replay + 用例 | operation=task_create_ai 独立键空间；请求摘要={"text","device_serial"} | 通过 |
| 8 | ④ AI 201 与响应形状变化如实更新测试 | git diff test_ai_tasks_api | TC-AI-001 200→201、data.task_id→data.id、plan 断言改核落库 TestTask.plan（更严） | 通过（更严） |
| 9 | 统一创建服务收口（v1.0 语义保持） | 读 task_creation.create_task_instance + ai_tasks 不再自写 TestTask/commit/设备推进 | 手动 tasks.py 薄委托同一服务 | 通过 |
| 10 | 独立重跑 | `pytest test_v1_followup_audit + test_ai_tasks_api` | **12 passed**，exit 0 | 通过 |
| 11 | 全量口径 | 开发 460 passed / 0 failed | `pytest-full-v1.1-taskB-green.log` | 通过（留痕） |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest test_v1_followup_audit.py test_ai_tasks_api.py`（含 B1/B2/B3） | **12 passed** | 0 | `evidence/v11-fix-20261113/v11-fix-b-b123-reviewer.log` |
| 开发证据：红测 | 3 failed（B1/B2/B3） | 1 | `docs/verification/tasks/T-04/red-b1-b2-20261113.log` |
| 开发证据：全量绿 | 460 passed / 0 failed | 0 | `docs/verification/tasks/T-04/pytest-full-v1.1-taskB-green.log` |
| 最终严格全量 | 待 Lead 两轮日志，届时补记 | — | — |

## 3. 问题与风险等级 / 遗留（如实）

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V11B-1 | AI 幂等键缺失仍走"不强幂等"兼容策略（与手动一致） | result B-5.1 | 契约 §3 必填偏差（T-10 已记录待用户确认）；AI 同样放宽 | 中（待用户） | 用户确认 |
| P-V1T24-2 | 设备不存在仍 400"无法识别"（契约 §2 未定为 404，保持现状） | result B-5.2 | 契约未明确该场景；保持现状，记录 | 低 | 记录性/后续契约澄清 |
| P-V1T24-3 | resolve_device 改全量匹配（他人设备可解析→403 不被 400 掩盖）：匹配语义变化属修复必要部分 | result B-4.2 | 已由授权阶段接管隔离；plan.device_id 来自真实解析 | 低 | 记录性 |

## 4. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 真实 LLM/知识库联调 | 测试以计数器/monkeypatch 验证"零调用"；真实 LLM 输出质量未联调 | 属 T-38 联调 |
| L2 | 全量 460 为自报 | 以 Lead 连续 2 轮严格全量为准 | 独立重跑 12 passed；全量待补记 |

## 5. 待用户确认项

缺失 Idempotency-Key 的兼容策略（手动+AI 一致不强幂等）是否改为强制必填——沿用 RR-V1-FIX-T10 待确认项，AI 路径并入同一决策。

## 6. 最终结论

**通过（变更包 2 B1～B3）。** 先红后绿完整（红 3 failed 留证）；独立重跑 B1/B2 计数断言（knowledge=0、llm=0）与 B3 差分全部通过（12 passed）；授权顺序代码级核对成立——resolve_device 仅查设备表，`ensure_can_create_task_on_device`(403) 与状态检查(409) 均先于 `plan_for_device`（知识/LLM），LLM 客户端初始化亦在授权后；任务写入收口统一创建服务（AI 删自写 TestTask/commit/设备推进，v1.0 语义保持）；AI 幂等 operation 独立键空间、重放预检先于状态检查；AI 201/响应形状测试更新更严未放宽。遗留如实：缺失键兼容策略（并入待用户确认）、设备不存在 400 保持现状。全量以 Lead 连续 2 轮严格全量为准。

## 7. 签名

reviewer，2026-11-13；本记录基于源码 diff、红绿日志与独立 B1/B2/B3 重跑作出，未替开发修改任何代码。
