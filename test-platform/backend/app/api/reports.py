import asyncio
import io
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.database import get_db, AsyncSessionLocal
from app.api.auth import get_current_user
from app.models import User, TestTask, TestRecord, TestItem, TestModule
from app.schemas import ExportFormat, ResponseModel
from app.models import FailurePattern
from app.services.knowledge_matcher import get_device_knowledge

router = APIRouter(prefix="/reports", tags=["报告管理"])


async def _match_failure_patterns(db: AsyncSession, record: TestRecord) -> List[dict]:
    """为测试记录匹配失败模式（只读，不更新计数）。"""
    if record.status not in ("fail", "error", "timeout"):
        return []

    result = await db.execute(select(FailurePattern))
    patterns = result.scalars().all()

    text = f"{record.output or ''}\n{record.fail_reason or ''}"
    matches = []
    for pattern in patterns:
        if re.search(pattern.pattern, text, re.IGNORECASE):
            matches.append({
                "pattern_id": pattern.id,
                "name": pattern.name,
                "category": pattern.category,
                "description": pattern.description,
                "suggested_fix": pattern.suggested_fix
            })
    return matches

 
def _build_verdict_basis(status: str, item: TestItem, record: TestRecord) -> str:
    """生成判定依据说明。"""
    if status == "skip":
        return f"设备不满足兼容性要求或测试项被跳过：{record.fail_reason or ''}"
    if status == "error":
        return f"执行过程异常：{record.fail_reason or ''}"
    if status == "timeout":
        return f"执行超时：{record.fail_reason or ''}"
    if status == "pass":
        if item.judgement_type == "assertion":
            return "断言规则校验通过"
        if item.judgement_type == "rubric":
            return "评分规则达到及格线"
        return "AI 兜底判定通过"
    if status == "fail":
        if item.judgement_type == "assertion":
            return f"断言规则未通过：{record.fail_reason or ''}"
        if item.judgement_type == "rubric":
            return f"评分规则未达标：{record.fail_reason or ''}"
        return f"AI 兜底判定失败：{record.fail_reason or ''}"
    return ""

logger = logging.getLogger(__name__)


def _task_report_dir(task_id: int) -> str:
    """任务报告落盘目录：REPORTS_PATH/task_{id}。"""
    return os.path.join(get_settings().REPORTS_PATH, f"task_{task_id}")


