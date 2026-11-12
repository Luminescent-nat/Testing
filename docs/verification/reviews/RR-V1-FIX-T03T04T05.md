# RR-V1-FIX-T03T04T05：V1-01/V1-07 设备与 WS 统一授权（task-9）

- 评审编号：RR-V1-FIX-T03T04T05
- 评审对象/任务编号：task-9（V1-01 越权创建 + V1-07 WS 部分；对应 T-03/T-04/T-05）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/device-authorization-v1.0.md` v1.0 §1、`docs/contracts/task-execution-v1.0.md` v1.0 §2 处理顺序、`docs/contracts/reporting-v1.0.md` v1.0 §批量导出、`RR-V1-READINESS-20261112.md` V1-01/V1-07、`targeted-defect-repro.py` R1、`verification-rules-v1.0.md` §3.1
- 环境与 commit/变更集：Windows 10；Python 3.12.10；git HEAD `fa70d3b` + 工作区（task-9 未提交；task-12 正在同文件 tasks.py 接入幂等）。变更：新增 `app/services/authorization.py`；`app/api/tasks.py`(授权调用，未含幂等/201)、`app/api/ai_tasks.py`、`app/api/devices.py`、`app/api/reports.py`、`app/websocket.py`；新增 `tests/integration/test_v1_authorization.py`
- 证据路径：`docs/verification/tasks/T-03/`、`T-04/`、`T-05/`（result.md、pytest-v1-authorization.log、pytest-affected-integration.log、pytest-full-run-03-final.log、repro-before-fix-demo.log）；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t03t04t05-v1auth-reviewer.log`（17 passed）、`v1-repro-R1-after-task9.log`（1 passed）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | ① repro R1：他人设备 403 且 DB 计数 0 | 独立重跑 R1（shim 插件，临时库） | **1 passed / 5 deselected**（403、total=0） | 通过 |
| 2 | ② 真值表：管理员任意/owner=本人+PC一致允许/PC不一致403/他人403/null 403/disabled 403 | 读 authorization.py:60-124；test_v1_authorization.py 用例 | 17 用例覆盖；独立重跑 17 passed | 通过 |
| 3 | ② WS disabled→1008、active 对照 | 读 websocket.py diff（is_active→1008、can_read_task）；test_ws_disabled_user_closed_1008/test_ws_active_user_still_allowed | 17 passed 含 WS 用例 | 通过 |
| 4 | ② 五入口均走 authorization.py | grep/读 diff：tasks.py(手动/重跑)、ai_tasks.py、devices.py、reports.py、websocket.py | 全部 import 同一 `app/services/authorization.py`；无第二套权限语义 | 通过 |
| 5 | ③ 批量导出由静默跳过改整体 403 | 读 reports.py:_build_multi_task_report（403 re-raise，not-found continue）；对照 reporting-v1.0.md:157,163 | 契约明确"任一 task 无权限整个请求失败，不静默跳过" | 通过（与契约一致） |
| 6 | ④ fail→pass 归因演示 | 读 repro-before-fix-demo.log | 临时移除守卫→旧行为 200（1 passed 演示），日志较简略；**核心由永久用例 test_v1_authorization.py + 我独立重跑 R1 佐证** | 通过（演示略简，核心证据充分） |
| 7 | ⑤ 发现/改派（device-discoveries/PATCH）未做 | grep devices.py | 仅 legacy `/devices/refresh`；无目标发现路径/PATCH 改派 | **V1-01 部分未闭环**（记 FINAL） |
| 8 | ⑥ 授权先于设备可用性判断（不泄露设备状态） | 读 tasks.py create_task 顺序：设备存在→ensure_can_create_task_on_device→offline/maintenance；对照 task-execution §2 处理顺序 | 顺序为"设备存在→owner/PC授权→可用状态"，与契约一致；无权限者得 403 不泄露 offline/testing | 通过 |
| 9 | 写前校验零写入 | test 用例断言 403 后 DB 计数 0、重跑不新增 | 通过 | 通过 |
| 10 | 未越界/未改他模块 | git status/diff | 仅上表文件；未改 models/alembic/database/judgement/execution/task_executor/device.py/test-tools/frontend | 通过 |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T03-1 | 设备发现（目标 `/device-discoveries`）与改派（`PATCH /devices/{serial}` 版本条件更新）**未实现**（task-9 禁改 device.py） | T-03 result §5.1；grep devices.py 仅 legacy refresh | **V1-01 部分未闭环**：普通用户发现不认领、管理员改派版本条件更新未覆盖；legacy refresh 行为未变 | 中 | 后续任务（允许改 device.py/新增路由） |
| P-V1T03-2 | 403 message 未附契约示例 `details.field=serial` | T-03 §5.2 | details 为可选；不影响授权判定 | 低 | 记录性 |
| P-V1T03-3 | disabled REST 403 由 get_current_user 提供（未改 auth.py） | T-03 §5.3 | 行为正确（disabled→403）；WS 走 authorization.is_active→1008 | 低 | 记录性 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 设备发现/改派授权 | task-9 禁改 device.py | V1-01 部分未闭环（见 P-V1T03-1） |
| L2 | 严格全量 378 passed 为开发自报 | task-12 在途可能再改 tasks.py；以 Lead 最终严格全量日志为准 | 本 RR 独立重跑定向 17 passed + R1；全量待补记 |
| L3 | 浏览器/前端按钮联动 | 属 T-22+/前端；本任务仅服务端 | 前端隐藏不作授权依据（本任务已服务端校验） |

## 4. 待用户确认项

无新增（真值表严格对齐 device-authorization-v1.0 §1）。

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| repro R1（shim 插件，临时库） | **1 passed / 5 deselected** | 0 | `evidence/v1-fix-20261112/v1-repro-R1-after-task9.log` |
| `pytest tests/integration/test_v1_authorization.py` | **17 passed** | 0 | `evidence/v1-fix-20261112/v1-fix-t03t04t05-v1auth-reviewer.log` |
| 开发证据：全量 | 378 passed（16:54-16:57） | 0 | `docs/verification/tasks/T-03/pytest-full-run-03-final.log` |
| 最终严格全量 | 待 Lead 最终日志，届时补记 | — | — |

## 6. 最终结论

**通过（V1-01/V1-07 授权主体；设备发现/改派除外）。** repro R1 已由 FAILED 转 **PASS**（他人设备 403 且零任务写入，独立重跑 1 passed）；`authorization.py` 为唯一授权事实来源，手动/AI/重跑/设备/报告/缓存/WS 五入口统一复用，真值表（管理员任意、owner=本人+PC一致允许、PC不一致/他人/null/disabled 403、WS disabled→1008）经 17 用例覆盖并独立重跑 17 passed；批量导出整体 403 与 reporting-v1.0 §批量导出（任一无权限整个请求失败、不静默跳过）一致；授权先于设备可用性判断符合 task-execution §2 处理顺序且不泄露设备状态。**未闭环：设备发现（目标路径）与改派（PATCH 版本条件更新）未实现 → V1-01 部分未闭环，记入 RR-V1-FINAL。** 全量以 Lead 最终严格日志为准（当前 378 为自报，task-12 在途）。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、契约与独立反例/定向测试重跑作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
