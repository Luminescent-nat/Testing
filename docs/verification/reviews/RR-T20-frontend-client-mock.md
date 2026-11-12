# RR-T20：前端契约客户端与可追溯 mock

- 评审编号：RR-T20
- 评审对象/任务编号：T-20 建立前端契约客户端并生成 mock
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/README.md` v1.0（2026-11-12 确认）、`docs/contracts/task-execution-v1.0.md` v1.0、`docs/verification/verification-rules-v1.0.md` v1.0 §7、`docs/plan/task-board-v1.0.md` T-20
- 环境与 commit/变更集：Windows 10，Node v24.15.0 / npm 11.6.4；git HEAD `d0b415d` + 工作区未提交变更。被评审变更：
  - 新增 `test-platform/frontend/src/api/client.js`
  - 重写 `test-platform/frontend/src/utils/request.js`（仅委托）
  - 新增 `test-platform/frontend/scripts/generate-contract-mocks.mjs`
  - 生成 `test-platform/frontend/src/mocks/generated/contract-mocks.js`
  - 新增 `test-platform/frontend/src/utils/__tests__/client.test.js`
  - 修改 `test-platform/frontend/package.json`（脚本 `mock:generate`）
- 证据路径：
  - 开发证据：`docs/verification/tasks/T-20/`（result.md、npm-test.log、npm-lint.log、npm-build.log、mock-generate.log、eslint-baseline.json、eslint-after.json、lint-diff-summary.txt）
  - 评审方独立重跑：`docs/verification/reviews/evidence/test-rerun-20261112/`（npm-test.log、npm-lint.log、npm-build.log、mock-generate.log）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 只改声明 scope | `git status`/`git diff HEAD` 核对全部改动文件 | 变更仅 client.js/request.js/generate-contract-mocks.mjs/contract-mocks.js/client.test.js/package.json；未触碰 views/layouts/api/*.js | 通过 |
| 2 | 统一根路径与鉴权/PC 头 | 读 client.js:26,438-457 | `API_BASE_URL='/api/v1'`；请求拦截器注入 `Authorization: Bearer` 与 `X-PC-Identifier` | 通过 |
| 3 | 错误外层归一化（新契约+legacy） | 读 client.js:295-345；单测 normalizeErrorPayload 6 例 | 新 `{code:string,message,details}`；legacy `{detail}`/DRF detail 数组/`{errors}`/数字 code 均映射，`legacy` 标记 | 通过 |
| 4 | 成功响应 0/false/""/null 不丢失 | 读 client.js:460-472；单测 1 例 | 直接返回 `body`，未用 `||` 覆盖 falsy；断言 zero/no/empty/nil/list 原样 | 通过 |
| 5 | Idempotency-Key 仅任务创建/重跑 | 读 client.js:155-226；单测 3 例 | POST /tasks、/tasks/{id}/reruns、legacy rerun-failed、ai natural 附加；devices/refresh、tasks/cancel、GET/PUT 不附加；8～128 可打印 ASCII 校验 | 通过 |
| 6 | 401 登出 | 读 client.js:483-489；单测 1 例 | 401 → userStore.logout() 且归一化 UNAUTHENTICATED | 通过 |
| 7 | request.js 委托保持 api/*.js 兼容 | 读 request.js；grep 全部 `@/utils/request` 导入 | 12 个 api/*.js 仍 `import request from '@/utils/request'`，request.js 默认导出 client 并再导出 getPcIdentifier；错误对象经 ApiError.response 兼容字段与 axios 形状对齐（修复后） | 通过 |
| 8 | mock 明确标注且隔离 | 读 contract-mocks.js 头部；grep 引用 | 第 2 行 `GENERATED MOCK - 仅隔离开发/测试，禁止用于生产/联调`；src 内除自身外 0 处引用 | 通过 |
| 9 | mock 生成确定性 | 两次运行 `npm run mock:generate` 比较 SHA256 | 两次文件 SHA256 均为 `0393196...1EA8E`，digest=ea3fc258efa2，entries=24 | 通过 |
| 10 | mock 来源合规（mock-api） | 检查主机工具 + 生成脚本来源 | 主机无 `mock-api` 命令；mock 由仓库脚本从 `docs/contracts/*.md` 生成 | **偏差（见 P-T20-1）** |
| 11 | 独立重跑 npm test | `npm test` | 3 文件 29 用例通过（client 23 + datetime 3 + request 3），退出码 0 | 通过 |
| 12 | 独立重跑 npm run lint | `npm run lint` | 1037 warnings / 0 errors，退出码 0（与基线一致，无新增） | 通过 |
| 13 | 独立重跑 npm run build | `npm run build` | 退出码 0，6.25s；15 条 legacy-js-api Sass 告警 + 1 条 chunk>500kB（历史告警） | 通过 |
| 14 | 未放宽断言/跳过测试 | 读 client.test.js | 23 用例均真实断言，无 `.skip`/`.only`；request.test.js 未改动仍通过 | 通过 |
| 15 | DoD「请求/响应类型与契约一致」 | 读 client.js JSDoc/导出 | 提供 JSDoc 类型与 ApiError 结构；属 JSDoc 级而非运行时 TS 类型（任务允许 JSDoc） | 通过（JSDoc 级） |

## 2. 问题与风险等级

| # | 问题 | 依据（文件:行/日志） | 影响 | 等级 | 责任/处置 |
|---|---|---|---|---|---|
| P-T20-1 | mock 非 mock-api 生成：主机无 mock-api 工具，改用仓库脚本 `generate-contract-mocks.mjs` 从契约 md 生成。DoD 与验证规则 §7 原文要求"mock 只能来自 mock-api 生成物" | verification-rules-v1.0.md:118；scripts/generate-contract-mocks.mjs:1-15；主机 `Get-Command mock-api` 退出码 1 | 字面不满足 DoD；须按偏差登记，不得声称"mock-api 生成"。**Lead 裁决 U1：接受仓库确定性生成脚本+显式来源标注作为本轮替代，必须标偏差、结论为有条件通过/待用户最终确认** | 中 | T-20；已按 U1 处置，mock 头部已如实标注为偏差产物 |
| P-T20-2 | 错误对象形状变化影响 1 处视图：request.js 由 axios 实例改为委托 client 后，失败 Promise 由 `axios Error`（带 `.response`）变为 `ApiError`（原无 `.response`）。`reports/index.vue:528` 读 `error?.response?.status === 404` | client.js:350-371,474-491（修复前）；reports/index.vue:528 | 报告页请求 404（无报告）时静默置空逻辑失效，误弹"获取报告失败"。UX 级兼容回归，非数据损坏 | 中 | **已修复（2026-11-12 增量复核通过）**：ApiError 新增 `response={status,data}` 兼容字段（client.js:359-380），错误拦截器与 HTTP200+legacy 数字码分支均注入快照（client.js:487-508）；`error?.response?.status===404` 行为恢复。新用例 3 条覆盖（client.test.js:243-273） |
| P-T20-3 | `isSuccessEnvelope` 对 `code` 缺失/非数字非字符串的响应体判为成功（比旧实现宽松） | client.js:402-408（修复前） | 若有 legacy 端点返回无 code 裸对象，行为从"拒绝"变"放行" | 低 | **已修复（收紧，2026-11-12 增量复核通过）**：client.js:424-428 收紧为"非对象/数组/无 code/非 2xx 整数 → 异常"，与旧 `request.js` 的 `res.code!==200` 语义一致；blob/arraybuffer 已在拦截器最前放行不受影响。新用例 1 条覆盖（client.test.js:196-200） |
| P-T20-4 | 幂等键对 `/ai/tasks/natural` 也自动附加（legacy AI 创建） | client.js:159 | 多余请求头，服务端忽略；无害 | 低 | 记录性 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 与真实后端联调的错误码/details 真实返回 | 环境无后端服务；仅按契约样例与单测验证 | 真实错误外层契约一致性属后端任务/最终联调 |
| L2 | 服务端幂等去重/并发唯一 | 后端职责，前端不可证 | 由 T-10 后端验证 |
| L3 | 浏览器真实请求链路与 UI 反馈 | 属 T-22+ 页面走查 | 本轮不签浏览器行为 |
| L4 | mock-api 官方生成物对比 | 无该工具 | 只能以仓库脚本确定性为准 |

## 4. 待用户确认项

| # | 事项 | 建议决定 |
|---|---|---|
| U1 | mock 生成方式偏差（P-T20-1） | Lead 已裁决：接受仓库确定性脚本+显式标注为临时替代，T-20 结论"有条件通过/待用户最终确认"，不得写成 mock-api 生成物。用户最终确认后可将 mock 用于隔离开发；真实联调仍须切真实 API |
| U2 | reports/index.vue 404 兼容（P-T20-2） | 建议在 T-20 或 T-25 改为 `error?.httpStatus ?? error?.response?.status`，避免 404 误弹错误 | **已按 ApiError.response 兼容字段修复，无需用户确认** |

## 5. 独立重跑记录

### 5.1 首轮（2026-11-12，修复前）

| 命令 | 数量/结果 | 退出码 | 独立日志 |
|---|---|---:|---|
| `npm test` | 3 文件 / 29 用例通过（client.test.js 23） | 0 | `evidence/test-rerun-20261112/npm-test.log` |
| `npm run lint` | 1037 warnings / 0 errors | 0 | `evidence/test-rerun-20261112/npm-lint.log` |
| `npm run build` | 构建成功 6.25s；15×legacy-js-api +1×chunk>500kB | 0 | `evidence/test-rerun-20261112/npm-build.log` |
| `npm run mock:generate`（×2） | entries=24，digest ea3fc258efa2，两次 SHA256 相同 `0393196…1EA8E` | 0 | `evidence/test-rerun-20261112/mock-generate.log` |

### 5.2 增量复核（2026-11-12，P-T20-2/P-T20-3 修复后）

| 命令 | 数量/结果 | 退出码 | 独立日志 |
|---|---|---:|---|
| `npm test` | 3 文件 / **33 用例**通过（client.test.js 27，新增 4） | 0 | `evidence/test-rerun-20261112/npm-test-after-fix.log` |
| `npm run lint` | 1037 warnings / 0 errors（无新增） | 0 | `evidence/test-rerun-20261112/npm-lint-after-fix.log` |
| `npm run build` | 构建成功；15×legacy-js-api（与基线一致） | 0 | `evidence/test-rerun-20261112/npm-build-after-fix.log` |
| mock 文件 SHA256 复核 | `0393196…1EA8E` 不变（修复未触碰 mock） | — | 与 5.1 相同 |

代码复核（增量）：ApiError 增 `response={status,data}` 兼容字段并注入两种错误路径（client.js:359-380,487-508）；`isSuccessEnvelope` 收紧为与旧实现一致（client.js:424-428）；新增 4 条用例（client.test.js:196-200,243-273）覆盖裸响应体异常语义、404 response 快照、HTTP200+legacy 数字码快照、网络错误 response=null；T-20/result.md §7 已如实记录修复。均在声明 scope 内，无越界。

重跑后 `git status` 仅见 T-20/T-21 预期文件，无越界改动。

## 6. 最终结论

**有条件通过（待用户最终确认）。** 契约客户端核心能力（统一路径、鉴权/PC 头、错误外层归一化、0/false/null 保留、幂等键、401 登出）经代码审阅与单测（27 用例）+ 独立重跑 test(33)/lint/build 全部通过，DoD 主体满足。首轮评审提出的 P-T20-2（404 兼容）与 P-T20-3（成功外层语义）**均已于 2026-11-12 修复并通过增量复核**（§5.2）。唯一剩余条件：**P-T20-1 mock 非 mock-api 生成**，按 Lead 裁决 U1 记为已登记偏差，须用户最终确认后方可用于隔离开发，不得声称替代 mock-api 或用于真实联调。该条件确认前，本结论维持"有条件通过/待用户最终确认"，不得作为最终验收通过。

## 7. 签名

reviewer，2026-11-12；本记录基于原始代码、单测与独立重跑日志作出，未代开发修改任何代码。
