# T-01 统一接口错误外层与目标路由适配 — 验证记录

- 任务编号：T-01（task-1，owner：backend-errors，最终 revision 5）
- 状态：实现完成，测试全绿（全量回归排除 T-19 并行改造中的 tests/unit/test_adb_runner.py，见"遗留/未验证项"第 1 条）
- 日期：2026-11-12
- 结论：DoD 逐条达成（见下），无放宽既有断言，未改 docs/plan，未动 main.py lifespan 区块，未 commit。

## 1. 变更集（可单独回退）

### 生产代码
| 文件 | 变更 |
|---|---|
| test-platform/backend/app/errors.py | 新增。错误外层构造 `build_error_body`、状态码→机器码映射（400 VALIDATION_ERROR、401 UNAUTHENTICATED、403 FORBIDDEN、404 NOT_FOUND、409 CONFLICT、503 SERVICE_UNAVAILABLE、422 归并 400 VALIDATION_ERROR、表外 5xx 归 INTERNAL_ERROR）；`register_error_handlers` 注册 HTTPException（fastapi/starlette 同一处理器）、RequestValidationError、未预期 Exception 三类处理器。错误 JSON 固定 `{"code","message","details"}`，details 仅允许 field/item_id/reason，数组下标用点号；5xx 响应不回显任何 detail，DEBUG 也不泄密 |
| test-platform/backend/app/main.py | 删除旧 `global_exception_handler`（原 `{"code":500,"message","detail"}` 外层，DEBUG 会回显 str(exc)），改为调用 `register_error_handlers(app)`。lifespan 区块零改动 |
| test-platform/backend/app/api/tasks.py | 新增目标路由 `POST /tasks/{task_id}/cancellations` 与 `POST /tasks/{task_id}/reruns`，函数体内直接 `await` 委托既有 `cancel_task` / `rerun_failed_items`（同一鉴权 Depends(get_current_user)、同一业务函数，无第二套权限/统计语义）；legacy `cancel_task`/`rerun_failed_items` docstring 标注 Deprecated（契约 v1.0 第 4 节）。幂等（Idempotency-Key）未实现，按任务约定留给 T-10 |

### 测试
| 文件 | 变更 |
|---|---|
| tests/integration/test_contract_errors.py | 新增 16 个用例：严格核对错误外层结构（键集合、机器码、中文摘要、details 键白名单、无顶层 detail、无 Traceback/泄露标记）、400 业务校验与 RequestValidationError 字段路径（`device_serial`、`item_ids.0`、`page`）、校验失败不落库（DB count==0）、401（无效 token + 缺 token）、403（非 owner、管理员接口）、404（含别名路径）、409（AI 任务设备 testing 真实分支）、503/500（临时路由真实触发处理器，500 用 `ASGITransport(raise_app_exceptions=False)` 读取 ServerErrorMiddleware 已发响应，DEBUG 开启下断言无敏感文本）；别名路由委托/鉴权/落库断言及成功外层 `{code,message,data}` 不变断言 |
| tests/integration/test_tasks_api.py | L60：`response.json()["detail"]` → `code=="VALIDATION_ERROR"` 且 `"离线" in message`（更严） |
| tests/integration/test_ai_tasks_api.py | L54、L81 两处 detail → code + message 断言（更严） |
| tests/integration/test_auth_api.py | L35 detail→message；L45 422→400 VALIDATION_ERROR 且 `details.field=="password"`；L108-109 未认证 403→401 UNAUTHENTICATED（契约"未认证为 401"，经 Lead 批准） |
| tests/integration/test_security_hardening.py | L29、L64 两处 detail → code + message 断言（更严） |
| tests/integration/test_tools_api.py | L82 detail→message（Lead 已将该文件纳入 scope，revision 4） |
| tests/integration/test_reports_stats_api.py | L163-166 未登录断言 403→401 且断言 code=UNAUTHENTICATED（Lead 批准，revision 5；仅此一处，其余 403 均为已认证无权限，保持 403） |
| tests/integration/test_knowledge_api.py | 未修改。L374 `data["detail"]["item_name"]` 是成功响应业务字段，非错误外层（经全量检索确认，Lead 同步确认勿改） |

## 2. 环境

- OS：Windows（PowerShell 7 / pwsh），工作目录 D:\MCTEST\test-platform\backend
- Python：D:\MCTEST\test-platform\.venv\Scripts\python.exe
- 版本：fastapi 0.109.0、starlette 0.35.1、httpx 0.26.0、pytest 7.4.4、pydantic v2（field_validator）
- 说明：与本任务无直接关系，但同期仓库存在并行改动（T-02 alembic/env.py+database.py、T-06 判定引擎、T-19 test-tools/adb_runner、前端 token），全量回归为多任务混合工作树状态。

