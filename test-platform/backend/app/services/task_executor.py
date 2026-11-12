import asyncio
import logging
import os
from typing import Dict, Optional
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import TestTask, TestRecord, TestItem, Device
from app.services import device as device_module
from app.services.execution_engine import EngineFactory
from app.services.memory_engine import FailurePatternService, BaselineService, GoldenCaseService
from app.services.knowledge_feedback import KnowledgeFeedbackService
from app.api.reports import generate_task_report_files
from app.websocket import notify_progress, push_log

logger = logging.getLogger(__name__)

# record.output 落库最大长度：超出时仅保留末尾并标注截断，完整内容在日志文件中
OUTPUT_MAX_LENGTH = 64 * 1024


def _truncate_output(output: Optional[str]) -> Optional[str]:
    """截断超长输出（保留尾部），完整内容见 record.log_file_path 对应的日志文件。"""
    if output and len(output) > OUTPUT_MAX_LENGTH:
        marker = f"[输出超过 {OUTPUT_MAX_LENGTH} 字符，已截断仅保留末尾部分，完整内容见日志文件]"
        return marker + "\n" + output[-OUTPUT_MAX_LENGTH:]
    return output


class DeviceLock:
    """设备锁：每个设备一把 asyncio.Lock，竞争同一设备的任务按 FIFO 排队等待。

    - acquire 在设备被占用时异步阻塞等待（等待期间任务保持 pending），
      等待可被 TaskExecutor.cancel_task 取消（CancelledError 打断 acquire）；
    - release 幂等且不校验持有者，持有者一致性由 _release_device 把关，
      排队中被取消的任务不会误放其他任务持有的锁。
    """

    _locks: Dict[str, asyncio.Lock] = {}
    _holders: Dict[str, int] = {}

    @classmethod
    async def acquire(cls, serial: str, task_id: int):
        """获取设备锁，设备被占用时按 FIFO 排队等待（不设超时，可被取消）。"""
        lock = cls._locks.setdefault(serial, asyncio.Lock())
        await lock.acquire()
        cls._holders[serial] = task_id

    @classmethod
    def release(cls, serial: str):
        """释放设备锁（幂等，未持锁时为 no-op）。"""
        cls._holders.pop(serial, None)
        lock = cls._locks.get(serial)
        if lock is not None and lock.locked():
            lock.release()

    @classmethod
    def get_holder(cls, serial: str) -> Optional[int]:
        """获取当前占用设备的任务ID，排队等待中的任务不算持有者。"""
        return cls._holders.get(serial)


