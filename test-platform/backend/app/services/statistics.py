"""统一统计 / 进度 / result 聚合口径（V1-06 / T-08）。

本模块是**唯一**的统计口径来源：任务详情、任务列表、WebSocket 进度、Dashboard、
报告与导出都必须复用这里的函数，禁止各消费者另写相反规则。

权威定义见 docs/design/execution-state-machine.md §3/§5/§6：

- 记录（TestRecord）只有 ``pending/running`` 两个非终态和
  ``pass/fail/skip/error/timeout`` 五个终态。
- ``completed_items`` = C = 五类终态记录数；running / pending 均不计入完成。
- ``progress_percent`` = floor(C / N * 100)（N>0，N 为选中测试项数）；N=0 → 0。
- 通过率 = ``pass / (pass + fail + error + timeout) * 100``，skip 不进分母；
  分母为 0 时返回 ``None``（API/WS/报告统一为 JSON number null）。
- 任务业务 ``result`` 仅在 ``status == completed`` 且 ``C == N``、
  无 running、无 pending 时按记录判定：任一 fail/error/timeout → ``failed``，
  否则有 pass → ``passed``，否则（全 skip / 零记录）→ ``None``。
  running / pending / cancelled / 平台 failed 一律 ``None``，不得出现业务 passed/failed。
"""

import math
from typing import Iterable, Optional

# 五类终态（顺序固定，便于计数与展示）
FINAL_STATUSES = ("pass", "fail", "skip", "error", "timeout")
# 计入失败分母的三类（skip 明确排除）
FAILURE_STATUSES = ("fail", "error", "timeout")


def count_statuses(statuses: Iterable[Optional[str]]) -> dict:
    """把记录状态序列计数为 7 类（五类终态 + running + pending）。

    未知状态一律忽略（失败关闭：不会因未知状态被当作 pass）。
    """
    counts = {
        "pass": 0,
        "fail": 0,
        "skip": 0,
        "error": 0,
        "timeout": 0,
        "pending": 0,
        "running": 0,
    }
    for status in statuses:
        if status in counts:
            counts[status] += 1
    return counts


def compute_pass_rate(counts: dict) -> Optional[float]:
    """通过率 = pass/(pass+fail+error+timeout)*100；skip 不进分母，分母 0 → None。"""
    denominator = (
        counts.get("pass", 0)
        + counts.get("fail", 0)
        + counts.get("error", 0)
        + counts.get("timeout", 0)
    )
    if denominator <= 0:
        return None
    return round(counts.get("pass", 0) / denominator * 100, 1)


def _compute_progress(completed_items: int, total_items: int) -> int:
    """progress = floor(C/N*100)，N>0；N=0 → 0（不伪造 100）。"""
    if total_items and total_items > 0:
        return int(math.floor(completed_items / total_items * 100))
    return 0


def compute_task_statistics(
    status: Optional[str],
    total_items: int,
    record_statuses: Iterable[Optional[str]],
) -> dict:
    """任务级统一聚合：result / completed_items / progress / counts / pass_rate。

    参数:
        status: 任务生命周期状态（pending/running/completed/failed/cancelled）。
        total_items: 选中测试项数 N。
        record_statuses: 该任务所有测试记录的状态序列。

    返回 dict:
        total_items, completed_items, progress_percent,
        counts(五类终态), pass_rate(number|None), result(passed/failed/None)。
    """
    counts = count_statuses(record_statuses)
    completed_items = sum(counts[s] for s in FINAL_STATUSES)
    running = counts["running"]
    pending = counts["pending"]
    total = total_items if total_items and total_items > 0 else 0

    progress = _compute_progress(completed_items, total)

    result: Optional[str] = None
    # 仅 completed、C=N、且无 running/pending 时才允许出现业务 passed/failed
    if (
        status == "completed"
        and total > 0
        and completed_items == total
        and running == 0
        and pending == 0
    ):
        if any(counts[s] > 0 for s in FAILURE_STATUSES):
            result = "failed"
        elif counts["pass"] > 0:
            result = "passed"
        else:
            result = None  # 全 skip：completed 但无业务通过/失败

    return {
        "total_items": total,
        "completed_items": completed_items,
        "progress_percent": progress,
        "counts": {s: counts[s] for s in FINAL_STATUSES},
        "pass_rate": compute_pass_rate(counts),
        "result": result,
    }


def summarize_records(record_statuses: Iterable[Optional[str]]) -> dict:
    """记录集合汇总（报告 / 导出用）：五类计数 + 兼容字段 + null 通过率。

    兼容字段 ``passed/failed/skipped`` 保持旧报告消费者可用；``failed`` 含
    timeout（历史展示口径），但 ``pass_rate`` 严格按五类分母计算，skip 不进分母。
    ``counts`` 提供完整五类终态计数。
    """
    statuses = list(record_statuses)
    counts = count_statuses(statuses)
    return {
        "total_items": len(statuses),
        "passed": counts["pass"],
        "failed": counts["fail"] + counts["timeout"],
        "skipped": counts["skip"],
        "error": counts["error"],
        "timeout": counts["timeout"],
        "counts": {s: counts[s] for s in FINAL_STATUSES},
        "pass_rate": compute_pass_rate(counts),
    }


def aggregate_counts(counts_list: Iterable[dict]) -> dict:
    """把多个五类计数 dict 累加为单一五类计数 dict。"""
    total = {s: 0 for s in FINAL_STATUSES}
    for counts in counts_list:
        for s in FINAL_STATUSES:
            total[s] += int((counts or {}).get(s, 0))
    return total


def classify_task_for_dashboard(
    status: Optional[str], total_items: int, record_statuses: Iterable[Optional[str]]
) -> str:
    """Dashboard/趋势任务分类：返回 passed/failed/no_result/execution_failed/cancelled/running/pending。

    - passed/failed：completed 且业务 result 为 passed/failed（仅这两类进入通过率分母）。
    - no_result：completed 但 result=null（全 skip / 零记录）。
    - execution_failed：status=failed（平台异常，不计入业务通过率）。
    - cancelled / running / pending：原状态单列。
    """
    stats = compute_task_statistics(status, total_items, record_statuses)
    if status == "completed":
        if stats["result"] == "passed":
            return "passed"
        if stats["result"] == "failed":
            return "failed"
        return "no_result"
    if status == "failed":
        return "execution_failed"
    if status == "cancelled":
        return "cancelled"
    if status == "running":
        return "running"
    return "pending"


def build_dashboard_breakdown(classified: Iterable[str]) -> dict:
    """把任务分类序列聚合为 Dashboard 分列计数。"""
    keys = (
        "passed",
        "failed",
        "no_result",
        "execution_failed",
        "cancelled",
        "running",
        "pending",
    )
    breakdown = {k: 0 for k in keys}
    for category in classified:
        if category in breakdown:
            breakdown[category] += 1
    return breakdown
