# RR-V1-FIX-T20：V1-10 前端 2xx 成功判定与登录/注册 pc_identifier（task-14）

- 评审编号：RR-V1-FIX-T20
- 评审对象/任务编号：V1-10 修订（共享任务 task-14；对应原 T-20 前端）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/README.md` v1.0、`docs/contracts/user-administration-v1.0.md` v1.0（登录/首管理员注册 201、body 含 pc_identifier）、`RR-V1-READINESS-20261112.md` V1-10、`docs/verification/verification-rules-v1.0.md` §7
- 环境与 commit/变更集：Windows 10；Node v24.15.0 / npm 11.6.4；git HEAD `fa70d3b` + 工作区（task-14 未提交变更）。变更：`src/api/client.js`（+withPcIdentifier/createSubmitGuard/isSuccessResponse）、`src/store/user.js`、14 个 views、新增 `src/utils/__tests__/v1-10-success.test.js`、新增 `scripts/check-success-codes.mjs`；前端 diffstat 15 文件 +115/-59
- 证据路径：`docs/verification/tasks/T-20/result.md` §11；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-10-check-success-codes-reviewer.log`、`v1-10-npm-test.log`、`v1-10-npm-lint.log`、`v1-10-npm-build.log`

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 散落 `code===200` 是否真 0 残留 | 独立 `node scripts/check-success-codes.mjs` + 宽正则 grep（含 `===200/==200/.code===200`，排除注释/mock/client 自述） | 脚本 exit 0：残留 0、统一判定 62 处；grep 仅 client.js:459 注释一处 | 通过 |
| 2 | 视图统一走 `isSuccessResponse` | 读 client.js:466（=isSuccessEnvelope 2xx 整数）；抽查 create.vue/login 等 diff | 各视图仅把 `res.code===200` 替换为 `isSuccessResponse(res)`+import | 通过 |
| 3 | 0/false/""/null 语义未被改动 | 读 client.js 未新增 `||` 覆盖；v1-10 测试断言 200/201 两路 falsy 原样 | zero=0/no=false/empty=''/nil=null 保留 | 通过 |
| 4 | pc_identifier 只注入不改业务 | 读 client.js:129 `withPcIdentifier` 返回新对象不改入参；store/user.js、login/index.vue diff | 仅登录/注册/ loginAction 注入 pc_identifier，业务字段不变；单测断言原入参不变 | 通过（注入非业务） |
| 5 | 200/201 双码依据 | 读 result.md §11.4；isSuccessResponse 接受 2xx | 契约登录/注册 201，前端兼容 200/201（后端当前可能 200）；已记录联调依据 | 通过（依据已记录；未与后端实测，环境无后端） |
| 6 | 重复提交保护 | 读 createSubmitGuard:136-150；测试 2 例 | 进行中跳过、异常复位，不重复请求 | 通过 |
| 7 | 独立重跑 npm test | `npm test` | 4 文件 / **43 用例通过**（client 27+v1-10 10+datetime 3+request 3），exit 0 | 通过 |
| 8 | 独立重跑 npm lint | `npm run lint` | 1037 warnings / 0 errors，无新增，exit 0 | 通过 |
| 9 | 独立重跑 npm build | `npm run build` | exit 0（历史 Sass/chunk 告警不变） | 通过 |
| 10 | 未改业务逻辑/超范围 | diff 审阅 | 仅成功判定条件与 pc_identifier 注入，无业务行为改动；未改 backend/test-tools/docs/plan | 通过 |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T20-1 | 204 用例以 `{code:204,data:{}}` 断言，真实 204 空 body 在 client 拦截器会得到空串→isSuccessResponse=false；当前无端点返回真 204 | v1-10-success.test.js:62；client.js isSuccessEnvelope | 潜在边界；当前无实际路径，风险低 | 低 | 记录性/后续联调 |
| P-V1T20-2 | 未与真实后端联调（环境无后端），200/201 双码与 pc_identifier 真实落库未核 | result.md §11.4 | 真实链路属后端联调/最终验收 | 低 | 最终联调 |
| P-V1T20-3 | lint 仍 1037 warning、build 有历史告警 | npm-lint/build 日志 | 属 V1-11/前端最终门禁（T-35），非本任务范围；本轮不得据此判 V1-10 通过全局前端门禁 | 中（范围外） | V1-11/T-35 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 页面级真实浏览器成功流程/201 切换后 UI | 无后端服务、未跑浏览器 | 属 T-22+/最终验收 |
| L2 | 后端是否切 201、幂等头落库 | 后端 switch 属 task-12；本轮仅前端兼容 | 联调后复核 |

## 4. 待用户确认项

无新增（200/201 双码为契约兼容，联调后以真实后端码为准）。

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `node scripts/check-success-codes.mjs` | 残留 0、统一判定 62 处 | 0 | `evidence/v1-fix-20261112/v1-10-check-success-codes-reviewer.log` |
| `npm test` | 43 用例通过（4 文件） | 0 | `v1-10-npm-test.log` |
| `npm run lint` | 1037 warnings / 0 errors | 0 | `v1-10-npm-lint.log` |
| `npm run build` | 构建成功 | 0 | `v1-10-npm-build.log` |

## 6. 最终结论

**通过（V1-10 范围内）。** 49 处散落 `code===200` 已全部改为 `isSuccessResponse`（独立脚本残留计数 0、宽正则 grep 0）；0/false/""/null 语义未改动；登录/注册/ loginAction 仅注入 pc_identifier（不改入参、不改业务）；200/201 双码兼容且依据已记录；重复提交保护纯逻辑可用。独立重跑 test 43 / lint 1037w-0e / build exit0 全部通过。P-V1T20-1/2/3 记为低/范围外限制：**lint/ mock 的前端最终门禁属 V1-11/T-35，本轮不据此判通过**；V1-10 结论不受影响。

## 7. 签名

reviewer，2026-11-12；本记录基于独立脚本、diff 与独立重跑日志作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
