# T-35-demo 演示前前端收口统一验证记录（task-29）

- 任务：task-29（演示前前端收口：监控项名称、daily/once 禁用、AI 规划标注、报告 E2E 修复）
- 日期：2026-11-13
- 工作目录：`D:\MCTEST\test-platform\frontend`
- 环境：Node v24.15.0 / npm 11.6.4；未 git commit；未改 backend、契约文档、其它视图
- 相关证据：`../T-24/result.md`（监控）、`../T-25/result.md`（报告 E2E）、`../T-20/result.md` 第 12 节（AI 标注）

## 1. 改动清单（diff 摘要）
| 文件 | 变更 |
|---|---|
| `src/utils/monitorRecord.js`（新增） | `normalizeRecord` / `normalizeRecords` / `formatRecordTitle` / `UNKNOWN_ITEM_NAME`：契约 `item_name` 归一，缺失→「未知测试项」，不读 legacy `item.name` |
| `src/utils/__tests__/monitor-record.test.js`（新增） | 9 用例：有/无 item_name、null、空串、纯空白、module 回退、空入参、不改入参、标题无 undefined |
| `src/views/tasks/monitor.vue` | 时间线 `node-name`、列表 `item-name` 改 `item.item_name`；`fetchTaskData`/WS `completed_results`/`current_item`/日志抽屉/全局日志标题全部经纯函数归一 |
| `src/views/tasks/create.vue` | 演示版禁用 `once`/`daily` 单选（`disabled` + 「（后续版本）」标注），仅保留立即执行；`canStart`/提交逻辑未改 |
| `src/utils/aiTask.js` | `buildPlanPreview` 增加 `llmUsed = plan.llm_used === true` 归一化 |
| `src/utils/__tests__/ai-task.test.js` | 新增 `llm_used=true/false/缺失` 用例；plan 断言同步（共 10 用例） |
| `src/views/ai-test/index.vue` | 预览面板新增「规划方式」标签：true→「AI 规划」，false/缺失→「规则规划（未调用 AI）」 |
| `tests/e2e/task-workflow.spec.js`（整文件重写） | 报告用例拆空态/非空态；非空态从 API 取在线设备+合法 item、创建严格断言 201、轮询 completed、进详情验证统计/通过率；无数据 skip 带原因；选择器更新为当前 DOM；创建页用例追加 daily/once disabled 断言 |

## 2. 产品/演示决策留痕
1. **保留 AI 预览面板**（承接 task-28 决策），数据源改为 `getTaskDetail(id)` 的 `plan` 快照；本轮补「规划方式」标注，未调用 LLM 不得宣称 AI。
2. **演示版仅立即执行**：`once`（T-11）/`daily`（T-12）调度能力未实施，选项 disabled 并标注「后续版本」，避免演示触发不可用流程。
3. **空报告页**：后端 task-30 将汇总接口 404 改为 200 空态；前端维持「404 静默置空、其余错误提示」逻辑，空态 `.el-empty` 无错误提示、无 console error（E2E 空态用例覆盖）。
4. **E2E 非空报告必须真实创建**：禁止 `item_ids=[]` 与静默接受创建失败；无设备/无 item 明确 `test.skip` 并注明原因（不算通过）。

## 3. 命令与退出码（2026-11-13 14:25）
| 命令 | 开始 | 结束 | 退出码 | 日志 |
|---|---|---|---|---|
| `npm test` | 14:25:28.164 | 14:25:29.885 | 0 | `npm-test.log` |
| `npm run lint` | 14:25:29.903 | 14:25:31.207 | 0 | `npm-lint.log` |
| `npm run build` | 14:25:31.209 | 14:25:38.562 | 0 | `npm-build.log` |
| `npx playwright test tests/e2e/task-workflow.spec.js --list` | 14:25:38.563 | 14:25:39.720 | 0 | `playwright-list.log` |
| 实跑 E2E（前置缺失） | 14:25:51.923 | — | 1（前置缺失，非用例失败） | `e2e-blocked-prereq.log` |

- `npm test`：**7 个测试文件 75 用例全绿**（新增 monitor-record 9、ai-task 10；既有 v1-06 13 / client 27 / v1-10 10 / datetime 3 / request 3）。
- `npm run lint`：**988 warnings / 0 errors**（上一轮 992 → 988：create.vue 25→21、ai-test 4→2；monitor.vue 63→63；新增文件与 E2E spec 均 0/0）。**未新增任何 error/warning**，未关规则/排除文件。
- `npm run build`：exit 0（6.6s），历史告警不变：Sass legacy-js-api 15 条、chunk>500kB 1 条。
- Playwright `--list`：exit 0，发现 4 tests（setup + 创建页选择 + 报告空态 + 非空报告），spec 语法/发现正常。

## 4. E2E 实跑前置（本机缺服务，未执行）
本机未启动后端/前端/一次性隔离库，实跑在 `global-setup.mjs:12` 被拒：
`运行 E2E 前必须设置 E2E_DATABASE_URL 为一次性隔离数据库`（exit 1，日志 `e2e-blocked-prereq.log`）。
由 Lead 统一准备后执行：
1. `E2E_DATABASE_URL` 指向一次性隔离空库（`E2E_TEST_MODE=1`，禁默认库）；
2. 后端 `http://localhost:8000` 启动（`global-setup` 写入固定管理员 e2e-admin/e2e-admin-pass）；
3. 前端 `http://localhost:3000` 启动（`npm run dev` 或 `FRONTEND_URL` 指定）；
4. 至少 1 台在线设备 + 1 个合法测试项（否则非空报告用例按设计 skip 并标原因）；
5. frontend 下执行 `npx playwright test tests/e2e/task-workflow.spec.js`（空态用例排在非空态前，需全新库）。

## 5. 未验证项 / 风险
- 实跑 Playwright 未执行（前置服务缺失），真实创建→completed→报告详情链路待 Lead 起服务后确认；若设备不可执行，非空态会在轮询后以 completed 断言失败（如实暴露）。
- 未浏览器实测监控页名称、daily/once 禁用态、AI 规划标签渲染（无前后端服务）。
- `auth.setup.spec.js` 仍用 legacy `/auth/login`、`/auth/register` 且断言 register 200；若后端改契约 201 需另行同步（不在本任务写范围，已记入 `../T-25/result.md`）。
- 后端 task-30（汇总空态 200）尚未联调；前端 404 静默置空逻辑已兼容两种返回。
