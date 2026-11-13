# T-24 前端监控页测试项名称修复（task-29，演示前收口）

- 任务：task-29（演示前前端收口：监控项名称）
- 日期：2026-11-13
- 依据：用户实测问题 1：监控页误用 `item.name`，契约 `TestRecord` 字段为 `item_name`，日志出现 `DDR/undefined`
- 工作目录：`D:\MCTEST\test-platform\frontend`

## 1. 缺陷与修复
- 契约事实（`docs/contracts/task-execution-v1.0.md` TestRecord）：名称字段为 `item_name`、模块为 `module_name`；`item.name` 不存在。
- 全量替换监控页名称读取点：
  - 执行流程时间线 `node-name`：`item.name` → `item.item_name`；
  - 测试项列表 `item-name`：`item.name` → `item.item_name`；
  - 详情/日志抽屉：`currentLog` 经 `normalizeRecord` 归一（优先后端 `item_name/module_name`，回退当前记录）；
  - 全局日志面板条目：`=== ${module_name} / ${item.name} ===` → `formatRecordTitle(item)`；
  - 记录列表与 WS 推送的 `completed_results` / `current_item` 均经 `normalizeRecords` / `normalizeRecord` 归一。
- 新增纯函数 `src/utils/monitorRecord.js`：`normalizeRecord`（`item_name` 非空保留，缺失/null/空串/纯空白 → 「未知测试项」；`module_name` 回退 `module.name` 再空串）、`normalizeRecords`、`formatRecordTitle`；**不读取 legacy `item.name`**，不修改入参。

## 2. 变更文件（diff 摘要）
| 文件 | 变更 |
|---|---|
| `src/views/tasks/monitor.vue` | 时间线/列表名称 `item.name`→`item.item_name`；`fetchTaskData` 用 `normalizeRecords`；WS `completed_results/current_item` 归一；日志抽屉 `currentLog` 经 `normalizeRecord`；全局日志标题用 `formatRecordTitle` |
| `src/utils/monitorRecord.js`（新增） | `UNKNOWN_ITEM_NAME` / `normalizeRecord` / `normalizeRecords` / `formatRecordTitle` |
| `src/utils/__tests__/monitor-record.test.js`（新增） | 9 用例：有 item_name、缺失、null、空串、纯空白、legacy item.name 不读取、module 回退、空/非对象、不改入参、批量与标题无 undefined |

## 3. 验证
| 项 | 结果 |
|---|---|
| `npx vitest run src/utils/__tests__/monitor-record.test.js` | 9 passed，exit 0（`monitor-record-vitest.log`） |
| 全量 `npm test` | 7 文件 75 用例全绿，exit 0（`../T-35-demo/npm-test.log`） |
| `npm run lint` | 988 warnings / 0 errors，exit 0；monitor.vue 基线 63 → 63（无新增） |
| `npm run build` | exit 0，历史告警不变（`../T-35-demo/npm-build.log`） |

## 4. 未验证项
- 未做浏览器实测（无后端/前端服务）：时间线/列表/日志抽屉在真实运行下的名称展示属页面走查；WS 实时推送路径需真实任务执行验证。
- 后端 `TestRecord.item_name` 已由契约与 schemas 确认；未改 backend/契约。
