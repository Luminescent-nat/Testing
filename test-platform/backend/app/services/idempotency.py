"""写操作幂等服务（V1-04 / 契约 docs/contracts/README.md 第 3 节）。

职责：
- 校验 Idempotency-Key：8～128 个可打印 ASCII 字符；
- 规范化请求体并计算 sha256（同键不同请求体必须可判 409）；
- 以 (user_id, operation, idempotency_key) 为唯一业务键读写 idempotency_records；
- 数据库 UNIQUE 约束兜底并发重复：先占键后执行，抢占失败方读取首次
  响应重放，保证「并发 N 次至多一次真实执行」。

服务只接收调用方传入的 AsyncSession（不做模块级会话绑定），因此测试环境
替换 app.database.AsyncSessionLocal 的隔离机制对本服务天然生效。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Awaitable, Callable, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyRecord

# Idempotency-Key 合法范围（契约第 3 节：8～128 可打印 ASCII）
KEY_MIN_LENGTH = 8
KEY_MAX_LENGTH = 128
OPERATION_TASK_CREATE = "task_create"
OPERATION_TASK_RERUN = "task_rerun"

# 并发抢占失败后等待首次执行方写回响应的最长时间与轮询间隔
RESPONSE_WAIT_TIMEOUT_SECONDS = 30.0
RESPONSE_WAIT_INTERVAL_SECONDS = 0.05


class IdempotencyKeyError(ValueError):
    """Idempotency-Key 缺失或格式不合法（映射 400 VALIDATION_ERROR）。"""


class IdempotencyConflictError(Exception):
    """同键不同请求体（映射 409 CONFLICT）。"""


def validate_idempotency_key(key: Any) -> str:
    """校验并原样返回 Idempotency-Key；不合法抛 IdempotencyKeyError。"""
    if not isinstance(key, str) or not key:
        raise IdempotencyKeyError("Idempotency-Key 不能为空")
    if not (KEY_MIN_LENGTH <= len(key) <= KEY_MAX_LENGTH):
        raise IdempotencyKeyError(
            f"Idempotency-Key 长度必须在 {KEY_MIN_LENGTH}～{KEY_MAX_LENGTH} 之间"
        )
    for ch in key:
        if not (0x20 <= ord(ch) <= 0x7E):
            raise IdempotencyKeyError("Idempotency-Key 只能包含可打印 ASCII 字符")
    return key


def canonical_request_sha256(payload: Any) -> str:
    """对请求体做规范化 JSON 序列化后计算 sha256。

    规范化规则：JSON 序列化（sort_keys、紧凑分隔符、ensure_ascii=False）。
    只对「语义内容」生效——键顺序不同但内容相同的请求视为同一请求。
    """
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def find_record(
    db: AsyncSession, *, user_id: int, operation: str, idempotency_key: str
) -> Optional[IdempotencyRecord]:
    """按唯一业务键查找已有幂等记录（不提交任何变更）。"""
    result = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def check_replay_or_conflict(
    db: AsyncSession,
    *,
    user_id: int,
    operation: str,
    idempotency_key: str,
    request_sha256: str,
) -> Optional[IdempotencyRecord]:
    """请求开始前的重放/冲突判定。

    返回：
    - None：无记录，调用方可继续真实执行；
    - 记录对象：
        * record.request_sha256 != request_sha256 → 同键不同请求体，
          抛 IdempotencyConflictError（调用方映射 409）；
        * 否则 → 同键同请求体重放，返回记录（response_json 可能仍为 None，
          表示首次请求正在执行中，调用方可调用 wait_for_response）。
    """
    record = await find_record(db, user_id=user_id, operation=operation, idempotency_key=idempotency_key)
    if record is None:
        return None
    if record.request_sha256 != request_sha256:
        raise IdempotencyConflictError(
            "Idempotency-Key 已被不同的请求体使用"
        )
    return record


async def claim_key(
    db: AsyncSession,
    *,
    user_id: int,
    operation: str,
    idempotency_key: str,
    request_sha256: str,
    task_id: Optional[int] = None,
) -> Tuple[IdempotencyRecord, bool]:
    """占用幂等键（先写记录，后执行业务）。

    返回 (record, won)：
    - won=True：本请求成功占用该键，可以执行真实业务；
    - won=False：并发竞争失败（数据库 UNIQUE 兜底），record 为已存在的
      首次记录；若其 request_sha256 不同则抛 IdempotencyConflictError。
    """
    existing = await find_record(db, user_id=user_id, operation=operation, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.request_sha256 != request_sha256:
            raise IdempotencyConflictError("Idempotency-Key 已被不同的请求体使用")
        return existing, False

    record = IdempotencyRecord(
        user_id=user_id,
        operation=operation,
        idempotency_key=idempotency_key,
        request_sha256=request_sha256,
        response_json=None,
        task_id=task_id,
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        # 并发窗口：另一请求先插入了同一 (user_id, operation, key)。
        await db.rollback()
        existing = await find_record(db, user_id=user_id, operation=operation, idempotency_key=idempotency_key)
        if existing is None:
            raise
        if existing.request_sha256 != request_sha256:
            raise IdempotencyConflictError("Idempotency-Key 已被不同的请求体使用")
        return existing, False
    await db.refresh(record)
    return record, True


async def complete_with_response(
    db: AsyncSession,
    record: IdempotencyRecord,
    *,
    response_payload: Any,
    task_id: Optional[int] = None,
) -> None:
    """首次执行完成后写回响应（重放方读取的就是这里保存的内容）。"""
    record.response_json = response_payload
    if task_id is not None:
        record.task_id = task_id
    await db.commit()


async def wait_for_response(
    db: AsyncSession,
    record: IdempotencyRecord,
    *,
    timeout: float = RESPONSE_WAIT_TIMEOUT_SECONDS,
    interval: float = RESPONSE_WAIT_INTERVAL_SECONDS,
) -> Optional[IdempotencyRecord]:
    """并发失败方等待首次执行方写回 response_json。

    超时仍无响应、或记录在等待期间被删除（首次执行失败会释放占键记录）
    时返回 None，调用方可重新尝试占用键，不伪造首次响应。
    """
    deadline = time.monotonic() + timeout
    current = record
    while current.response_json is None:
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(interval)
        try:
            await db.refresh(current)
        except Exception:
            # 记录已被删除（首次执行失败释放占键），调用方需重新抢占
            return None
    return current


async def run_idempotent(
    db: AsyncSession,
    *,
    user_id: int,
    operation: str,
    idempotency_key: str,
    request_payload: Any,
    execute: Callable[[], Awaitable[Any]],
    task_id_extractor: Optional[Callable[[Any], Optional[int]]] = None,
) -> Tuple[Any, IdempotencyRecord]:
    """幂等执行编排：同键同请求体只真实执行一次，其余全部重放。

    - execute()：真实业务（创建任务/重跑），返回可 JSON 序列化的响应负载；
    - 重放路径不调用 execute()；
    - 并发抢占失败：等待首次执行方写回响应后重放；首次执行失败时占键
      记录被释放，失败方重新抢占并自行执行。

    返回 (response_payload, record)。任何 execute() 抛出的异常原样向上
    传播（占键记录已删除，同键同体重试可再次执行，同键不同体仍 409）。
    """
    request_sha256 = canonical_request_sha256(request_payload)

    while True:
        # 快路径：记录已存在（重放或冲突）
        existing = await check_replay_or_conflict(
            db,
            user_id=user_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
        )
        if existing is not None:
            if existing.response_json is None:
                existing = await wait_for_response(db, existing)
                if existing is None:
                    continue  # 首次执行失败已释放占键，重新抢占
            return existing.response_json, existing

        record, won = await claim_key(
            db,
            user_id=user_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
        )
        if not won:
            waited = await wait_for_response(db, record)
            if waited is None:
                continue  # 首次执行失败已释放占键，重新抢占
            return waited.response_json, waited

        try:
            response_payload = await execute()
        except Exception:
            # 真实执行失败：释放占键记录，允许同键同体重试再次执行
            await db.delete(record)
            await db.commit()
            raise
        task_id = task_id_extractor(response_payload) if task_id_extractor else None
        await complete_with_response(db, record, response_payload=response_payload, task_id=task_id)
        return response_payload, record
