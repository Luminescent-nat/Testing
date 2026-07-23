from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime, timezone

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin
from app.models import User, FailurePattern, Baseline, GoldenCase
from app.schemas import (
    ResponseModel,
    FailurePatternCreate,
    FailurePatternUpdate,
    BaselineCreate,
    BaselineUpdate,
    GoldenCaseCreate,
    GoldenCaseUpdate,
)
from app.services.memory_engine import BaselineService

router = APIRouter(prefix="/memory", tags=["记忆体"])


# ========== 失败模式库 ==========

@router.get("/failure-patterns", response_model=ResponseModel)
async def list_failure_patterns(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询失败模式库。"""
    query = select(FailurePattern)
    if category:
        query = query.where(FailurePattern.category == category)

    result = await db.execute(query.order_by(FailurePattern.occurrence_count.desc()))
    patterns = result.scalars().all()

    return ResponseModel(
        code=200,
        data=[
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "pattern": p.pattern,
                "description": p.description,
                "suggested_fix": p.suggested_fix,
                "occurrence_count": p.occurrence_count
            }
            for p in patterns
        ]
    )


@router.post("/failure-patterns", response_model=ResponseModel)
async def create_failure_pattern(
    data: FailurePatternCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建失败模式（管理员）。"""
    pattern = FailurePattern(
        name=data.name,
        category=data.category,
        pattern=data.pattern,
        description=data.description,
        suggested_fix=data.suggested_fix,
        created_by=current_user.id
    )
    db.add(pattern)
    await db.commit()
    await db.refresh(pattern)
    return ResponseModel(code=200, message="创建成功", data={
        "id": pattern.id,
        "name": pattern.name,
        "category": pattern.category,
        "pattern": pattern.pattern,
        "description": pattern.description,
        "suggested_fix": pattern.suggested_fix,
        "occurrence_count": pattern.occurrence_count
    })


@router.put("/failure-patterns/{pattern_id}", response_model=ResponseModel)
async def update_failure_pattern(
    pattern_id: int,
    data: FailurePatternUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新失败模式（管理员）。"""
    result = await db.execute(select(FailurePattern).where(FailurePattern.id == pattern_id))
    pattern = result.scalar_one_or_none()
    if not pattern:
        raise HTTPException(status_code=404, detail="失败模式不存在")

    for field in ["name", "category", "pattern", "description", "suggested_fix"]:
        value = getattr(data, field)
        if value is not None:
            setattr(pattern, field, value)

    pattern.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(pattern)
    return ResponseModel(code=200, message="更新成功", data={
        "id": pattern.id,
        "name": pattern.name,
        "category": pattern.category,
        "pattern": pattern.pattern,
        "description": pattern.description,
        "suggested_fix": pattern.suggested_fix,
        "occurrence_count": pattern.occurrence_count
    })


@router.delete("/failure-patterns/{pattern_id}", response_model=ResponseModel)
async def delete_failure_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除失败模式（管理员）。"""
    result = await db.execute(select(FailurePattern).where(FailurePattern.id == pattern_id))
    pattern = result.scalar_one_or_none()
    if not pattern:
        raise HTTPException(status_code=404, detail="失败模式不存在")

    await db.delete(pattern)
    await db.commit()
    return ResponseModel(code=200, message="删除成功")


# ========== 统计基线 ==========

@router.get("/baselines", response_model=ResponseModel)
async def list_baselines(
    device_model: Optional[str] = None,
    item_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询统计基线。"""
    baselines = await BaselineService.get_baselines(db, device_model, item_id)

    return ResponseModel(
        code=200,
        data=[
            {
                "id": b.id,
                "device_model": b.device_model,
                "item_id": b.item_id,
                "metric_name": b.metric_name,
                "avg_value": b.avg_value,
                "min_value": b.min_value,
                "max_value": b.max_value,
                "sample_count": b.sample_count,
                "updated_at": b.updated_at.isoformat() if b.updated_at else None
            }
            for b in baselines
        ]
    )


@router.post("/baselines", response_model=ResponseModel)
async def create_baseline(
    data: BaselineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """手动创建统计基线（管理员）。"""
    baseline = Baseline(
        device_model=data.device_model,
        item_id=data.item_id,
        metric_name=data.metric_name,
        avg_value=data.avg_value,
        min_value=data.min_value,
        max_value=data.max_value,
        sample_count=data.sample_count
    )
    db.add(baseline)
    await db.commit()
    await db.refresh(baseline)
    return ResponseModel(code=200, message="创建成功", data={
        "id": baseline.id,
        "device_model": baseline.device_model,
        "item_id": baseline.item_id,
        "metric_name": baseline.metric_name,
        "avg_value": baseline.avg_value,
        "min_value": baseline.min_value,
        "max_value": baseline.max_value,
        "sample_count": baseline.sample_count,
        "updated_at": baseline.updated_at.isoformat() if baseline.updated_at else None
    })


@router.put("/baselines/{baseline_id}", response_model=ResponseModel)
async def update_baseline(
    baseline_id: int,
    data: BaselineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新统计基线（管理员）。"""
    result = await db.execute(select(Baseline).where(Baseline.id == baseline_id))
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="基线不存在")

    for field in ["device_model", "item_id", "metric_name", "avg_value", "min_value", "max_value", "sample_count"]:
        value = getattr(data, field)
        if value is not None:
            setattr(baseline, field, value)

    baseline.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(baseline)
    return ResponseModel(code=200, message="更新成功", data={
        "id": baseline.id,
        "device_model": baseline.device_model,
        "item_id": baseline.item_id,
        "metric_name": baseline.metric_name,
        "avg_value": baseline.avg_value,
        "min_value": baseline.min_value,
        "max_value": baseline.max_value,
        "sample_count": baseline.sample_count,
        "updated_at": baseline.updated_at.isoformat() if baseline.updated_at else None
    })


@router.delete("/baselines/{baseline_id}", response_model=ResponseModel)
async def delete_baseline(
    baseline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除统计基线（管理员）。"""
    result = await db.execute(select(Baseline).where(Baseline.id == baseline_id))
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="基线不存在")

    await db.delete(baseline)
    await db.commit()
    return ResponseModel(code=200, message="删除成功")


# ========== 黄金案例库 ==========

@router.get("/golden-cases", response_model=ResponseModel)
async def list_golden_cases(
    device_model: Optional[str] = None,
    item_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询黄金案例库。"""
    query = select(GoldenCase)
    if device_model:
        query = query.where(GoldenCase.device_model == device_model)
    if item_id:
        query = query.where(GoldenCase.item_id == item_id)

    result = await db.execute(query)
    cases = result.scalars().all()

    return ResponseModel(
        code=200,
        data=[
            {
                "id": c.id,
                "item_id": c.item_id,
                "device_model": c.device_model,
                "expected_status": c.expected_status,
                "expected_output_pattern": c.expected_output_pattern,
                "sample_output": c.sample_output,
                "pass_count": c.pass_count,
                "total_count": c.total_count,
                "is_active": c.is_active
            }
            for c in cases
        ]
    )


@router.post("/golden-cases", response_model=ResponseModel)
async def create_golden_case(
    data: GoldenCaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建黄金案例（管理员）。"""
    case = GoldenCase(
        item_id=data.item_id,
        device_model=data.device_model,
        expected_status=data.expected_status,
        expected_output_pattern=data.expected_output_pattern,
        sample_output=data.sample_output,
        pass_count=1,
        total_count=1,
        is_active=data.is_active
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return ResponseModel(code=200, message="创建成功", data={
        "id": case.id,
        "item_id": case.item_id,
        "device_model": case.device_model,
        "expected_status": case.expected_status,
        "expected_output_pattern": case.expected_output_pattern,
        "sample_output": case.sample_output,
        "pass_count": case.pass_count,
        "total_count": case.total_count,
        "is_active": case.is_active
    })


@router.put("/golden-cases/{case_id}", response_model=ResponseModel)
async def update_golden_case(
    case_id: int,
    data: GoldenCaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新黄金案例（管理员）。"""
    result = await db.execute(select(GoldenCase).where(GoldenCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="黄金案例不存在")

    for field in ["item_id", "device_model", "expected_status", "expected_output_pattern", "sample_output", "is_active"]:
        value = getattr(data, field)
        if value is not None:
            setattr(case, field, value)

    case.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(case)
    return ResponseModel(code=200, message="更新成功", data={
        "id": case.id,
        "item_id": case.item_id,
        "device_model": case.device_model,
        "expected_status": case.expected_status,
        "expected_output_pattern": case.expected_output_pattern,
        "sample_output": case.sample_output,
        "pass_count": case.pass_count,
        "total_count": case.total_count,
        "is_active": case.is_active
    })


@router.delete("/golden-cases/{case_id}", response_model=ResponseModel)
async def delete_golden_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除黄金案例（管理员）。"""
    result = await db.execute(select(GoldenCase).where(GoldenCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="黄金案例不存在")

    await db.delete(case)
    await db.commit()
    return ResponseModel(code=200, message="删除成功")
