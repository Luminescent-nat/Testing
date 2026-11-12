# 执行状态机与统计契约

- 版本：v1.0
- 状态：2026-11-12 用户已确认
- 需求：R8～R12、R15、R31

## 1. 状态集合

测试记录只有 `pending/running` 两个非终态和 `pass/fail/skip/error/timeout` 五个终态。任务生命周期固定为 `pending/running/completed/failed/cancelled`，业务结果固定为 `passed/failed/null`。禁止引入 `unknown` 作为落库或展示终态。

## 2. 单项判定优先级

按从上到下取第一个适用规则，任何后续规则不得把已确定的 fail/error/timeout 改成 pass。

| 顺序 | 条件 | 记录终态 | reason 要求 |
|---:|---|---|---|
| 1 | 执行超过 timeout | timeout | 记录超时上限与终止结果 |
| 2 | 子进程/执行器无法启动或内部异常 | error | 安全异常摘要，不含堆栈 |
| 3 | returncode != 0 | fail | 包含退出码；即使输出有 SKIP/pass_pattern 也不通过 |
| 4 | rc=0 且输出存在独立原生 SKIP 行 | skip | 保存原生原因；无原因则为空字符串 |
| 5 | fail_pattern 命中，或 pass/fail 同时命中 | fail | 指出失败模式命中 |
| 6 | judgement_type=assertion 且有效条件规则完整执行为 true | pass | 可为 null |
| 7 | 有效 assertion 规则执行为 false，或 pass_pattern 未命中 | fail | 指出未满足断言 |
| 8 | judgement_type=rubric 且有效评分达到阈值 | pass | 可为 null |
| 9 | 有效 rubric 评分低于阈值 | fail | 指出阈值与得分 |
| 10 | judgement_type=ai_fallback 且有效 AI 明确给出通过/失败 | pass/fail | 保存模型结论摘要 |
| 11 | 无判定配置、空规则、未知操作符、规则结构非法或 AI 无有效结论 | error | 标记配置/判定不可用；绝不为 pass |

原生 SKIP 行仅接受整行 `RESULT: SKIP` 或 `RESULT: SKIP: <原因>`，前后允许空白，标记本身区分大小写。`foo RESULT: SKIP`、`RESULT: SKIPPED`、多行中的相似自然语言均不匹配。skip 不触发 stop-on-failure。

知识转换在预览和写入前使用同一规则 schema 校验 conditions；list、标量、未知操作符和空规则返回 400。历史非法配置若绕过写入校验，在运行时按第 11 条 error，不得默认通过。

## 3. 任务聚合真值表

令 N=选中测试项数，C=五类终态记录数，R=running 记录数，P=pending 记录数。

| 场景 | status | result | completed_items | progress |
|---|---|---|---:|---:|
| 等待到期或设备排队 | pending | null | 当前 C | floor(C/N*100)，N>0 |
| 已开始且未全部收尾 | running | null | C，不含 running | floor(C/N*100) |
| 正常收尾，任一 fail/error/timeout | completed | failed | N | 100 |
| 正常收尾，无失败类且至少一项 pass | completed | passed | N | 100 |
| 正常收尾，N>0 且全部 skip | completed | null | N | 100 |
| 平台异常无法形成完整正常收尾 | failed | null | 当前 C | 保留实际进度，不伪造 100 |
| 用户取消 | cancelled | null | 当前 C | 保留实际进度，不伪造 100 |
| 仍有 P>0 或 R>0 或 C<N | 不得 completed | null | C | 按实际值 |

存量 N=0 或零记录任务保持其可识别终态和 result=null，界面显示“无执行记录”；不得为了新规则补造 pass/skip。

## 4. stop-on-failure

给定 5 项，第 1 项 pass，第 2 项 `on_failure=stop` 且 fail：

| 项 | 是否执行命令 | 终态 | 原因 |
|---|---|---|---|
| 1 | 是 | pass | null |
| 2 | 是 | fail | 实际失败原因 |
| 3～5 | 否 | skip | `stopped_by_item_id=2`，不得伪造输出或消耗重试 |

最终 `status=completed`、`result=failed`、pass=1、fail=1、skip=3、error=0、timeout=0、C=5、progress=100、pass_rate=50.0。触发项为 error/timeout 时同样停止并补 skip；skip 自身不停止。

## 5. 进度与通过率

- `completed_items=C`，running 和 pending 均不计入。
- `progress_percent=floor(C/N*100)`，N>0；100% 只表示全部处理。
- 单项/模块/报告通过率：`pass/(pass+fail+error+timeout)*100`，skip 不进分母；分母 0 返回 null。
- Dashboard 任务通过率：仅 `status=completed` 且 `result in (passed,failed)` 的任务进入分母，公式为 `passed_tasks/(passed_tasks+failed_tasks)*100`。
- 全 skip、零记录、pending/running、平台 failed、cancelled 均不进入 Dashboard 通过率分母，必须分别计数展示。

## 6. 统一统计样例

| 输入 | 预期 |
|---|---|
| pass=2/fail=1/timeout=1/skip=2，N=6 | C=6、progress=100、pass_rate=50.0 |
| 全部 skip，N>0 | completed/result=null、pass_rate=null |
| 首项 stop+fail，其余 4 项补 skip | pass=0、fail=1、skip=4、pass_rate=0.0 |
| 有一项 running，另有 3 项 pass | running 不计 C，任务不得 completed |
| 分母为 0 | API/WS/报告均为 null，前端显示“无有效结果”而非 0% 或 100% |

## 7. 消费者约束

执行器负责唯一判定和任务聚合；WS、任务详情、Dashboard、报告、导出和前端不得另写相反规则。前端可以格式化 number/null，但不得把 timeout 排除出失败分母、把 running 计入完成或把 completed 直接显示为 passed。