## 3. 命令与退出码（原始日志均在 docs/verification/tasks/T-01/ 下）

| # | 命令 | 起止时间 | 退出码 | 结果 | 日志 |
|---|---|---|---|---|---|
| 1 | 聚焦：`python -m pytest tests/integration/test_contract_errors.py tests/integration/test_auth_api.py tests/integration/test_tasks_api.py tests/integration/test_ai_tasks_api.py tests/integration/test_security_hardening.py tests/integration/test_tools_api.py tests/integration/test_reports_stats_api.py -q --tb=short -rA` | START 2026-11-12 11:58:29 +08:00 / END 11:59:15 | 0 | 56 passed, 0 failed | pytest-focused-contract.log |
| 2 | 全量首跑：`python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA` | START 2026-11-12 11:52:28 +08:00 / END 11:54:31，122.9s | **1** | 211 passed, **25 failed**（24 个 test_adb_runner.py 瞬时 TypeError＝T-19 并行改 runner 文件所致，单文件复跑即 25 passed；1 个 test_stats_endpoints_require_auth 403→401 决策当时未落，已按 Lead 决策 A 修复）。失败日志按规则原样保留 | pytest-full-run-01.log |
| 3 | 最终全量（排除 T-19 in-flight 文件）：`python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA --ignore=tests/unit/test_adb_runner.py` | START 2026-11-12 11:56:05 +08:00 / END 11:58:13，128.1s | **0** | **211 passed, 0 failed, 0 warning 类失败** | pytest-full-run-02.log |
| 4 | 参考：`python -m pytest tests/unit/test_adb_runner.py -q --tb=line`（非 T-01 scope，仅记录 T-19 文件单独可跑通） | 2026-11-12 11:59:43 +08:00 | 0 | 25 passed | pytest-adb-runner-standalone.log |

- 用例数：变更前基线 189 → 现 236（收集数，含 T-02/T-06/T-19 并行新增与本任务新增 16 个；211+25=236）。本任务新增 16，满足"新增实现必须增加覆盖"。
- 修复前失败日志（run-01）与修复后日志（run-02）均保留，未覆盖。

## 4. 错误码真实触发矩阵（verification-rules 3.4）

| code | HTTP | 触发方式 | 结果 |
|---|---:|---|---|
| VALIDATION_ERROR | 400 | 真实业务：离线设备创建任务、重跑无失败项、别名重复取消终态任务；RequestValidationError：缺 device_serial、item_ids.0 类型错误、query page 类型错误 | ✅ 通过（含 details.field 点号路径、写前校验 DB 无新增） |
| UNAUTHENTICATED | 401 | 真实：无效 JWT（get_current_user 401）；缺少 Authorization（HTTPBearer 403 "Not authenticated" 归并 401，保留 WWW-Authenticate） | ✅ 通过 |
| FORBIDDEN | 403 | 真实：普通用户查看他人任务（owner 校验）、普通用户访问管理员接口、别名取消他人任务 | ✅ 通过（越权无落库断言） |
| NOT_FOUND | 404 | 真实：GET /tasks/999999 与 4 条取消/重跑路径（新旧路径）任务不存在 | ✅ 通过 |
| CONFLICT | 409 | 真实业务分支：AI 任务目标设备 testing（app/api/ai_tasks.py L69） | ✅ 通过 |
| INTERNAL_ERROR | 500 | 当前生产代码无未预期异常可稳定触发，按任务约定用 app.add_api_route 临时测试路由真实触发处理器（含 DEBUG=True 与敏感标记文本，测试后立即移除路由，未改生产代码） | ✅ 通过（500 通用摘要、details={}、DEBUG 下无异常文本/路径/SQL 泄露） |
| SERVICE_UNAVAILABLE | 503 | 当前生产代码无 503 触发路径（ADB 失败关闭归 T-13），按任务约定用临时路由真实触发映射 | ✅ 通过（code/message/details 正确） |
| （422） | 400 | RequestValidationError 归并：pytest 中所有原 422 断言（test_auth_api 弱密码）改为 400 VALIDATION_ERROR | ✅ 通过 |

## 5. DoD 逐条结论（task-board T-01）

