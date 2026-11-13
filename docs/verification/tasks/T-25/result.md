# T-25 空报告汇总空态（演示前收口，实测问题 2）验证记录

- 任务：task-30（演示前后端收口：空报告页 404 → 200 空态）
- 状态：实现完成；聚焦 **31 passed / exit 0**；全量严格回归 **472 passed / 0 failed / exit 0**（265.6s）
- 日期：2026-11-13；未 commit（Lead 统一提交）；契约未改
- 环境：Windows + D:\MCTEST\test-platform\.venv\Scripts\python.exe（Python 3.12.10，pytest 7.4.4，fastapi 0.109.0）

## 1. 问题与修复
- 实测：全新数据库首次进入报告页 `GET /api/v1/reports/summary/all` → 404「未找到可汇总的任务报告」→ 前端报错。
- 修复：`_build_multi_task_report` 新增 `allow_empty` 参数（默认 False），**仅** `get_summary_report`（/reports/summary/all）传 `allow_empty=True`：空库/无任务时返回 `_empty_multi_task_report`（HTTP 200 空汇总）；显式批量导出 `/reports/batch/export` 保持原语义（任一任务不可用整体失败，空集 404）；单任务 `/reports/{id}` 不存在仍 404（未改）。

## 2. 空态响应 shape 样例（HTTP 200）
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "report_version": "1.1",
    "report_type": "batch",
    "report_id": "RPT-BATCH-20261113-XXXXXX",
    "created_at": "2026-11-13T06:00:00",
    "task_count": 0,
    "executor": {"user_id": 1, "username": "admin", "role": "admin"},
    "summary": {
      "total_items": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0, "timeout": 0,
      "counts": {"pass": 0, "fail": 0, "skip": 0, "error": 0, "timeout": 0},
      "pass_rate": null
    },
    "module_statistics": {},
    "tasks": [],
    "results": [],
    "items": [],
    "total": 0
  }
}
```
- 与非空 batch 汇总逐字段同形状（report_version/report_type/report_id/created_at/task_count/executor/summary/module_statistics/tasks/results）；
- 前端空态兼容字段 `items=[]`、`total=0` 仅空态附加（非空响应保持原形状不变）；
- `counts` 复用 statistics.FINAL_STATUSES 口径（五类全 0），`pass_rate` 为 JSON null（非 0 / 非 "0%"），task-16 统计口径与 task-26 导出修复未动（仅新增空态分支）。

## 3. 变更文件
| 文件 | 变更 |
|---|---|
| app/api/reports.py | `_build_multi_task_report(..., allow_empty=False)`；新增 `_empty_multi_task_report(current_user)`；`get_summary_report` 传 `allow_empty=True` |
| tests/integration/test_reports_api.py | 新增 3 用例：空库 200 空态（形状+counts+pass_rate null+items/total+JSON 可序列化）、非空形状/口径不变（task_count、tasks 长度、counts 五键、pass_rate=100.0）、单任务不存在仍 404 |
| tests/integration/test_v1_statistics.py | 新增 1 用例：空态消费字段兼容（counts 五类 0、pass_rate is None 且 !=0、tasks/results 空数组、report_type/version 与非空一致） |

注：另补 1 用例「显式批量导出全部不存在任务仍 404」（test_reports_api.py，共 +4 用例）。

## 4. 命令与退出码（原始日志）
| # | 命令 | 结果 | 日志 |
|---|---|---|---|
| 1 | `pytest tests/integration/test_reports_api.py tests/integration/test_v1_statistics.py tests/integration/test_reports_stats_api.py -q --tb=short -rA` | **31 passed，exit 0**（28.3s） | [pytest-focused.log](pytest-focused.log) |
| 2 | 全量 `pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA` | **472 passed，0 failed，exit 0**（265.6s） | [pytest-full.log](pytest-full.log) |

## 5. DoD 结论
- 空库/无任务 → 200 空汇总（items/tasks 空数组、五类 counts 全 0、pass_rate=null、total=0、形状与非空一致）→ 达成（第 2 节 + 2 个空态用例）。
- 非空库行为不变 → 达成（非空形状/口径用例 + 既有 STAT/导出全量回归 472 passed）。
- 单任务 /reports/{id} 不存在仍 404 → 达成（新增用例）。
- 保持 task-16 统计口径与 task-26 导出修复不动 → 达成（仅新增空态分支；未改 aggregate_counts/compute_pass_rate/导出生成器）。
- 批量导出语义（契约：任一 task_id 不可用整体失败）→ 保持（allow_empty 默认 False，新增 404 用例）。

## 6. 遗留 / 转前端任务
1. **前端 reports 页空态消费**：后端现返回 200 空汇总；若前端把 `tasks=[]`/`items=[]` 仍当错误弹提示或未渲染空态，属前端处理，建议同轮 frontend-contracts 处理（本任务未改 frontend，按 scope 禁止）。
2. 空态额外附加 `items`/`total` 兼容字段仅在空响应出现；若前端统一改用 `tasks`/`summary` 消费，可在前端收口后移除（记录待确认）。
