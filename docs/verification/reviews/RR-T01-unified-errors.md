# RR-T01：统一接口错误外层与目标路由适配

- 评审编号：RR-T01
- 评审对象/任务编号：T-01（task-1，owner backend-errors）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/README.md` v1.0 §2（成功/错误外层、通用错误码表、兼容与迁移）、`docs/contracts/task-execution-v1.0.md` v1.0 §10（legacy 路径）、`docs/verification/verification-rules-v1.0.md` v1.0 §3（四类强制校验，尤其 3.4 错误路径）、`docs/plan/task-board-v1.0.md` T-01
- 环境与 commit/变更集：Windows 10，Python 3.12.10（`D:\MCTEST\test-platform\.venv\Scripts\python.exe`），fastapi 0.109.0 / starlette 0.35.1 / httpx 0.26.0 / pytest 7.4.4；git HEAD `d0b415d` + 工作区未提交变更。T-01 变更：新增 `app/errors.py`、改 `app/main.py`、改 `app/api/tasks.py`、新增 `tests/integration/test_contract_errors.py`、6 个既有集成测试的断言更新（见 §1）
- 证据路径：
  - 开发证据：`docs/verification/tasks/T-01/`（result.md、pytest-focused-contract.log、pytest-full-run-01/02.log、pytest-adb-runner-standalone.log）
  - 评审方独立重跑：`docs/verification/reviews/evidence/test-rerun-20261112/backend-targeted-t01-t02-t19-reviewer.log`（87 passed）、`backend-full-regression-reviewer.log`

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 只改声明 scope | `git status`/`git diff HEAD` | T-01 = `app/errors.py`(新)、`app/main.py`、`app/api/tasks.py`、`test_contract_errors.py`(新)、6 个集成测试断言；未改 docs/plan、schemas、未动 main.py lifespan 区块 | 通过 |
| 2 | 错误外层结构与机器码映射符合契约错误码表 | 读 errors.py 全文；对照 contracts/README.md:49-59 | `{"code","message","details"}`；STATUS_TO_CODE 400/401/403/404/409/503 + 5xx→INTERNAL_ERROR + 422→VALIDATION_ERROR；与契约表一致 | 通过 |
| 3 | 422→400 归并 | 读 errors.py:51-58,76-78,103-119；测 test_auth_api 弱密码 422→400 | RequestValidationError 与 HTTPException(422) 均归并 400 VALIDATION_ERROR，details.field 给字段路径 | 通过 |
| 4 | 403 "Not authenticated"→401 归并的偏差说明 | 读 errors.py:38-41,80-86；result.md §6 决策1；contracts/README.md:24（未认证为401） | HTTPBearer 无凭据 403 归并 401 UNAUTHENTICATED 并保留 WWW-Authenticate；已认证无权限仍 403；偏差如实记录并经 Lead 批准 | 通过（如实记录） |
| 5 | 5xx 不泄密（含 DEBUG） | 读 errors.py:90-96,122-134；test 500 用例 | 表外 5xx 与未预期异常固定通用摘要，完整原因仅入日志；DEBUG=True 下断言无异常文本/路径/SQL | 通过 |
| 6 | 目标路由别名委托同一函数、零复制 | 读 tasks.py diff（新增 /cancellations、/reruns 两函数体仅 `return await cancel_task/rerun_failed_items(...)`，同 Depends(get_current_user)） | 无第二套权限/统计；legacy docstring 标 Deprecated（契约 §4） | 通过 |
| 7 | 7 处旧 detail 断言等价更新未放宽 | `git diff` 6 文件；逐条核对 | 7 处 `["detail"]`→`code+message`（tasks1/ai2/auth1/security2/tools1），另 422→400、403→401×2；均新增 `code==` 断言且保留 message 子串校验，更严或等价 | 通过 |
| 8 | 未放宽/跳过/删测试 | 读 diff、全量/聚焦结果 | 无删除用例、无 skip、无 `.only`；211/236 通过证据保留 | 通过 |
| 9 | 校验在业务写入前 | test_request_validation_400_missing_field 断言 TestTask count==0 | 缺字段 400 后 DB 无新增 | 通过 |
| 10 | 成功外层 ResponseModel 不破坏 | 读 aliases 用例 `set(body)=={code,message,data}`；schemas.py 未改 | 别名成功响应 200 + data | 通过 |
| 11 | 500/503 真实触发方式 | 读 test_contract_errors.py:54-63,183-218 | 用 `app.add_api_route` 临时路由真实触发处理器（含 DEBUG 500、ServerErrorMiddleware 读取已发响应），用完即移除，未改生产代码；result.md §4、§7 如实标注"无生产触发路径" | 通过（机制级，见 P-T01-1 限制） |
| 12 | 独立重跑（T-01 范围） | pytest 16 契约 + 6 更新集成文件 + adb/migration（受审范围）：87 passed | `backend-targeted-t01-t02-t19-reviewer.log` | 通过 |
| 13 | 独立全量回归（当前工作树） | `pytest tests -q -W error::...` | **2 failed, 234 passed**：均为 `test_judgement_engine.py`（default_returncode/ai_fallback），因 T-06 正在并行改 `judgement_engine.py`/`task_executor.py`/`execution_engine.py`/`test_judgement_engine.py`，与 T-01 无关 | 见 L1（非 T-01 缺陷） |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-T01-1 | 503/500 仅"处理器级"真实触发，无生产业务触发路径（503 ADB 失败关闭属 T-13；500 未预期异常无稳定生产入口） | test_contract_errors.py:183-218；result.md §7 | 契约"适用错误码真实触发一次"（verification §3.4）对 503 尚未在生产路径满足；不得声称错误码全覆盖 | 中 | T-13（503 真实路径）/后续 |
| P-T01-2 | 501 等表外状态码保持原 HTTP、code=INTERNAL_ERROR，未在契约错误码表归类 | errors.py:90-96；result.md §6 决策3 | 501（如 PDF 导出未实现端点）语义未定；PDF 导出 endpoint 后续任务的契约归类缺口 | 低 | T-37/相关端点任务 |
| P-T01-3 | RequestValidationError 的 `details.reason` 为 pydantic 英文模板（如 "Input should be a valid integer"），message 已中文化 | errors.py:116-118；result.md §7.6 | details.reason 非中文；契约未强制 reason 语言，但若验收要求中文需调整 | 低 | 待用户确认（U-T01-1） |
| P-T01-4 | 401/403/4xx 处理器对 `exc.detail` 原样透传为 message（未清洗） | errors.py:84-89,98 | 若某业务端点把敏感信息写入 HTTPException.detail 会外泄；当前业务 detail 均为中文安全摘要，风险低 | 低 | 记录性（后续端点审查） |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 独立全量回归当前 2 failed（test_judgement_engine） | T-06 正在并行编辑 judgement_engine/task_executor/execution_engine 及其测试，非 T-01 缺陷；T-01 范围定向 87 passed | 全量 236 通过以 T-02/T-19 证据日志时间点为准；最终全量须在 T-06 完成后由 Lead 统一重跑 |
| L2 | 503 生产触发 | 属 T-13 | 记"未验证"，T-13 落地后补真实用例 |
| L3 | 500 生产触发 | 无稳定生产路径 | 处理器机制已验证，生产路径记"未验证" |

## 4. 待用户确认项

| # | 事项 | 建议 |
|---|---|---|
| U-T01-1 | details.reason 是否必须中文化 | 建议保留 pydantic 原始安全摘要（英文）作为 reason，message 保持中文；如需中文 reason 由后续统一映射 |

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/integration/test_contract_errors.py + 6 更新集成 + tests/unit/test_adb_runner.py + test_migration_contract.py -q` | **87 passed** | 0 | `evidence/test-rerun-20261112/backend-targeted-t01-t02-t19-reviewer.log` |
| `pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA`（当前工作树） | 2 failed（test_judgement_engine，T-06 in-flight）/ 234 passed | 1 | `evidence/test-rerun-20261112/backend-full-regression-reviewer.log` |
| 开发证据对照：pytest-full-run-02（排除 adb in-flight） | 211 passed | 0 | `docs/verification/tasks/T-01/pytest-full-run-02.log` |

## 6. 最终结论

**通过（T-01 范围内 DoD 达成）。** 统一错误外层 `{"code","message","details"}`、机器码映射与契约错误码表一致；422→400、403"Not authenticated"→401 偏差如实记录并符合"未认证为 401"契约；500/503 处理器机制经真实临时路由验证且 5xx 不泄密；目标路由 `/cancellations`、`/reruns` 零复制委托同一业务函数与鉴权，legacy 标 Deprecated；7 处旧 detail 断言等价更新更严未放宽；成功外层不变。独立定向重跑 87 passed、退出码 0。遗留（503 生产触发待 T-13、500 生产路径未验证、501 归类、reason 语言）均记入限制/待确认，不改变本任务错误外层与路由适配结论；T-13 落地前不得声称"全部适用错误码已在生产路径真实触发"。

## 7. 签名

reviewer，2026-11-12；本记录基于源码、diff 与独立重跑日志作出，未替开发修改任何代码。