def _write_report_file(file_path: str, content: bytes) -> None:
    """报告内容落盘（best-effort，失败仅记日志，不影响响应与任务收尾）。"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as exc:
        logger.warning("报告落盘失败 %s: %s", file_path, exc)


def _read_report_file(file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        return f.read()


async def _check_report_permission(db: AsyncSession, task_id: int, current_user: User) -> None:
    """返回落盘文件前的轻量权限校验（口径与 _build_report 一致）。"""
    result = await db.execute(select(TestTask).where(TestTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限查看报告")


def _render_report_content(report_data: dict, format: ExportFormat) -> bytes:
    """同步生成报告字节内容（重计算，async 上下文中需经 asyncio.to_thread 调用）。"""
    if format == ExportFormat.JSON:
        return json.dumps(report_data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    if format == ExportFormat.MARKDOWN:
        return _generate_markdown(report_data).encode("utf-8")
    if format == ExportFormat.WORD:
        return _generate_word(report_data)
    if format == ExportFormat.EXCEL:
        return _generate_excel(report_data)
    if format == ExportFormat.HTML:
        return _generate_html(report_data).encode("utf-8")
    if format == ExportFormat.PDF:
        raise HTTPException(status_code=501, detail="PDF 导出待后续实现")
    raise HTTPException(status_code=400, detail="不支持的导出格式")


# 导出格式与落盘文件扩展名 / 响应 Content-Type 的映射
_EXPORT_EXTS = {
    ExportFormat.JSON: "json",
    ExportFormat.MARKDOWN: "md",
    ExportFormat.WORD: "docx",
    ExportFormat.EXCEL: "xlsx",
    ExportFormat.HTML: "html",
}

_EXPORT_MEDIA_TYPES = {
    ExportFormat.JSON: "application/json",
    ExportFormat.MARKDOWN: "text/markdown",
    ExportFormat.WORD: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ExportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.HTML: "text/html",
}


async def generate_task_report_files(task_id: int) -> None:
    """任务收尾时后台生成 JSON + HTML 报告落盘，并回填 report_path（相对 REPORTS_PATH）。

    供 TaskExecutor 以 asyncio.create_task 调用；所有异常在此吞掉并记日志，
    绝不影响任务收尾。Word/Excel 较重，不在此生成，由导出接口按需生成并缓存。
    """
    try:
        async with AsyncSessionLocal() as db:
            task = await db.get(TestTask, task_id)
            if not task:
                return
            user = await db.get(User, task.user_id)
            if not user:
                logger.warning("任务 %s 的执行人不存在，跳过报告生成", task_id)
                return
            report_data = await _build_report(db, task_id, user)
            json_content = json.dumps(report_data, ensure_ascii=False, indent=2, default=str)
            # HTML 生成是同步 CPU 计算，放到 worker 线程避免阻塞事件循环
            html_content = await asyncio.to_thread(_generate_html, report_data)
            report_dir = _task_report_dir(task_id)
            await asyncio.to_thread(
                _write_report_file,
                os.path.join(report_dir, "report.json"),
                json_content.encode("utf-8"),
            )
            await asyncio.to_thread(
                _write_report_file,
                os.path.join(report_dir, "report.html"),
                html_content.encode("utf-8"),
            )
            task.report_path = f"task_{task_id}/report.json"
            await db.commit()
    except Exception:
        logger.exception("任务 %s 后台报告生成失败", task_id)


async def _build_report(db: AsyncSession, task_id: int, current_user: User) -> dict:
    """构建单个任务的完整测试报告数据。"""
    result = await db.execute(
        select(TestTask)
        .options(joinedload(TestTask.device))
        .where(TestTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限查看报告")

    records_result = await db.execute(
        select(TestRecord, TestItem, TestModule)
        .join(TestItem, TestRecord.item_id == TestItem.id)
        .join(TestModule, TestItem.module_id == TestModule.id)
        .where(TestRecord.task_id == task_id)
        .order_by(TestRecord.id)
    )
    record_rows = records_result.all()

    if task.completed_at and task.started_at:
        duration_seconds = int((task.completed_at - task.started_at).total_seconds())
        minutes, seconds = divmod(duration_seconds, 60)
        total_duration = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"
    else:
        total_duration = "-"

    passed = sum(1 for row in record_rows if row[0].status == "pass")
    failed = sum(1 for row in record_rows if row[0].status in ("fail", "timeout"))
    skipped = sum(1 for row in record_rows if row[0].status == "skip")
    error = sum(1 for row in record_rows if row[0].status == "error")
    total = len(record_rows)
    pass_rate = f"{passed / total * 100:.1f}%" if total > 0 else "0%"

    # 加载设备相关知识库洞察
    knowledge_insights = []
    if task.device:
        try:
            knowledge_insights = await get_device_knowledge(
                db, task.device,
                entry_types=["device_profile", "baseline", "rule", "failure_pattern"],
                limit=10
            )
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.warning("加载报告知识库洞察失败: %s", exc)

    results = []
    for record, item, module in record_rows:
        # 实际结果：优先使用结构化提取数据，否则取输出摘要
        actual_result = record.extracted_data
        if not actual_result and record.output:
            actual_result = (record.output or "")[:500]

        # 判定依据说明
        verdict_basis = _build_verdict_basis(record.status, item, record)

        result_item = {
            "item_id": item.id,
            "item_name": item.name,
            "module_name": module.name,
            "status": record.status,
            "execution_time": record.execution_time,
            "fail_reason": record.fail_reason,
            "extracted_data": record.extracted_data,
            "output_summary": (record.output or "")[:500] if record.output else None,
            "actual_result": actual_result,
            "judgement_type": item.judgement_type,
            "conditional_rules": item.conditional_rules,
            "rubric_criteria": item.rubric_criteria,
            "result_parse": item.result_parse,
            "compatibility": item.compatibility,
            # 标准测试卡字段
            "objective": item.objective,
            "precondition": item.precondition,
            "steps": item.steps,
            "expected_result": item.expected_result,
            "verdict_basis": verdict_basis,
        }

        # 失败/错误/超时时匹配失败模式库，给出修复建议
        if record.status in ("fail", "error", "timeout"):
            matches = await _match_failure_patterns(db, record)
            result_item["failure_patterns"] = matches
            result_item["suggested_fix"] = matches[0]["suggested_fix"] if matches else None

        results.append(result_item)

    return {
        "report_version": "1.0",
        "report_type": "single",
        "report_id": f"RPT-{task.created_at.strftime('%Y%m%d')}-{task.id:03d}",
        "task_id": task.id,
        "task_name": task.name,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "total_duration": total_duration,
        "executor": {
            "user_id": task.user_id,
            "username": current_user.username,
            "role": current_user.role
        },
        "device": {
            "serial_number": task.device.serial_number if task.device else None,
            "model": task.device.model if task.device else None,
            "brand": task.device.brand if task.device else None,
            "android_version": task.device.android_version if task.device else None,
            "cpu_abi": task.device.cpu_abi if task.device else None
        },
        "summary": {
            "total_items": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "error": error,
            "pass_rate": pass_rate
        },
        "knowledge_insights": knowledge_insights,
        "results": results
    }


async def _build_multi_task_report(
    db: AsyncSession,
    task_ids: List[int],
    current_user: User
) -> dict:
    """构建多个任务的聚合总报告。"""
    reports = []
    for task_id in task_ids:
        try:
            report = await _build_report(db, task_id, current_user)
            reports.append(report)
        except HTTPException:
            continue

    if not reports:
        raise HTTPException(status_code=404, detail="未找到可汇总的任务报告")

    total_items = sum(r["summary"]["total_items"] for r in reports)
    passed = sum(r["summary"]["passed"] for r in reports)
    failed = sum(r["summary"]["failed"] for r in reports)
    skipped = sum(r["summary"]["skipped"] for r in reports)
    error = sum(r["summary"]["error"] for r in reports)
    pass_rate = f"{passed / total_items * 100:.1f}%" if total_items > 0 else "0%"

    module_stats = {}
    all_results = []
    for report in reports:
        for result in report["results"]:
            module_name = result["module_name"]
            if module_name not in module_stats:
                module_stats[module_name] = {
                    "total": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0,
                    "running": 0, "pending": 0
                }
            status_map = {
                "pass": "passed",
                "fail": "failed",
                "timeout": "failed",
                "skip": "skipped",
                "error": "error",
                "running": "running",
                "pending": "pending",
                "unknown": "error"
            }
            module_stats[module_name]["total"] += 1
            module_stats[module_name][status_map.get(result["status"], "error")] += 1

            all_results.append({
                **result,
                "task_id": report["task_id"],
                "task_name": report["task_name"],
                "device_model": report["device"]["model"],
                "device_serial": report["device"]["serial_number"]
            })

    return {
        "report_version": "1.1",
        "report_type": "batch",
        "report_id": f"RPT-BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "created_at": datetime.now(),
        "task_count": len(reports),
        "executor": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role
        },
        "summary": {
            "total_items": total_items,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "error": error,
            "pass_rate": pass_rate
        },
        "module_statistics": module_stats,
        "tasks": [
            {
                "task_id": r["task_id"],
                "task_name": r["task_name"],
                "device_model": r["device"]["model"],
                "device_serial": r["device"]["serial_number"],
                "pass_rate": r["summary"]["pass_rate"],
                "total_items": r["summary"]["total_items"],
                "created_at": r["created_at"]
            }
            for r in reports
        ],
        "results": all_results
    }


def _extract_extcsd(results: list) -> dict:
    """从结果中提取 EXT_CSD 数据。"""
    for r in results:
        if "EXT_CSD" in (r.get("item_name") or ""):
            ed = r.get("extracted_data") or {}
            if ed and "mmc_node" in ed:
                return ed
    return {}


def _extract_perf_results(results: list) -> list:
    """提取性能测试结果。"""
    perf = []
    for r in results:
        name = r.get("item_name", "")
        if "性能" in name and "稳定性" not in name:
            ed = r.get("extracted_data") or {}
            perf.append({
                "name": name,
                "status": r.get("status"),
                "bw_mbps": ed.get("bw_mbps"),
                "iops": ed.get("iops"),
                "max_iops": ed.get("max_iops"),
                "lat_p999_us": ed.get("lat_p999_us"),
                "cpu_total": round((ed.get("cpu_usr", 0) or 0) + (ed.get("cpu_sys", 0) or 0), 2),
                "emmc_util": ed.get("emmc_util"),
                "rounds": ed.get("rounds"),
            })
    return perf


def _extract_stability_results(results: list) -> list:
    """提取稳定性测试结果（含曲线图）。"""
    stability = []
    for r in results:
        name = r.get("item_name", "")
        if "稳定性" in name:
            ed = r.get("extracted_data") or {}
            rounds_data = ed.get("rounds_data", [{}])
            rd = rounds_data[0] if rounds_data else {}
            stability.append({
                "name": name,
                "status": r.get("status"),
                "chart_base64": ed.get("chart_base64", ""),
                "bw_mean": rd.get("bw_stats_mbps", {}).get("mean"),
                "bw_cv": rd.get("bw_stats_mbps", {}).get("cv"),
                "iops_mean": rd.get("iops_stats", {}).get("mean"),
                "iops_cv": rd.get("iops_stats", {}).get("cv"),
                "curve_points": len(rd.get("curve", {}).get("bw", [])),
            })
    return stability


def _generate_markdown(report_data: dict) -> str:
    """生成 Markdown 格式报告（参考标准测试卡）。"""
    lines = []
    is_batch = report_data.get("report_type") == "batch"

    lines.append(f"# EMMC 性能测试与验证报告\n")
    lines.append(f"**报告 ID**：{report_data['report_id']}\n\n")

    if is_batch:
        lines.append(f"- 报告类型：批量汇总\n")
        lines.append(f"- 汇总任务数：{report_data['task_count']}\n")
    else:
        lines.append(f"## 1. 基本信息\n\n")
        lines.append(f"| 项目 | 内容 |\n|---|---|\n")
        lines.append(f"| 任务名称 | {report_data.get('task_name', '-')} |\n")
        lines.append(f"| 设备型号 | {report_data['device'].get('model', '-')} |\n")
        lines.append(f"| 设备序列号 | {report_data['device'].get('serial_number', '-')} |\n")
        lines.append(f"| Android 版本 | {report_data['device'].get('android_version', '-')} |\n")
        lines.append(f"| CPU 架构 | {report_data['device'].get('cpu_abi', '-')} |\n")
        lines.append(f"| 执行人 | {report_data['executor'].get('username', '-')} ({report_data['executor'].get('role', '-')}) |\n")
        lines.append(f"| 总耗时 | {report_data.get('total_duration') or '-'} |\n")
        lines.append(f"| 生成时间 | {report_data.get('created_at')} |\n")

    summary = report_data["summary"]
    lines.append("\n## 2. 汇总统计\n\n")
    lines.append("| 总项数 | 通过 | 失败 | 跳过 | 错误 | 通过率 |\n")
    lines.append("|---|---|---|---|---|---|\n")
    lines.append(
        f"| {summary['total_items']} | {summary['passed']} | {summary['failed']} | "
        f"{summary['skipped']} | {summary['error']} | {summary['pass_rate']} |\n"
    )

    if not is_batch:
        # 主要性能参数
        extcsd = _extract_extcsd(report_data["results"])
        if extcsd:
            lines.append("\n## 3. 主要性能参数\n\n")
            lines.append("| 参数 | 解析结果 | 影响 |\n")
            lines.append("|---|---|---|\n")
            lines.append(f"| 缓存 Cache Size | {extcsd.get('cache_size', 'N/A')} | 文件读写性能 |\n")
            lines.append(f"| 最大数据包(读取) | {extcsd.get('max_packed_reads', 'N/A')} | 并发读取能力 |\n")
            lines.append(f"| 最大数据包(写入) | {extcsd.get('max_packed_writes', 'N/A')} | 并发写入能力 |\n")
            lines.append(f"| TRIM Multiplier | {extcsd.get('trim_multiplier', 'N/A')} | 操作效率及寿命 |\n")
            lines.append(f"| 容量 | {extcsd.get('capacity_gib', 'N/A')} GiB | 实际容量 |\n")
            lines.append(f"| 睡眠电流(VCC/VCCQ) | {extcsd.get('sleep_current_vcc', '-')}/{extcsd.get('sleep_current_vccq', '-')} | 休眠功耗 |\n")
            lines.append(f"| HC WP Group Size | {extcsd.get('hc_wp_group_size', 'N/A')} | 写保护分组尺寸 |\n")
            lines.append(f"| 休眠唤醒超时 | {extcsd.get('sleep_awake_timeout', 'N/A')} | 唤醒响应时长 |\n")
            lines.append(f"| CMDQ 深度 | {extcsd.get('cmdq_depth', 'N/A')} | 随机并发提速 |\n")
            card_type = str(extcsd.get('card_type', 'N/A')).replace('\n', '<br>')
            lines.append(f"| 驱动强度 Card Type | {card_type} | 支持下行频率 |\n")

        # 基础性能测试
        perf_results = _extract_perf_results(report_data["results"])
        if perf_results:
            lines.append("\n## 4. 基础性能测试（FIO）\n\n")
            lines.append("| 测试项 | 状态 | 带宽(MB/s) | IOPS | MAX IOPS | P99.9延迟(us) | CPU(%) | EMMC利用率(%) |\n")
            lines.append("|---|---|---|---|---|---|---|---|\n")
            for p in perf_results:
                lines.append(
                    f"| {p['name']} | {p['status']} | {p['bw_mbps'] or '-'} | "
                    f"{p['iops'] or '-'} | {p['max_iops'] or '-'} | {p['lat_p999_us'] or '-'} | "
                    f"{p['cpu_total'] or '-'} | {p['emmc_util'] or '-'} |\n"
                )

        # 稳定性测试
        stability_results = _extract_stability_results(report_data["results"])
        if stability_results:
            lines.append("\n## 5. EMMC 稳定性测试\n\n")
            lines.append(
                "> 测试背景：挂载底层稳定性跑速，高负载队列下输出图表，持续压测运行观察带宽、IOPS 数据下沉情况。\n\n"
            )
            for s in stability_results:
                lines.append(f"### {s['name']}\n\n")
                lines.append("| 指标 | 数值 |\n|---|---|\n")
                lines.append(f"| 状态 | {s['status']} |\n")
                lines.append(f"| BW 均值(MB/s) | {s['bw_mean'] or '-'} |\n")
                lines.append(f"| BW 变异系数 CV | {s['bw_cv'] or '-'}% |\n")
                lines.append(f"| IOPS 均值 | {s['iops_mean'] or '-'} |\n")
                lines.append(f"| IOPS 变异系数 CV | {s['iops_cv'] or '-'}% |\n")
                lines.append(f"| 曲线采样点数 | {s['curve_points']} |\n")
                if s['chart_base64']:
                    lines.append(f"\n![{s['name']}]({s['chart_base64']})\n\n")
                lines.append(f"**分析**：整体读写速率与 IOPS 利用率浮动情况如上所示。\n\n")

        # 可靠性寿命
        if extcsd:
            lines.append("\n## 6. 可靠性寿命估算\n\n")
            lines.append(f"- Life Time Type A: `{extcsd.get('life_time_type_a', 'N/A')}`\n")
            lines.append(f"- Life Time Type B: `{extcsd.get('life_time_type_b', 'N/A')}`\n")
            lines.append(f"- PRE EOL Info: `{extcsd.get('pre_eol_info', 'N/A')}`\n")
            lines.append("> 请根据以上数据进行综合评估。\n")

    if is_batch and report_data.get("module_statistics"):
        lines.append("\n## 模块统计\n\n")
        lines.append("| 模块 | 总项数 | 通过 | 失败 | 跳过 | 错误 |\n")
        lines.append("|---|---|---|---|---|---|\n")
        for module, stats in report_data["module_statistics"].items():
            lines.append(
                f"| {module} | {stats['total']} | {stats['passed']} | {stats['failed']} | "
                f"{stats['skipped']} | {stats['error']} |\n"
            )

    lines.append("\n## 7. 标准测试卡详情\n\n")
    for r in report_data["results"]:
        lines.append(f"### {r['module_name']} / {r['item_name']}（{r['status']}）\n\n")
        lines.append(f"- **测试目的**：{r.get('objective') or '未配置'}\n")
        lines.append(f"- **前置条件**：{r.get('precondition') or '无特殊前置条件'}\n")
        steps = r.get('steps') or '未配置'
        lines.append(f"- **测试步骤**：\n\n```\n{steps}\n```\n\n")
        lines.append(f"- **预期结果**：{r.get('expected_result') or '未配置'}\n")
        actual = r.get('actual_result')
        if isinstance(actual, dict):
            actual_str = json.dumps(actual, ensure_ascii=False, indent=2)
        else:
            actual_str = actual or '-'
        lines.append(f"- **实际结果**：\n\n```\n{actual_str}\n```\n\n")
        lines.append(f"- **判定依据**：{r.get('verdict_basis') or ''}\n")
        if r.get('suggested_fix'):
            lines.append(f"- **修复建议**：{r['suggested_fix']}\n")
        if r['status'] in ('fail', 'error', 'timeout'):
            lines.append(f"- **失败原因**：{r.get('fail_reason') or ''}\n")
        lines.append("\n")

    if not is_batch:
        lines.append("\n## 8. 结论与建议\n\n")
        failed_items = [r for r in report_data["results"] if r['status'] in ('fail', 'error', 'timeout')]
        skipped_items = [r for r in report_data["results"] if r['status'] == 'skip']
        if not failed_items and not skipped_items:
            lines.append("- 所有测试项均通过，设备当前状态符合预期。\n")
        else:
            if failed_items:
                lines.append(f"- 存在 {len(failed_items)} 个失败/错误项，建议优先排查。\n")
            if skipped_items:
                lines.append(f"- 存在 {len(skipped_items)} 个跳过项，请确认设备兼容性与测试项配置。\n")
            for r in failed_items:
                fix = r.get('suggested_fix')
                lines.append(f"- {r['module_name']}/{r['item_name']}：{fix or r.get('fail_reason') or '请查看日志排查'}\n")

    return "".join(lines)


def _generate_word(report_data: dict) -> bytes:
    """生成 Word 格式报告（参考标准测试卡），返回 docx 字节流。"""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少 python-docx 依赖")

    def add_table(doc, headers, rows):
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr_cells = table.rows[0].cells
        for i, h in enumerate(headers):
            hdr_cells[i].text = str(h)
            for para in hdr_cells[i].paragraphs:
                for run in para.runs:
                    run.font.bold = True
        for row in rows:
            cells = table.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = str(v) if v is not None else ""
        return table

    is_batch = report_data.get("report_type") == "batch"
    doc = Document()

    # 标题
    title = doc.add_heading("EMMC 性能测试与验证报告", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"报告 ID：{report_data['report_id']}", style="Intense Quote").alignment = WD_ALIGN_PARAGRAPH.CENTER

    if is_batch:
        doc.add_paragraph(f"报告类型：批量汇总")
        doc.add_paragraph(f"汇总任务数：{report_data['task_count']}")
    else:
        device = report_data.get("device", {})
        # 1. 基本信息
        doc.add_heading("1. 基本信息", level=1)
        add_table(doc,
                  ["项目", "内容"],
                  [
                      ["任务名称", report_data.get("task_name", "-")],
                      ["设备型号", device.get("model", "-")],
                      ["设备序列号", device.get("serial_number", "-")],
                      ["Android 版本", device.get("android_version", "-")],
                      ["CPU 架构", device.get("cpu_abi", "-")],
                      ["执行人", f"{report_data['executor'].get('username', '-')} ({report_data['executor'].get('role', '-')})"],
                      ["总耗时", report_data.get("total_duration") or "-"],
                      ["生成时间", str(report_data.get("created_at"))],
                  ])

    # 2. 汇总统计
    doc.add_heading("2. 汇总统计", level=1)
    summary = report_data["summary"]
    add_table(doc,
              ["总项数", "通过", "失败", "跳过", "错误", "通过率"],
              [[summary["total_items"], summary["passed"], summary["failed"],
                summary["skipped"], summary["error"], summary["pass_rate"]]])

    if is_batch and report_data.get("module_statistics"):
        doc.add_heading("模块统计", level=1)
        rows = []
        for module, stats in report_data["module_statistics"].items():
            rows.append([module, stats["total"], stats["passed"], stats["failed"], stats["skipped"], stats["error"]])
        add_table(doc, ["模块", "总项数", "通过", "失败", "跳过", "错误"], rows)

    if not is_batch:
        results = report_data["results"]
        extcsd = _extract_extcsd(results)

        # 3. 主要性能参数
        if extcsd:
            doc.add_heading("3. 主要性能参数", level=1)
            card_type = str(extcsd.get("card_type", "N/A")).replace("\n", "; ")
            add_table(doc,
                      ["参数", "解析结果", "影响"],
                      [
                          ["缓存 Cache Size", extcsd.get("cache_size", "N/A"), "文件读写性能"],
                          ["最大数据包(读取)", extcsd.get("max_packed_reads", "N/A"), "并发读取能力"],
                          ["最大数据包(写入)", extcsd.get("max_packed_writes", "N/A"), "并发写入能力"],
                          ["TRIM Multiplier", extcsd.get("trim_multiplier", "N/A"), "操作效率及寿命"],
                          ["容量", f"{extcsd.get('capacity_gib', 'N/A')} GiB", "实际容量"],
                          ["睡眠电流(VCC/VCCQ)", f"{extcsd.get('sleep_current_vcc', '-')}/{extcsd.get('sleep_current_vccq', '-')}", "休眠功耗"],
                          ["HC WP Group Size", extcsd.get("hc_wp_group_size", "N/A"), "写保护分组尺寸"],
                          ["休眠唤醒超时", extcsd.get("sleep_awake_timeout", "N/A"), "唤醒响应时长"],
                          ["CMDQ 深度", extcsd.get("cmdq_depth", "N/A"), "随机并发提速"],
                          ["驱动强度 Card Type", card_type, "支持下行频率"],
                      ])

        # 4. 基础性能测试（FIO）
        perf_results = _extract_perf_results(results)
        if perf_results:
            doc.add_heading("4. 基础性能测试（FIO）", level=1)
            rows = []
            for p in perf_results:
                rows.append([
                    p["name"], p["status"],
                    p["bw_mbps"] if p["bw_mbps"] is not None else "-",
                    p["iops"] if p["iops"] is not None else "-",
                    p["max_iops"] if p["max_iops"] is not None else "-",
                    p["lat_p999_us"] if p["lat_p999_us"] is not None else "-",
                    p["cpu_total"] if p["cpu_total"] is not None else "-",
                    p["emmc_util"] if p["emmc_util"] is not None else "-",
                ])
            add_table(doc,
                      ["测试项", "状态", "带宽(MB/s)", "IOPS", "MAX IOPS", "P99.9延迟(us)", "CPU(%)", "EMMC利用率(%)"],
                      rows)

        # 5. 稳定性测试
        stability_results = _extract_stability_results(results)
        if stability_results:
            doc.add_heading("5. EMMC 稳定性测试", level=1)
            doc.add_paragraph(
                "测试背景：挂载底层稳定性跑速，高负载队列下输出图表，持续压测运行观察带宽、IOPS 数据下沉情况。",
                style="Intense Quote"
            )
            for s in stability_results:
                doc.add_heading(s["name"], level=2)
                add_table(doc,
                          ["指标", "数值"],
                          [
                              ["状态", s["status"]],
                              ["BW 均值(MB/s)", s["bw_mean"] if s["bw_mean"] is not None else "-"],
                              ["BW 变异系数 CV", f"{s['bw_cv']}%" if s["bw_cv"] is not None else "-"],
                              ["IOPS 均值", s["iops_mean"] if s["iops_mean"] is not None else "-"],
                              ["IOPS 变异系数 CV", f"{s['iops_cv']}%" if s["iops_cv"] is not None else "-"],
                              ["曲线采样点数", s["curve_points"]],
                          ])
                if s["chart_base64"]:
                    try:
                        import base64
                        img_data = s["chart_base64"]
                        if "," in img_data:
                            img_data = img_data.split(",", 1)[1]
                        image_bytes = io.BytesIO(base64.b64decode(img_data))
                        doc.add_paragraph("BW/IOPS 曲线图：")
                        doc.add_picture(image_bytes, width=Inches(5.5))
                    except Exception as e:
                        doc.add_paragraph(f"[图表嵌入失败：{e}]")
                doc.add_paragraph("分析：整体读写速率与 IOPS 利用率浮动情况如上所示。")

        # 6. 可靠性寿命估算
        if extcsd:
            doc.add_heading("6. 可靠性寿命估算", level=1)
            doc.add_paragraph(f"Life Time Type A：{extcsd.get('life_time_type_a', 'N/A')}")
            doc.add_paragraph(f"Life Time Type B：{extcsd.get('life_time_type_b', 'N/A')}")
            doc.add_paragraph(f"PRE EOL Info：{extcsd.get('pre_eol_info', 'N/A')}")
            doc.add_paragraph("请根据以上数据进行综合评估。", style="Intense Quote")

    # 7. 标准测试卡详情
    doc.add_heading("7. 标准测试卡详情", level=1)
    for r in report_data["results"]:
        doc.add_heading(f"{r['module_name']} / {r['item_name']}（{r['status']}）", level=2)
        add_table(doc,
                  ["字段", "内容"],
                  [
                      ["测试目的", r.get("objective") or "未配置"],
                      ["前置条件", r.get("precondition") or "无特殊前置条件"],
                      ["测试步骤", r.get("steps") or "未配置"],
                      ["预期结果", r.get("expected_result") or "未配置"],
                      ["实际结果", json.dumps(r.get("actual_result"), ensure_ascii=False) if isinstance(r.get("actual_result"), dict) else (r.get("actual_result") or "-")],
                      ["判定依据", r.get("verdict_basis") or ""],
                      ["修复建议", r.get("suggested_fix") or ""],
                      ["失败原因", r.get("fail_reason") or ""],
                  ])

    # 8. 结论与建议
    doc.add_heading("8. 结论与建议", level=1)
    failed_items = [r for r in report_data["results"] if r['status'] in ('fail', 'error', 'timeout')]
    skipped_items = [r for r in report_data["results"] if r['status'] == 'skip']
    if not failed_items and not skipped_items:
        doc.add_paragraph("所有测试项均通过，设备当前状态符合预期。")
    else:
        if failed_items:
            doc.add_paragraph(f"存在 {len(failed_items)} 个失败/错误项，建议优先排查。")
        if skipped_items:
            doc.add_paragraph(f"存在 {len(skipped_items)} 个跳过项，请确认设备兼容性与测试项配置。")
        for r in failed_items:
            fix = r.get('suggested_fix')
            doc.add_paragraph(f"- {r['module_name']}/{r['item_name']}：{fix or r.get('fail_reason') or '请查看日志排查'}")

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


def _generate_excel(report_data: dict) -> bytes:
    """生成 Excel 格式报告，返回 xlsx 字节流。"""
    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少 openpyxl 依赖")

    is_batch = report_data.get("report_type") == "batch"
    wb = Workbook()
    ws = wb.active
    ws.title = "测试报告"

    ws.append(["报告ID", report_data["report_id"]])
    if is_batch:
        ws.append(["报告类型", "批量汇总"])
        ws.append(["汇总任务数", report_data["task_count"]])
    else:
        ws.append(["任务名称", report_data.get("task_name", "-")])
        ws.append(["设备", f"{report_data['device']['model']} ({report_data['device']['serial_number']})"])
        ws.append(["总耗时", report_data.get("total_duration") or "-"])
    ws.append(["生成时间", str(report_data.get("created_at"))])
    ws.append([])

    summary = report_data["summary"]
    ws.append(["总项数", "通过", "失败", "跳过", "错误", "通过率"])
    ws.append([
        summary["total_items"], summary["passed"], summary["failed"],
        summary["skipped"], summary["error"], summary["pass_rate"]
    ])
    ws.append([])

    if is_batch and report_data.get("module_statistics"):
        ws.append(["模块", "总项数", "通过", "失败", "跳过", "错误"])
        for module, stats in report_data["module_statistics"].items():
            ws.append([
                module, stats["total"], stats["passed"], stats["failed"],
                stats["skipped"], stats["error"]
            ])
        ws.append([])

    ws.append(["模块", "测试项", "状态", "耗时(秒)", "失败原因", "测试目的", "前置条件", "预期结果", "判定依据", "修复建议", "提取数据"])
    for r in report_data["results"]:
        ws.append([
            r["module_name"],
            r["item_name"],
            r["status"],
            r["execution_time"] or 0,
            r.get("fail_reason") or "",
            r.get("objective") or "",
            r.get("precondition") or "",
            r.get("expected_result") or "",
            r.get("verdict_basis") or "",
            r.get("suggested_fix") or "",
            json.dumps(r.get("extracted_data") or {}, ensure_ascii=False)[:500]
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()


def _generate_html(report_data: dict) -> str:
    """生成 HTML 格式报告（参考标准测试卡）。"""
    is_batch = report_data.get("report_type") == "batch"
    device = report_data.get("device", {})
    summary = report_data["summary"]
    results = report_data["results"]

    summary_html = f"""
    <table>
        <tr><th>总项数</th><th>通过</th><th>失败</th><th>跳过</th><th>错误</th><th>通过率</th></tr>
        <tr>
            <td>{summary['total_items']}</td>
            <td>{summary['passed']}</td>
            <td>{summary['failed']}</td>
            <td>{summary['skipped']}</td>
            <td>{summary['error']}</td>
            <td>{summary['pass_rate']}</td>
        </tr>
    </table>
    """

    device_html = ""
    if not is_batch:
        device_html = f"""
        <h2>1. 基本信息</h2>
        <table>
            <tr><th>项目</th><th>内容</th></tr>
            <tr><td>任务名称</td><td>{report_data.get('task_name', '-')}</td></tr>
            <tr><td>设备型号</td><td>{device.get('model', '-')}</td></tr>
            <tr><td>设备序列号</td><td>{device.get('serial_number', '-')}</td></tr>
            <tr><td>Android 版本</td><td>{device.get('android_version', '-')}</td></tr>
            <tr><td>CPU 架构</td><td>{device.get('cpu_abi', '-')}</td></tr>
            <tr><td>执行人</td><td>{report_data['executor'].get('username', '-')} ({report_data['executor'].get('role', '-')})</td></tr>
            <tr><td>总耗时</td><td>{report_data.get('total_duration') or '-'}</td></tr>
            <tr><td>生成时间</td><td>{report_data.get('created_at')}</td></tr>
        </table>
        """

    extcsd = _extract_extcsd(results)
    extcsd_html = ""
    if extcsd and not is_batch:
        card_type = str(extcsd.get('card_type', 'N/A')).replace('\n', '<br>')
        extcsd_html = f"""
        <h2>3. 主要性能参数</h2>
        <table>
            <tr><th>参数</th><th>解析结果</th><th>影响</th></tr>
            <tr><td>缓存 Cache Size</td><td>{extcsd.get('cache_size', 'N/A')}</td><td>文件读写性能</td></tr>
            <tr><td>最大数据包(读取)</td><td>{extcsd.get('max_packed_reads', 'N/A')}</td><td>并发读取能力</td></tr>
            <tr><td>最大数据包(写入)</td><td>{extcsd.get('max_packed_writes', 'N/A')}</td><td>并发写入能力</td></tr>
            <tr><td>TRIM Multiplier</td><td>{extcsd.get('trim_multiplier', 'N/A')}</td><td>操作效率及寿命</td></tr>
            <tr><td>容量</td><td>{extcsd.get('capacity_gib', 'N/A')} GiB</td><td>实际容量</td></tr>
            <tr><td>睡眠电流(VCC/VCCQ)</td><td>{extcsd.get('sleep_current_vcc', '-')}/{extcsd.get('sleep_current_vccq', '-')}</td><td>休眠功耗</td></tr>
            <tr><td>HC WP Group Size</td><td>{extcsd.get('hc_wp_group_size', 'N/A')}</td><td>写保护分组尺寸</td></tr>
            <tr><td>休眠唤醒超时</td><td>{extcsd.get('sleep_awake_timeout', 'N/A')}</td><td>唤醒响应时长</td></tr>
            <tr><td>CMDQ 深度</td><td>{extcsd.get('cmdq_depth', 'N/A')}</td><td>随机并发提速</td></tr>
            <tr><td>驱动强度 Card Type</td><td>{card_type}</td><td>支持下行频率</td></tr>
        </table>
        """

    perf_results = _extract_perf_results(results)
    perf_html = ""
    if perf_results and not is_batch:
        rows = ""
        for p in perf_results:
            rows += f"""
            <tr>
                <td>{p['name']}</td>
                <td class="{p['status']}">{p['status']}</td>
                <td>{p['bw_mbps'] or '-'}</td>
                <td>{p['iops'] or '-'}</td>
                <td>{p['max_iops'] or '-'}</td>
                <td>{p['lat_p999_us'] or '-'}</td>
                <td>{p['cpu_total'] or '-'}</td>
                <td>{p['emmc_util'] or '-'}</td>
            </tr>
            """
        perf_html = f"""
        <h2>4. 基础性能测试（FIO）</h2>
        <table>
            <tr>
                <th>测试项</th><th>状态</th><th>带宽(MB/s)</th><th>IOPS</th>
                <th>MAX IOPS</th><th>P99.9延迟(us)</th><th>CPU(%)</th><th>EMMC利用率(%)</th>
            </tr>
            {rows}
        </table>
        """

    stability_results = _extract_stability_results(results)
    stability_html = ""
    if stability_results and not is_batch:
        sections = ""
        for s in stability_results:
            img_html = f'<img src="{s["chart_base64"]}" style="max-width:100%; border:1px solid #ddd;">' if s['chart_base64'] else '<p>无图表</p>'
            sections += f"""
            <div class="stability-section">
                <h3>{s['name']}</h3>
                <table>
                    <tr><th>指标</th><th>数值</th></tr>
                    <tr><td>状态</td><td class="{s['status']}">{s['status']}</td></tr>
                    <tr><td>BW 均值(MB/s)</td><td>{s['bw_mean'] or '-'}</td></tr>
                    <tr><td>BW 变异系数 CV</td><td>{s['bw_cv'] or '-'}%</td></tr>
                    <tr><td>IOPS 均值</td><td>{s['iops_mean'] or '-'}</td></tr>
                    <tr><td>IOPS 变异系数 CV</td><td>{s['iops_cv'] or '-'}%</td></tr>
                    <tr><td>曲线采样点数</td><td>{s['curve_points']}</td></tr>
                </table>
                <p><strong>BW/IOPS 曲线图：</strong></p>
                {img_html}
                <p class="analysis">分析：整体读写速率与 IOPS 利用率浮动情况如上所示。</p>
            </div>
            """
        stability_html = f"""
        <h2>5. EMMC 稳定性测试</h2>
        <p class="note">测试背景：挂载底层稳定性跑速，高负载队列下输出图表，持续压测运行观察带宽、IOPS 数据下沉情况。</p>
        {sections}
        """

    reliability_html = ""
    if extcsd and not is_batch:
        reliability_html = f"""
        <h2>6. 可靠性寿命估算</h2>
        <ul>
            <li>Life Time Type A: <code>{extcsd.get('life_time_type_a', 'N/A')}</code></li>
            <li>Life Time Type B: <code>{extcsd.get('life_time_type_b', 'N/A')}</code></li>
            <li>PRE EOL Info: <code>{extcsd.get('pre_eol_info', 'N/A')}</code></li>
        </ul>
        <p class="note">请根据以上数据进行综合评估。</p>
        """

    # 标准测试卡：每个测试项的详情
    test_card_sections = ""
    for r in results:
        objective = r.get('objective') or '未配置'
        precondition = r.get('precondition') or '无特殊前置条件'
        steps = r.get('steps') or '未配置'
        expected = r.get('expected_result') or '未配置'
        actual = r.get('actual_result')
        if isinstance(actual, dict):
            actual_html = '<pre class="json-preview">' + json.dumps(actual, ensure_ascii=False, indent=2) + '</pre>'
        else:
            actual_html = f'<p>{actual or "-"}</p>'
        verdict = r.get('verdict_basis') or ''
        suggested_fix = r.get('suggested_fix')

        test_card_sections += f"""
        <div class="test-card">
            <h3>{r['module_name']} / {r['item_name']} <span class="status {r['status']}">{r['status']}</span></h3>
            <table>
                <tr><th style="width: 120px">字段</th><th>内容</th></tr>
                <tr><td>测试目的</td><td>{objective}</td></tr>
                <tr><td>前置条件</td><td>{precondition}</td></tr>
                <tr><td>测试步骤</td><td><pre class="steps">{steps}</pre></td></tr>
                <tr><td>预期结果</td><td>{expected}</td></tr>
                <tr><td>实际结果</td><td>{actual_html}</td></tr>
                <tr><td>判定依据</td><td>{verdict}</td></tr>
                {'<tr><td>修复建议</td><td class="fix">' + suggested_fix + '</td></tr>' if suggested_fix else ''}
                {'<tr><td>失败原因</td><td class="fail">' + (r.get('fail_reason') or '') + '</td></tr>' if r['status'] in ('fail', 'error', 'timeout') else ''}
            </table>
        </div>
        """

    # 结论与建议
    conclusion_items = []
    failed_items = [r for r in results if r['status'] in ('fail', 'error', 'timeout')]
    skipped_items = [r for r in results if r['status'] == 'skip']
    if not failed_items and not skipped_items:
        conclusion_items.append("所有测试项均通过，设备当前状态符合预期。")
    else:
        if failed_items:
            conclusion_items.append(f"存在 {len(failed_items)} 个失败/错误项，建议优先排查。")
        if skipped_items:
            conclusion_items.append(f"存在 {len(skipped_items)} 个跳过项，请确认设备兼容性与测试项配置。")
    for r in failed_items:
        fix = r.get('suggested_fix')
        conclusion_items.append(f"- {r['module_name']}/{r['item_name']}：{fix or r.get('fail_reason') or '请查看日志排查'}")

    conclusion_html = ""
    if not is_batch:
        conclusion_html = f"""
        <h2>7. 结论与建议</h2>
        <ul>
            {''.join(f'<li>{item}</li>' for item in conclusion_items)}
        </ul>
        """

    # 原始日志
    log_html = ""
    if not is_batch:
        log_sections = ""
        for r in results:
            if r.get('output_summary'):
                log_sections += f"""
                <div class="log-section">
                    <h4>{r['module_name']} / {r['item_name']}</h4>
                    <pre>{r['output_summary']}</pre>
                </div>
                """
        log_html = f"""
        <h2>8. 原始日志摘要</h2>
        {log_sections or '<p>无日志输出</p>'}
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>EMMC 性能测试与验证报告 {report_data['report_id']}</title>
    <style>
        body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 40px; color: #333; background: #f8f9fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: #fff; padding: 40px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a5276; border-bottom: 3px solid #3498db; padding-bottom: 15px; }}
        h2 {{ color: #2874a6; margin-top: 35px; border-left: 5px solid #3498db; padding-left: 12px; }}
        h3 {{ color: #2e86c1; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 14px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #eaf2f8; font-weight: bold; }}
        tr:nth-child(even) {{ background-color: #f8f9fa; }}
        .pass {{ color: #27ae60; font-weight: bold; }}
        .fail {{ color: #e74c3c; font-weight: bold; }}
        .skip {{ color: #7f8c8d; }}
        .error {{ color: #f39c12; font-weight: bold; }}
        .stability-section {{ margin: 25px 0; padding: 20px; background: #fafafa; border-radius: 8px; }}
        .stability-section img {{ max-width: 100%; height: auto; margin: 15px 0; }}
        .test-card {{ margin: 25px 0; padding: 20px; background: #fafafa; border-radius: 8px; }}
        .test-card h3 {{ margin-top: 0; }}
        .test-card .status {{ margin-left: 10px; font-size: 14px; padding: 2px 8px; border-radius: 4px; }}
        .test-card pre {{ background: #fff; border: 1px solid #ddd; padding: 10px; border-radius: 4px; white-space: pre-wrap; word-break: break-all; font-size: 13px; }}
        .test-card pre.steps {{ max-height: 200px; overflow-y: auto; }}
        .test-card .fix {{ color: #e67e22; }}
        .log-section {{ margin: 15px 0; }}
        .log-section pre {{ background: #f4f4f4; padding: 12px; border-radius: 4px; max-height: 300px; overflow-y: auto; font-size: 12px; white-space: pre-wrap; word-break: break-all; }}
        .note {{ color: #666; font-size: 13px; font-style: italic; }}
        .analysis {{ color: #555; font-size: 14px; margin-top: 10px; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>测试报告</h1>
    <p><strong>报告 ID：</strong>{report_data['report_id']}</p>

    {device_html}

    <h2>2. 汇总统计</h2>
    {summary_html}

    {extcsd_html}
    {perf_html}
    {stability_html}
    {reliability_html}

    <h2>7. 标准测试卡详情</h2>
    {test_card_sections}

    {conclusion_html}

    {log_html}
</div>
</body>
</html>
    """


def _export_report_data(report_data: dict, format: ExportFormat, filename_base: str):
    """根据格式导出报告数据。"""
    if format == ExportFormat.JSON:
        content = json.dumps(report_data, ensure_ascii=False, indent=2, default=str)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.json"}
        )

    elif format == ExportFormat.MARKDOWN:
        content = _generate_markdown(report_data)
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.md"}
        )

    elif format == ExportFormat.WORD:
        docx_bytes = _generate_word(report_data)
        return StreamingResponse(
            io.BytesIO(docx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.docx"}
        )

    elif format == ExportFormat.EXCEL:
        xlsx_bytes = _generate_excel(report_data)
        return StreamingResponse(
            io.BytesIO(xlsx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"}
        )

    elif format == ExportFormat.HTML:
        content = _generate_html(report_data)
        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.html"}
        )

    elif format == ExportFormat.PDF:
        raise HTTPException(status_code=501, detail="PDF 导出待后续实现")

    else:
        raise HTTPException(status_code=400, detail="不支持的导出格式")


@router.get("/stats/trend", response_model=ResponseModel)
async def get_stats_trend(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """最近 N 天任务趋势：按 completed_at（无则 created_at）日期聚合每天任务数、通过数、失败数。

    通过/失败口径与任务 result 一致：记录中有 fail/error/timeout 为失败，否则有 pass 为通过。
    非管理员仅统计自己的任务（与汇总报告一致）。
    """
    day_col = func.date(func.coalesce(TestTask.completed_at, TestTask.created_at))
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)

    query = select(TestTask.id, day_col.label("day")).where(day_col >= start.isoformat())
    if current_user.role != "admin":
        query = query.where(TestTask.user_id == current_user.id)
    task_rows = (await db.execute(query)).all()
    task_days = {row[0]: row[1] for row in task_rows}

    record_statuses = {}
    if task_days:
        rec_rows = (await db.execute(
            select(TestRecord.task_id, TestRecord.status)
            .where(TestRecord.task_id.in_(task_days.keys()))
        )).all()
        for task_id, rec_status in rec_rows:
            record_statuses.setdefault(task_id, []).append(rec_status)

    daily = {}
    for task_id, day in task_days.items():
        entry = daily.setdefault(day, {"total": 0, "passed": 0, "failed": 0})
        entry["total"] += 1
        statuses = record_statuses.get(task_id, [])
        if any(s in ("fail", "error", "timeout") for s in statuses):
            entry["failed"] += 1
        elif any(s == "pass" for s in statuses):
            entry["passed"] += 1

    series = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        entry = daily.get(day, {"total": 0, "passed": 0, "failed": 0})
        pass_rate = round(entry["passed"] / entry["total"] * 100, 1) if entry["total"] else 0.0
        series.append({
            "date": day,
            "total": entry["total"],
            "passed": entry["passed"],
            "failed": entry["failed"],
            "pass_rate": pass_rate,
        })

    return ResponseModel(code=200, data={"days": days, "series": series})


@router.get("/stats/by-module", response_model=ResponseModel)
async def get_stats_by_module(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """各测试模块通过率：按记录聚合，timeout 计入失败，error 单列但算未通过。

    通过率 = pass / (pass + fail + error + timeout)，不含 skip/pending/running。
    非管理员仅统计自己的任务记录。
    """
    query = (
        select(TestModule.name, TestRecord.status, func.count(TestRecord.id))
        .join(TestItem, TestRecord.item_id == TestItem.id)
        .join(TestModule, TestItem.module_id == TestModule.id)
    )
    if current_user.role != "admin":
        query = query.join(TestTask, TestRecord.task_id == TestTask.id).where(
            TestTask.user_id == current_user.id
        )
    query = query.group_by(TestModule.name, TestRecord.status)
    rows = (await db.execute(query)).all()

    modules = {}
    for module_name, rec_status, count in rows:
        entry = modules.setdefault(module_name, {"passed": 0, "failed": 0, "error": 0})
        if rec_status == "pass":
            entry["passed"] += count
        elif rec_status in ("fail", "timeout"):
            entry["failed"] += count
        elif rec_status == "error":
            entry["error"] += count

    items = []
    for module_name, entry in modules.items():
        total = entry["passed"] + entry["failed"] + entry["error"]
        items.append({
            "module_name": module_name,
            "total": total,
            "passed": entry["passed"],
            "failed": entry["failed"],
            "error": entry["error"],
            "pass_rate": round(entry["passed"] / total * 100, 1) if total else 0.0,
        })
    items.sort(key=lambda x: x["pass_rate"])

    return ResponseModel(code=200, data={"items": items})


@router.get("/{task_id}", response_model=ResponseModel)
async def get_report(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取单个任务测试报告（优先读已落盘的 JSON 文件，不存在才现算并顺手落盘）。"""
    file_path = os.path.join(_task_report_dir(task_id), "report.json")
    if os.path.exists(file_path):
        await _check_report_permission(db, task_id, current_user)
        content = await asyncio.to_thread(_read_report_file, file_path)
        return ResponseModel(code=200, data=json.loads(content))

    report_data = await _build_report(db, task_id, current_user)
    content = json.dumps(report_data, ensure_ascii=False, indent=2, default=str)
    await asyncio.to_thread(_write_report_file, file_path, content.encode("utf-8"))
    return ResponseModel(code=200, data=report_data)


@router.get("/summary/all", response_model=ResponseModel)
async def get_summary_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取当前用户所有任务的汇总总报告。"""
    query = select(TestTask).where(TestTask.user_id == current_user.id).order_by(TestTask.id.desc())
    if current_user.role == "admin":
        query = select(TestTask).order_by(TestTask.id.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()
    task_ids = [t.id for t in tasks]

    report_data = await _build_multi_task_report(db, task_ids, current_user)
    return ResponseModel(code=200, data=report_data)


@router.get("/batch/export")
async def export_batch_report(
    task_ids: str = Query(..., description="逗号分隔的任务ID，例如 1,2,3"),
    format: ExportFormat = ExportFormat.HTML,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """导出多个任务的聚合报告。"""
    try:
        ids = [int(x.strip()) for x in task_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="task_ids 格式错误，应为逗号分隔的整数")

    report_data = await _build_multi_task_report(db, ids, current_user)
    return _export_report_data(report_data, format, f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}")


@router.get("/{task_id}/export")
async def export_report(
    task_id: int,
    format: ExportFormat = ExportFormat.HTML,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """导出单个任务测试报告。

    优先返回已落盘的缓存文件；文件不存在才现算（重计算经 asyncio.to_thread
    放到 worker 线程，避免阻塞事件循环）并顺手落盘缓存。
    """
    ext = _EXPORT_EXTS.get(format)
    if ext is None:
        if format == ExportFormat.PDF:
            raise HTTPException(status_code=501, detail="PDF 导出待后续实现")
        raise HTTPException(status_code=400, detail="不支持的导出格式")

    file_path = os.path.join(_task_report_dir(task_id), f"report.{ext}")
    if not os.path.exists(file_path):
        report_data = await _build_report(db, task_id, current_user)
        content = await asyncio.to_thread(_render_report_content, report_data, format)
        await asyncio.to_thread(_write_report_file, file_path, content)
    else:
        await _check_report_permission(db, task_id, current_user)

    return FileResponse(
        file_path,
        media_type=_EXPORT_MEDIA_TYPES[format],
        filename=f"report_{task_id}.{ext}",
    )


@router.get("/{task_id}/items/{item_id}/log", response_model=ResponseModel)
async def get_item_log(
    task_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取测试项的详细日志"""
    result = await db.execute(
        select(TestRecord).where(
            TestRecord.task_id == task_id,
            TestRecord.item_id == item_id
        )
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    task_result = await db.execute(
        select(TestTask).where(TestTask.id == task_id)
    )
    task = task_result.scalar_one()

    if current_user.role != "admin" and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限查看")

    return ResponseModel(
        code=200,
        data={
            "item_id": record.item_id,
            "status": record.status,
            "output": record.output,
            "fail_reason": record.fail_reason,
            "extracted_data": record.extracted_data
        }
    )