class TaskExecutor:
    """任务执行器，负责在后台异步执行测试任务。"""

    _running_tasks: Dict[int, asyncio.Task] = {}

    @classmethod
    def start_task(cls, task_id: int) -> bool:
        """启动一个后台任务。"""
        if task_id in cls._running_tasks:
            logger.warning("任务 %s 已在运行中", task_id)
            return False

        task = asyncio.create_task(cls._run_task(task_id), name=f"task-{task_id}")
        cls._running_tasks[task_id] = task

        # 任务结束后自动清理
        def _on_done(t: asyncio.Task):
            cls._cleanup(task_id)
            try:
                t.result()
            except asyncio.CancelledError:
                logger.info("任务 %s 已取消", task_id)
            except Exception as exc:
                logger.exception("任务 %s 执行异常: %s", task_id, exc)

        task.add_done_callback(_on_done)
        return True

    @classmethod
    def cancel_task(cls, task_id: int) -> bool:
        """取消正在运行的任务。"""
        running = cls._running_tasks.get(task_id)
        if running and not running.done():
            running.cancel()
            return True
        return False

    @classmethod
    def _cleanup(cls, task_id: int):
        """清理已结束的任务引用。"""
        cls._running_tasks.pop(task_id, None)

    @classmethod
    async def _run_task(cls, task_id: int):
        """任务主执行逻辑。"""
        async with AsyncSessionLocal() as db:
            try:
                await cls._execute_with_db(task_id, db)
            except asyncio.CancelledError:
                await cls._handle_cancel(task_id, db)
                raise
            except Exception as exc:
                logger.exception("任务 %s 执行失败: %s", task_id, exc)
                await cls._handle_failure(task_id, db, str(exc))

    @classmethod
    async def _execute_with_db(cls, task_id: int, db: AsyncSession):
        """在数据库会话中执行任务。"""
        # 加载任务，同时预加载设备信息
        result = await db.execute(
            select(TestTask)
            .options(joinedload(TestTask.device))
            .where(TestTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            logger.error("任务 %s 不存在", task_id)
            return

        # 加载设备
        result = await db.execute(select(Device).where(Device.id == task.device_id))
        device = result.scalar_one_or_none()
        if not device:
            task.status = "failed"
            task.error_message = "设备不存在"
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return

        # 获取设备锁：设备被占用时按 FIFO 排队等待，等待期间任务保持 pending；
        # 排队中取消任务时 acquire 抛 CancelledError，由 _handle_cancel 收尾，
        # 不会误放其他任务持有的锁
        await DeviceLock.acquire(device.serial_number, task_id)

        try:
            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            task.progress_percent = 0
            # 排队期间设备可能已被上一任务释放回 online，拿到锁后重新标记 testing
            device.status = "testing"
            await db.commit()
            await notify_progress(task_id)

            total = len(task.selected_items)
            for idx, item_id in enumerate(task.selected_items):
                # 每个测试项开始前做一次轻量探活（短超时，只在项间一次，不显著拖慢
                # 正常流程）：设备离线时当前项及剩余项直接标记 error 并终止任务，
                # 避免离线设备上每条 adb 命令都等到超时（默认 300s）才逐个失败。
                # 取舍：单次探活失败（含 adb 自身异常）即判离线，宁可快速失败也不
                # 引入连续失败计数；设备离线属于环境故障，不进入重试循环。
                if not await cls._probe_device_online(device.serial_number):
                    await cls._fail_remaining_items(task, device, idx, db)
                    return

                # 创建测试记录
                record = TestRecord(
                    task_id=task_id,
                    item_id=item_id,
                    status="running",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(record)
                await db.commit()
                await db.refresh(record)

                # 加载测试项
                result = await db.execute(select(TestItem).where(TestItem.id == item_id))
                item = result.scalar_one_or_none()

                if not item:
                    record.status = "skip"
                    record.fail_reason = "测试项不存在"
                    record.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                elif not item.enabled:
                    record.status = "skip"
                    record.fail_reason = "测试项已禁用"
                    record.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                else:
                    await cls._execute_item(task, device, item, record, db)

                # 更新任务进度
                task.progress_percent = int((idx + 1) / total * 100) if total > 0 else 100
                await db.commit()
                await notify_progress(task_id)

                # 检查是否因失败停止
                if record.status in ("fail", "error", "timeout") and item and item.on_failure == "stop":
                    logger.info("任务 %s 在测试项 %s 处失败停止", task_id, item_id)
                    break

            # 任务收尾
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            task.progress_percent = 100
            await db.commit()
            await notify_progress(task_id)

            # 记忆体沉淀：失败模式归类、基线更新、黄金案例积累
            await cls._update_memory(db, task, device)

            # 后台生成报告文件（JSON+HTML）落盘，失败不影响任务收尾
            cls._schedule_report_generation(task_id)

        finally:
            await cls._release_device(db, device, task_id)

    @classmethod
    def _schedule_report_generation(cls, task_id: int):
        """后台异步生成任务报告文件落盘；调度本身失败只记日志，不影响任务收尾。"""
        try:
            asyncio.create_task(
                generate_task_report_files(task_id), name=f"report-{task_id}"
            )
        except Exception as exc:
            logger.warning("任务 %s 报告生成调度失败: %s", task_id, exc)

    @classmethod
    async def _probe_device_online(cls, serial: str) -> bool:
        """项间轻量探活（短超时 8s）。

        探活异常（如 adb 不可用）按离线处理：单次失败即判离线，
        宁可快速失败也不让任务在离线设备上空等超时。
        """
        try:
            # 通过模块属性访问，保证测试中 monkeypatch ADBService 后生效
            return await device_module.ADBService().is_device_online(serial, timeout=8)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("设备 %s 项间探活异常，按离线处理: %s", serial, exc)
            return False

    @classmethod
    async def _fail_remaining_items(cls, task: TestTask, device: Device, start_idx: int, db: AsyncSession):
        """设备离线快速失败：当前项及剩余所有项标记 error，任务按失败收尾。

        设备状态不在此处理：finally 中的 _release_device 会再次探活，
        探活失败则保持 offline。
        """
        now = datetime.now(timezone.utc)
        reason = f"设备 {device.serial_number} 离线，测试项未执行"
        for item_id in task.selected_items[start_idx:]:
            db.add(TestRecord(
                task_id=task.id,
                item_id=item_id,
                status="error",
                fail_reason=reason,
                started_at=now,
                completed_at=now,
            ))
        task.status = "failed"
        task.error_message = f"设备 {device.serial_number} 离线，任务终止"
        task.completed_at = now
        task.progress_percent = 100
        await db.commit()
        await notify_progress(task.id)
        logger.warning("任务 %s 因设备 %s 离线终止", task.id, device.serial_number)
        # 失败收尾同样后台生成报告落盘
        cls._schedule_report_generation(task.id)

    @classmethod
    async def _release_device(cls, db: AsyncSession, device: Device, task_id: Optional[int] = None):
        """释放设备锁并恢复设备状态。

        task_id 与当前锁持有者不一致时（任务在排队中被取消、设备被其他任务持有），
        不释放锁也不改设备状态，避免误放他人的锁或把执行中设备置回 online。

        释放前做一次轻量 adb 探活：探活失败说明设备已离线，置为 offline，
        避免任务结束/取消时把离线设备误置 online；探活本身异常时沿用旧行为
        置 online（不因为探活故障而误判设备离线）。
        """
        holder = DeviceLock.get_holder(device.serial_number)
        if task_id is not None and holder is not None and holder != task_id:
            logger.info("设备 %s 被任务 %s 持有，任务 %s 不执行释放", device.serial_number, holder, task_id)
            return
        DeviceLock.release(device.serial_number)
        online = True
        try:
            # 通过模块属性访问，保证测试中 monkeypatch ADBService 后生效
            online = await device_module.ADBService().is_device_online(device.serial_number)
        except Exception as exc:
            logger.warning("设备 %s 探活异常，默认置 online: %s", device.serial_number, exc)
        device.status = "online" if online else "offline"
        device.last_seen_at = datetime.now(timezone.utc)
        await db.commit()

    @classmethod
    async def _execute_item(
        cls,
        task: TestTask,
        device: Device,
        item: TestItem,
        record: TestRecord,
        db: AsyncSession
    ):
        """执行单个测试项。"""
        # 准备自定义参数：优先使用任务级别为该测试项配置的参数
        custom_params = task.custom_parameters or {}
        item_custom_params = custom_params.get(str(item.id), {}) if isinstance(custom_params, dict) else {}

        # 兼容性检查
        engine = EngineFactory.get_engine(item.exec_type)
        valid, reason = await engine.validate(device, item)
        if not valid:
            record.status = "skip"
            record.fail_reason = reason
            record.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return

        # 执行测试：失败（fail/error/timeout）时按 retry_count 自动重试，
        # 每次尝试的输出都保留，最终状态以最后一次执行为准，不产生新的 TestRecord
        max_retries = item.retry_count or 0
        outputs = []
        attempt = 0

        # 实时日志：执行过程中的输出行逐行落盘到日志文件，并通过 WebSocket 推送到
        # 监控页；日志文件路径相对 settings.LOGS_PATH 存储到 record.log_file_path
        record.log_file_path = f"task_{task.id}/record_{record.id}.log"
        log_abs_path = os.path.join(get_settings().LOGS_PATH, record.log_file_path)
        os.makedirs(os.path.dirname(log_abs_path), exist_ok=True)
        log_file = open(log_abs_path, "a", encoding="utf-8")
        streamed_lines = 0

        async def on_output(line: str):
            nonlocal streamed_lines
            log_file.write(line)
            streamed_lines += 1
            if streamed_lines % 50 == 0:
                log_file.flush()
            await push_log(task.id, record.id, line)

        try:
            while True:
                if attempt > 0:
                    logger.info("测试项 %s 第 %s/%s 次重试", item.id, attempt, max_retries)
                    retry_marker = f"=== 重试 {attempt}/{max_retries} ==="
                    outputs.append(retry_marker)
                    await on_output(retry_marker + "\n")
                try:
                    lines_before = streamed_lines
                    exec_result = await engine.execute(device, item, item_custom_params, on_output=on_output)
                    # T-06 后执行引擎只产出 pass/fail/skip/error/timeout；保留防御性映射，
                    # 任何越界状态一律落 error（失败关闭，绝不落 unknown）。
                    record.status = exec_result.status if exec_result.status in ("pass", "fail", "skip", "error", "timeout") else "error"
                    record.fail_reason = exec_result.fail_reason
                    record.execution_time = (record.execution_time or 0) + exec_result.execution_time
                    record.extracted_data = exec_result.extracted_data
                    if exec_result.output:
                        outputs.append(exec_result.output)
                        # 引擎本次未产生任何流式回调时（如 adb 层被 mock），
                        # 补写完整输出，保证日志文件内容完整
                        if streamed_lines == lines_before:
                            await on_output(exec_result.output + "\n")
                except asyncio.CancelledError:
                    # 被取消时不重试，直接向上传播
                    record.status = "error"
                    record.fail_reason = "任务被取消"
                    record.output = _truncate_output("\n\n".join(outputs) or None)
                    raise
                except Exception as exc:
                    logger.exception("测试项 %s 执行异常: %s", item.id, exc)
                    record.status = "error"
                    record.fail_reason = f"执行异常: {exc}"

                attempt += 1
                if record.status not in ("fail", "error", "timeout") or attempt > max_retries:
                    break
        finally:
            log_file.close()

        record.output = _truncate_output("\n\n".join(outputs) or None)
        record.completed_at = datetime.now(timezone.utc)
        await db.commit()

    @classmethod
    async def _update_memory(cls, db: AsyncSession, task: TestTask, device: Device):
        """任务完成后沉淀失败模式、统计基线、黄金案例和知识库反馈。"""
        # 重新加载 records（避免会话过期）
        result = await db.execute(
            select(TestRecord).where(TestRecord.task_id == task.id)
        )
        records = result.scalars().all()

        for record in records:
            try:
                await FailurePatternService.match_record(db, record)
            except Exception as exc:
                logger.warning("失败模式匹配异常: %s", exc)

            try:
                await BaselineService.update_from_record(db, record, device.model or "unknown")
            except Exception as exc:
                logger.warning("基线更新异常: %s", exc)

            try:
                await GoldenCaseService.update_from_record(db, record, device.model or "unknown")
            except Exception as exc:
                logger.warning("黄金案例更新异常: %s", exc)

            try:
                # 加载测试项用于知识库匹配
                result = await db.execute(select(TestItem).where(TestItem.id == record.item_id))
                item = result.scalar_one_or_none()
                await KnowledgeFeedbackService.update_from_record(db, record, item)
            except Exception as exc:
                logger.warning("知识库反馈更新异常: %s", exc)

    @classmethod
    async def _handle_cancel(cls, task_id: int, db: AsyncSession):
        """处理任务取消。"""
        result = await db.execute(
            select(TestTask)
            .options(joinedload(TestTask.device))
            .where(TestTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            logger.warning("取消的任务 %s 不存在，跳过状态收尾", task_id)
            return

        # 任务最终状态保持 cancelled，不允许被覆盖回 completed
        task.status = "cancelled"
        task.completed_at = datetime.now(timezone.utc)

        # 收尾仍处于 running/pending 的测试记录（取消可能发生在记录刚创建后）
        rec_result = await db.execute(
            select(TestRecord).where(
                TestRecord.task_id == task_id,
                TestRecord.status.in_(["running", "pending"]),
            )
        )
        for record in rec_result.scalars().all():
            record.status = "error"
            record.fail_reason = "任务被取消"
            record.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await notify_progress(task_id)

        # 释放设备（排队中被取消时不持锁，_release_device 内部会校验持有者）
        result = await db.execute(select(Device).where(Device.id == task.device_id))
        device = result.scalar_one_or_none()
        if device:
            await cls._release_device(db, device, task_id)

    @classmethod
    async def _handle_failure(cls, task_id: int, db: AsyncSession, error_message: str):
        """处理任务执行失败。"""
        result = await db.execute(
            select(TestTask)
            .options(joinedload(TestTask.device))
            .where(TestTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            logger.warning("失败的任务 %s 不存在，跳过状态收尾", task_id)
            return

        task.status = "failed"
        task.error_message = error_message
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await notify_progress(task_id)
        # 失败收尾同样后台生成报告落盘
        cls._schedule_report_generation(task_id)

        result = await db.execute(select(Device).where(Device.id == task.device_id))
        device = result.scalar_one_or_none()
        if device:
            await cls._release_device(db, device, task_id)