1. **适用异常只返回契约 `{"code","message","details"}`，校验在业务写入前，无堆栈泄露** → **达成**。
   - test_contract_errors 每个错误响应断言：键集合恒等 {code,message,details}、code 为契约机器码、message 非空中文摘要、details 键 ∈ {field,item_id,reason}、无顶层 detail、文本无 Traceback/敏感标记；缺字段 400 后 TestTask count==0（写前校验）；500 用例 DEBUG=True 下无异常文本/绝对路径/SQL。
   - 成功外层 ResponseModel(code/message/data) 不变：别名用例与全量回归 211 passed 共同证实，无既有成功断言被破坏。
2. **legacy 仅委托同一服务，不形成第二套权限或统计语义** → **达成**。
   - 两个别名函数体仅 `return await cancel_task/rerun_failed_items(...)`（同一函数、同一 Depends 鉴权）；别名与 legacy 均验证：终态任务再取消同 400"任务无法取消"、非 owner 同 403"无权限取消此任务"、任务不存在同 404；legacy docstring 标注 Deprecated。幂等未实现（T-10）。
3. **验证：运行新增 test_contract_errors.py 及现有 API 集成测试；每个适用错误码真实触发且 JSON 合法** → **达成**（见第 3、4 节；503/500 用临时路由并如实记录）。

## 6. 关键决策（需评审知悉）

1. **HTTPBearer 缺 token 403→401 归并**：FastAPI `HTTPBearer(auto_error=True)` 在无 Authorization 头时抛 403 "Not authenticated"，与契约"未认证为 401"冲突。在错误外层统一归并为 401 UNAUTHENTICATED（保留 WWW-Authenticate 头），已认证但无权限仍 403。经 Lead 批准（决策 A），并等价更新 test_auth_api、test_reports_stats_api 两处未登录断言。
2. **5xx 一律通用摘要**：对显式 `HTTPException(5xx)`（如 knowledge.py L541 `f"转换失败：{exc}"` 可能携带异常文本）也不回显 detail，仅写服务端日志；这与"未预期异常不泄密"同口径，收紧了旧行为。
3. **表外状态码兜底**：501 等 5xx 保持原 HTTP 状态、code=INTERNAL_ERROR；其他未映射 4xx code=VALIDATION_ERROR。501 不在契约错误码表内，建议后续任务处理 PDF 导出未实现端点的契约归类。
4. **RequestValidationError details 只报首个错误**：契约 details 仅允许单 field/reason，无法表达错误列表；取 errors()[0]。
5. **测试 500 的客户端处理**：Starlette ServerErrorMiddleware 在发送处理器响应后会重新抛异常，测试用 `ASGITransport(raise_app_exceptions=False)` 读取已发响应（与生产 uvicorn 行为一致）。

## 7. 未验证项 / 遗留

1. **最终全量回归含 test_adb_runner.py 未由本任务执行**：全量首跑时 T-19 正在并行改造 test-tools/common/adb_runner.py，24 个用例瞬时失败（单文件复跑 25 passed，见 pytest-adb-runner-standalone.log）。按 Lead 指示，最终全量回归（不含 ignore）由 Lead 在集成阶段统一执行；本任务证据为 run-02（排除该文件，211 passed）。
2. **503 无生产触发路径**：T-13（ADB 失败关闭）落地后需补真实触发用例；当前仅临时路由覆盖处理器映射。
3. **500 无生产触发路径**：同上用临时路由覆盖；真实路径依赖后续任务注入。
4. **501 端点契约归类未处理**（见决策 3）。
5. **Idempotency-Key 未实现**：T-10 范围。
6. **契约第 2 节要求 message"中文安全摘要"**：pydantic reason 为英文模板（如 "Input should be a valid integer"），未做中文化，作为 details.reason 保留原始校验语义，message 本身已中文化；如验收要求 reason 中文需后续调整。

## 8. 回退说明

- 独立变更集，单任务可回退，不影响其他任务的服务逻辑：
  - `git checkout -- test-platform/backend/app/main.py test-platform/backend/app/api/tasks.py test-platform/backend/tests/integration/test_tasks_api.py test-platform/backend/tests/integration/test_ai_tasks_api.py test-platform/backend/tests/integration/test_auth_api.py test-platform/backend/tests/integration/test_security_hardening.py test-platform/backend/tests/integration/test_tools_api.py test-platform/backend/tests/integration/test_reports_stats_api.py`
  - 删除新增文件：`app/errors.py`、`tests/integration/test_contract_errors.py`
- 回退后恢复旧错误外层（`{"code":500,"message","detail"}` 与 legacy 路径无目标别名）；不涉及数据库、迁移或其他任务的文件。
