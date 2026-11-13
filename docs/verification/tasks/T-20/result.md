# T-20 验证记录：前端契约客户端与可追溯 mock

## 1. 任务
按 `docs/contracts/README.md` v1.0 建立统一 API client（`/api/v1`、Bearer + `X-PC-Identifier` 注入、错误外层解析兼容 legacy、401 登出、任务创建/重跑 `Idempotency-Key`、响应 data 中 `0/false/""/null` 不丢失、JSDoc 类型），并把 `request.js` 改为委托新 client 以保持现有 `api/*.js` 与响应结构兼容；mock 由仓库内确定性脚本生成并明确标注。

## 2. 变更文件
| 文件 | 类型 | 说明 |
|---|---|---|
| `test-platform/frontend/src/api/client.js` | 新增 | 统一契约客户端：路径/鉴权/PC 标识/错误归一化/幂等键/401/成功外层保留 |
| `test-platform/frontend/src/utils/request.js` | 重写 | 仅委托 `@/api/client`，保留默认导出与 `getPcIdentifier` 命名导出（视图与 api/*.js 零改动） |
| `test-platform/frontend/scripts/generate-contract-mocks.mjs` | 新增 | 从 `docs/contracts/*.md` 的 JSON 样例确定性生成 mock |
| `test-platform/frontend/src/mocks/generated/contract-mocks.js` | 生成 | 头部标注 `GENERATED MOCK - 仅隔离开发/测试，禁止用于生产/联调` |
| `test-platform/frontend/src/utils/__tests__/client.test.js` | 新增 | 27 个 Vitest 用例 |
| `test-platform/frontend/package.json` | 修改 | 新增脚本 `mock:generate`、`check:tokens` |

## 3. 环境
- OS：Windows（工作目录 `D:\MCTEST\test-platform\frontend`）
- Node：v24.15.0；npm：11.6.4；`node_modules` 已存在
- 契约版本：v1.0（docs/contracts/README.md，2026-11-12 确认）

## 4. 命令与退出码
最终复跑（含评审修复 P-T20-2/P-T20-3 之后，2026-11-12）：
| 命令 | 开始 | 结束 | 退出码 | 原始日志 |
|---|---|---|---|---|
| `npm test` | 2026-11-12 11:57:46.623 | 2026-11-12 11:57:48.059 | 0 | `npm-test.log` |
| `npm run lint` | 2026-11-12 11:57:48.079 | 2026-11-12 11:57:49.332 | 0 | `npm-lint.log` |
| `npm run build` | 2026-11-12 11:57:49.334 | 2026-11-12 11:57:55.997 | 0 | `npm-build.log` |
| `npm run mock:generate` | 2026-11-12 11:47:52.891 | 2026-11-12 11:47:53.253 | 0 | `mock-generate.log` |

（首轮记录 2026-11-12 11:47:38～11:47:52：test/lint/build 退出码均为 0；日志已被最终复跑覆盖，评审修复记录见第 7 节。）

`npm test` 结果：3 个测试文件、33 个用例全部通过（其中客户端用例 27 个；原 datetime 3、request 3）。`request.test.js` 未改动且继续通过，证明 `request.js` 委托后 `getPcIdentifier` 行为兼容。

## 5. DoD 逐条证据
- **请求/响应类型与契约一致，错误 details 可读，0/false/null 不丢失**
  - `client.js` 对成功外层、错误外层、Idempotency 配置与 ApiError 均提供 JSDoc 类型；`normalizeErrorPayload`/`toApiError` 输出 `{code, rawMessage, details, httpStatus, legacy}`。
  - 用例「成功响应保留 data 中的 0/false/\"\"/null/[]」：断言 `zero=0`、`no=false`、`empty=''`、`nil=null`、`list=[]` 全部原样保留（未使用 `||` 覆盖 falsy）。
  - 用例「新契约错误外层被归一化为 ApiError」：`code=VALIDATION_ERROR`、`details.field=custom_parameters.12.count` 可读；「legacy {detail}」「legacy DRF detail 数组」「legacy {errors}」「legacy 数字 code」均通过。
- **鉴权与 PC 标识**：用例「注入 Bearer token 与 X-PC-Identifier」验证 `Authorization: Bearer jwt-abc` 与 `X-PC-Identifier` 头。
- **401 登出**：用例「401 触发登出」断言 `logout` 被调用 1 次且错误归一化为 `UNAUTHENTICATED/401`。
- **错误对象向后兼容 `.response`**（评审修复 P-T20-2）：ApiError 同时提供 `response = { status, data }` 与 `.httpStatus/.code/.details/.rawMessage/.legacy`；既有视图 `src/views/reports/index.vue:528` 的 `error?.response?.status === 404` 在报告不存在时恢复为静默置空（未改任何视图）。用例「ApiError 携带与 httpStatus 一致的 response 兼容字段」「HTTP 200 + legacy 数字错误码时 response.status 与 httpStatus 一致」「无 response 的网络错误保留 response=null」通过。
- **Idempotency-Key 仅任务创建/重跑**：`shouldAttachIdempotencyKey` 对 `POST /tasks`、`/tasks/{id}/reruns`、legacy `/tasks/{id}/rerun-failed`、`/ai/tasks/natural` 为 true，对 `POST /devices/refresh`、`POST /tasks/{id}/cancel`、`GET /tasks`、`PUT /tasks/{id}` 为 false；用例「自动附加合法 Idempotency-Key」「调用方传入原样使用」「非幂等请求不附加」通过。
- **幂等键格式 8～128 可打印 ASCII**：`isValidIdempotencyKey` 边界用例通过（7 位/129 位/换行/中文均拒绝）。
- **mock 明确标注且仅隔离开发/测试，可切换真实 API**
  - 生成文件第 2 行即 `GENERATED MOCK - 仅隔离开发/测试，禁止用于生产/联调`，并含 `source-digest`。
  - `scripts/generate-contract-mocks.mjs` 只读 `docs/contracts/*.md`，不联网、不含时间戳；连续两次生成 SHA256 一致（确定性），本次 digest=`ea3fc258efa2`，共 24 个接口条目。
  - mock 未被 `main.js`/任何视图导入，生产构建不引用；联调时直接使用真实 axios client 即可切换，无耦合。
  - 偏差：当前环境无 `mock-api` 工具，故以本脚本替代，**需用户确认**（详见第 7 节）。

## 6. 既有告警与新增告警对比
- **ESLint**：改动前基线（`eslint-baseline.json`，42 文件）1037 warnings / 0 errors；评审修复复跑后（`eslint-after.json`，45 文件）1037 warnings / 0 errors。逐文件对比无一项告警数变化；新增 3 个 JS 文件均 0/0。**未引入新 error 或新 warning**。
- **Build**：`legacy-js-api` Sass 弃用告警 15 条、`chunks are larger than 500 kB` 1 条，均与改动前基线一致（历史告警，T-35 处理范围）；无 CJS 错误、无 Sass 编译错误。退出码 0。
- 未通过关闭规则、排除文件或删除测试达成。

## 7. 评审修复记录（RR-T20，2026-11-12）
- **P-T20-2（必须修，已修）**：`src/api/client.js` 的 ApiError 新增兼容字段 `response = { status, data }`（错误拦截器与 HTTP 200 + legacy 数字错误码分支均注入；无 response 的网络错误为 `null`），保留 `.httpStatus/.code/.details/.rawMessage/.legacy`。未改任何视图文件；`src/views/reports/index.vue:528` 的 `error?.response?.status === 404` 行为恢复。
- **P-T20-3（评估，已收紧）**：原实现把"无 `code` 的裸响应体"判为成功，比旧实现（`res.code !== 200` 即拒绝）宽松。复核结论：blob/arraybuffer 在响应拦截器最前已提前返回，不经过该判断；仓库内所有视图均依赖 `res.code === 200`，旧实现同样拒绝无 code 响应体，因此无保留宽松语义的必要。已收紧为：非对象/数组/无 `code`/`code` 非 2xx 整数 → 视为异常并走错误归一化；用例「无 code 的裸响应体按旧实现语义视为异常」覆盖（`{}`/`null`/`'raw'`/`[1,2,3]` 均为 false）。影响面：行为与旧 `request.js` 一致，视图无感。
- 复跑结果见第 4 节：test 33 用例全绿、lint 0 error/新增 0 warning、build exit 0。

## 8. 未验证项 / 需用户确认偏差
- **需用户确认**：环境缺少 `mock-api` 工具，`src/mocks/generated/contract-mocks.js` 由本地确定性脚本生成，属已登记偏差；在获得用户确认前不得将其用于真实联调或声称替代 mock-api。
- 未与真实后端联调（环境无后端服务），错误码/details 的真实返回仅按契约样例验证。
- 未在浏览器实测真实页面请求链路与 UI 反馈（属 T-22+ / 页面走查范围）。
- 幂等键服务端去重/并发唯一性属后端契约验证，非前端可证。

## 9. 回退说明
- 单独还原 `src/api/client.js`（删除）与 `src/utils/request.js`（恢复原文件）即可回到旧实现；`api/*.js` 与视图无需改动。
- 删除 `src/mocks/generated/contract-mocks.js` 与 `scripts/generate-contract-mocks.mjs`，并移除 `package.json` 的 `mock:generate`（及 `check:tokens`）脚本。
- 上述回退不影响页面业务逻辑；若仅回退 P-T20-2/P-T20-3 兼容修复，需同步回退 `client.test.js` 对应用例。

## 10. 证据文件
- `npm-test.log`、`npm-lint.log`、`npm-build.log`、`mock-generate.log`
- `eslint-baseline.json`、`eslint-after.json`、`lint-diff-summary.txt`

## 11. V1-10 修订记录：统一 2xx 成功判定 + 登录/注册 pc_identifier（2026-11-12）

### 11.1 任务与改动
- **① 统一成功判定**：`src/api/client.js` 新增 `isSuccessResponse(body)`（2xx 整数 `code` 的成功外层，200/201/204 均成功；字符串码/非 2xx/无 code 为失败；不改动 `data` 取值，`0/false/""/null` 语义保持）。全部散落的 `res.code === 200`（49 处）替换为 `isSuccessResponse(res)`，涉及文件：
  - `src/store/user.js`（2）、`src/views/login/index.vue`（2）、`src/views/tasks/monitor.vue`（3）、`src/views/tasks/create.vue`（4）、`src/views/tasks/index.vue`（3）、`src/views/dashboard/index.vue`（5）、`src/views/devices/index.vue`（3）、`src/views/modules/index.vue`（3）、`src/views/knowledge/index.vue`（11）、`src/views/reports/index.vue`（4）、`src/views/memory/index.vue`（4）、`src/views/admin/users.vue`（3）、`src/views/profile/index.vue`（2）、`src/views/ai-test/index.vue`（1）。
  - 每个文件新增 `import { isSuccessResponse } from '@/api/client'`；未改动任何业务分支、跳转、提示语或数据取值。
- **② 登录/注册契约字段**：`src/api/client.js` 新增 `withPcIdentifier(payload)`（读取 `getPcIdentifier()` 并附加 `pc_identifier`，不改入参）。`src/views/login/index.vue` 的注册与登录请求体、`src/store/user.js` 的 `loginAction` 均通过 `withPcIdentifier(...)` 注入 `pc_identifier`，符合 `docs/contracts/user-administration-v1.0.md`（登录/首管理员注册字段要求）。登录/注册成功码兼容 200/201（`isSuccessResponse` 接受 2xx）。
- **③ 重复提交保护**：`src/api/client.js` 新增纯逻辑 `createSubmitGuard()`（进行中跳过重复调用，异常时复位）；视图既有按钮 `:disabled`/`:loading` 守卫（login `:disabled="loading"`、create `:disabled="!canStart"` + `:loading="starting"`）保持不变，未改视图提交逻辑。
- **④ 静态检查**：新增 `scripts/check-success-codes.mjs`，扫描 `src/**/*.{js,vue}` 输出统一判定使用点与残留 `===200` 计数（退出码 0）。

### 11.2 命令与退出码（2026-11-12 16:30 复跑）
| 命令 | 开始 | 结束 | 退出码 | 原始日志 |
|---|---|---|---|---|
| `npm test` | 16:30:54.571 | 16:30:56.104 | 0 | `npm-test.log` |
| `npm run lint` | 16:30:56.126 | 16:30:57.901 | 0 | `npm-lint.log` |
| `npm run build` | 16:30:57.903 | 16:31:05.325 | 0 | `npm-build.log` |
| `node scripts/check-success-codes.mjs` | 16:31:05.326 | 16:31:05.382 | 0 | `v1-10-success-codes.log` |

### 11.3 DoD 证据
- **200/201 成功**：新增 `src/utils/__tests__/v1-10-success.test.js`（10 用例）「200/201/204 成功外层均判定为成功」「201 成功响应保留 data 中的 0/false/\"\"/null」；全量 `npm test` 4 个测试文件 **43 用例全绿**（datetime 3 + client 27 + v1-10 10 + request 3）。
- **0/false/空串保留**：201 与 200 两条用例分别断言 `zero=0`、`no=false`、`empty=''`、`nil=null` 原样保留。
- **错误外层**：用例断言 400 `VALIDATION_ERROR` 带 `details.field` 被拒绝并归一化；字符串码/非 2xx/无 code 均判失败。
- **重复提交按钮禁用不重复请求**：`createSubmitGuard` 用例断言并发 3 次触发仅发起 1 次请求、其余返回 undefined、结束后可再次提交、异常后不锁死。
- **登录/注册 pc_identifier**：`withPcIdentifier` 用例断言请求体新增 `pc_identifier`（复用持久化标识，缺失时自动生成）且不修改原对象；登录/注册调用点（login/index.vue、store/user.js loginAction）均已接入。
- **改动点与残留计数**：`v1-10-success-codes.log` 统一判定使用 62 处（含测试），**残留 `code ===/== 200` 计数 0**（`src/api/client.js` 与生成 mock 已排除/仅注释）。
- **lint 不新增**：ESLint 基线 1037 warnings/0 errors → 修改 14 个视图/存储文件 + 新增 1 个测试文件后仍 **1037 warnings/0 errors**（46 文件，逐文件告警数无变化）；build 退出码 0，历史告警（Sass legacy-js-api 15 条 + chunk>500kB 1 条）不变。

### 11.4 联调依据与遗留
- 联调依据：契约 `user-administration-v1.0.md` 登录成功 201、首管理员注册成功 201；当前后端可能仍返回 200，前端 `isSuccessResponse` 同时接受 200/201，双码兼容待后端切换后核对（未与后端实测，环境无后端服务）。
- 遗留：`createSubmitGuard` 为共享纯逻辑，视图仍用各自 `:disabled/:loading` 守卫（遵守“不得改视图业务逻辑”约束）；如需统一可后续在 T-23+ 接入。
- `scripts/check-success-codes.mjs` 未注册 npm 脚本（`package.json` 不在本任务写范围），以 `node scripts/check-success-codes.mjs` 直接执行。

## 12. 演示前 AI 规划标注（task-29，2026-11-13）
- **需求**：AI 页按 `plan.llm_used` 展示规划方式，true→「AI 规划」，false/缺失→「规则规划（未调用 AI）」，不得宣称调用 AI。
- **实现**：`src/utils/aiTask.js` 的 `buildPlanPreview` 归一化 `llmUsed = rawPlan.llm_used === true`；
  `src/views/ai-test/index.vue` 预览面板新增「规划方式」`el-tag`（success/info 两态，文案严格按上表）。
  `plan` 为 null/缺失时仍显示「该任务无规划快照」，不显示规划方式标签（避免误标）。
- **测试**：`src/utils/__tests__/ai-task.test.js` 新增用例验证 `llm_used=true/false/缺失` 三种归一；
  现有 plan 完整/部分缺失断言同步更新（`task29-ai-task-vitest.log`：10 passed，exit 0）。
- **产品/演示决策留痕**：预览面板保留（承接 task-28 决策），规划方式按后端真实 `llm_used` 标注；
  未调用 LLM 时明确写「规则规划（未调用 AI）」，不把规则解析包装成 AI 能力。
- **三件套**（详见 `../T-35-demo/result.md`）：`npm test` 75 用例全绿 exit 0；
  `npm run lint` 988 warnings/0 errors exit 0（ai-test/index.vue 基线 4→2，新增文件 0/0，无新增告警）；
  `npm run build` exit 0。
- **未验证**：未浏览器实测标签渲染（无后端/前端服务），真实 `plan.llm_used` 由后端 `ai_tasks.py`
  写入 `plan["llm_used"] = planner.llm_invoked`，仅静态核对。
