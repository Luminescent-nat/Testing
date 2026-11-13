# RR-V1-DEMO-FINAL-ACCEPT-20261113：V1.0-demo 独立最终验收

- 验收日期：2026-11-13
- 核验人：reviewer（独立复核）
- 验收基线：`cee1628d5c65bcd5722cb9507de795ac48c9153b`
- 验收依据：`RR-V1-DEMO-20261113.md` §6 的 V1.0-demo 最终门禁；不采用提交方口头结论代替实测。
- 验收范围：本机部署、本机浏览器、隔离 SQLite/storage、真实只读 ADB 执行与报告导出。
- 非范围：完整 V1.0 生产上线、Docker/服务器、高并发、daily/once、真实 AI 输出质量、全设备矩阵、配置导入。
- 独立证据：`evidence/v1-demo-final-review-20261113/`。
- 核验开始前工作树干净；本轮未修改产品代码，仅新增本报告及独立证据，未提交 Git。

## 1. 逐条验收结果

| 编号 | 验收标准 | 核验方式 | 实际结果 | 结论 |
|---|---|---|---|---|
| A1 | D-01/D-02/D-03 修复，并有关键边界、异常测试 | 检查实现与测试；独立 Vitest、后端全量、Playwright、监控页专属 Chromium 检查 | D-01 统一 `item_name`，9 项归一化测试覆盖缺失/null/空串/非对象/不改入参；真实浏览器显示“容量校验”，日志弹窗含 MemTotal，无 `undefined`。D-02 空汇总 200、五类计数 0、零分母 null，非空和单任务/批量 404 语义有回归测试。D-03 空态/非空态拆分，非空创建严格断言 201 并轮询 completed，不再接受非法空 `item_ids` | 通过 |
| A2 | D-04 明确新演示库策略，启动脚本与文档一致 | 在独立证据目录执行 `start_demo.ps1 -MigrateOnly`，随后用同一脚本真实启动服务并访问 `/health`、运行 E2E | 空库迁移 001→004，`004_task_deleted_at (head)`；服务 `/health` 返回 healthy；实际使用独立 demo.db 与 storage/demo；历史库 SHA-256 前后均为 `2f919b0544e37618628ac358f1b5684ee16c9253596483b62919166a91b1a789` | 通过 |
| A3 | daily/once 不作为可用演示能力 | 检查创建页并执行创建页 Playwright 用例 | immediate 可选；once/daily 均 disabled 且标注“后续版本”；对应浏览器断言通过 | 通过 |
| A4 | `.env.example` 与演示文档补 AI 配置、无密钥降级和启动步骤 | 检查 `.env.example`、`docs/DEMO.md`、`DEPLOYMENT.md`、AI 规划标签及 Vitest | 七项 LLM 配置齐全；明确 OpenAI-compatible `/chat/completions`；无密钥显示“规则规划（未调用 AI）”，`llm_used===true` 才显示“AI 规划”；未宣称真实外部 AI 已验收 | 通过 |
| A5 | 后端严格全量连续 2 轮 0 failed；前端 Vitest/lint/build 成功 | 当前 HEAD 独立执行两轮 `pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`；执行 npm 三件套 | 后端第 1 轮 **472 passed / 0 failed / 264.71s / EXIT=0**；第 2 轮 **472 passed / 0 failed / 252.00s / EXIT=0**。前端 **7 文件/75 用例通过**；lint **0 errors/988 warnings / EXIT=0**；build 成功 / EXIT=0 | 通过 |
| A6 | Playwright 全绿；空/非空页面无 console/page error/5xx；监控页无 undefined | 隔离服务上运行完整 Playwright；另运行监控页专属 Chromium 脚本 | 完整套件 **16 passed / 0 failed / 0 skipped / EXIT=0**，含空报告 console 0 error、非空 201→completed→详情统计、once/daily disabled。监控页时间线、详情和日志弹窗名称正确；console error=0、page error=0、HTTP 5xx=0 | 通过 |
| A7 | 保留并复跑只读 ADB 全链路：201→pass→completed/passed→报告→HTML 导出 | 本轮未 Mock ADB 的演示服务执行种子只读项，再调用任务、记录、报告和导出 API | 设备 `5c000c2834414751c9d`；任务 1 创建 201；执行 `cat /proc/meminfo | grep MemTotal`；任务 `completed/passed`；记录“容量校验”为 pass；报告 `pass_rate=100.0`；HTML 导出 200、4878 字节，内容含任务名、容量校验、MemTotal 和 100.0% | 通过 |
| A8 | 演示标签明确，不承诺生产/高并发/完整调度/全 AI/全设备矩阵 | 检查 DEMO.md 与提交边界说明 | 文档明确 V1.0-demo 非生产指南；daily/once 禁用；真实 AI 未验证不得宣称；历史库保留只读；范围外事项单列 | 通过 |

## 2. 独立测试证据索引

| 证据 | 结果 |
|---|---|
| `backend-full-r1.log` | 472 passed，EXIT_CODE=0 |
| `backend-full-r2.log` | 472 passed，EXIT_CODE=0 |
| `frontend-vitest.log` | 7 files / 75 tests passed，EXIT_CODE=0 |
| `frontend-lint.log` | 0 errors / 988 warnings，EXIT_CODE=0 |
| `frontend-build.log` | built successfully，EXIT_CODE=0 |
| `demo-migrate.log` | 空库 001→004 head，EXIT_CODE=0，历史库哈希不变 |
| `demo-server.log` | 真实隔离演示服务启动日志 |
| `playwright-full.log` | 16 passed / 0 failed / 0 skipped，EXIT_CODE=0 |
| `browser-monitor-smoke.mjs` / `browser-monitor.log` / `browser-monitor.png` | 监控页专属真实 Chromium 检查，PASS |
| `readonly-report-export.log` / `task-1-report.html` | 当前 HEAD 真实只读任务、报告与 HTML 导出复核，PASS |
| `source-db-final-hash.log` | 所有演示操作后历史库仍保持不变 |

## 3. 非阻塞保留项

1. 前端仍有 **988 个 lint warnings**；本机演示版不阻塞，但不能描述为“前端静态检查零问题”。
2. `start_demo.ps1` 使用绝对自定义路径时，控制台展示会出现 `$Backend/$DemoDbPath` 拼接形式；实际环境变量和运行路径正确，不影响本次功能，建议后续仅修正显示。
3. 非空报告 E2E 当前选择第一个在线设备与第一个测试项；当前种子首项已确认是只读 MemTotal，后续建议固定只读用例标识或增加命令白名单，防止种子顺序变化后执行非预期项目。
4. 真实 AI provider 联调与输出质量未纳入本次验收；当前通过的是配置口、规则降级和展示口径。
5. 历史默认库仍有结构漂移；本次通过的是独立新演示库方案，不是历史数据迁移验收。

## 4. 总体结论

**验收通过：V1.0-demo / 本机演示版。**

八项验收标准全部有当前 HEAD 的独立实际运行结果，无不通过或无法核验项。提交方关于六项修复完成的陈述与本轮实测一致，且本轮补充了提交方原报告未覆盖的监控页浏览器断言和当前 HEAD 的真实只读 ADB/HTML 导出复核。

**该结论不等于完整 V1.0 生产上线通过。** Docker/服务器、高并发、历史数据迁移、daily/once、完整 AI 能力、全设备矩阵和配置导入仍不得据此宣称已验收。

签署：reviewer，2026-11-13。
