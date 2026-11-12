from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Any, Dict, Optional

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin
from app.errors import build_error_body
from app.models import User, Device
from app.schemas import (
    DeviceResponse, DeviceUpdate, DeviceList, ResponseModel,
    DeviceStatus
)
from app.services.device import DeviceService, ADBDiscoveryError
from app.services.authorization import ensure_device_access, filter_visible_devices
from app.services.knowledge_matcher import get_device_knowledge

router = APIRouter(prefix="/devices", tags=["设备管理"])
# 顶级路由（无 prefix）：POST /api/v1/device-discoveries（契约 §5）
discovery_router = APIRouter(tags=["设备发现"])
device_service = DeviceService()

DEVICE_FORBIDDEN_MESSAGE = "无权限访问此设备"
ADB_DISCOVERY_FAILED_MESSAGE = "ADB发现失败"


class DeviceAssignmentRequest(BaseModel):
    """PATCH /devices/{serial} 改派请求体（契约 §6；未知字段 400）。

    owner_id 必填（可显式 null 取消分配）：缺字段 → 422 → 400 VALIDATION_ERROR
    details.field=owner_id，不允许可省略后默认取消分配。
    """

    model_config = ConfigDict(extra="forbid")

    owner_id: Optional[int]                  # 必填；显式 null 表示取消分配
    pc_identifier: str = Field(..., min_length=1, max_length=255)
    version: int = Field(..., ge=1)


def _device_payload(device: Device) -> dict:
    """序列化设备并附带 version（schemas.DeviceResponse 由 task-16 后续补 version 字段）。"""
    payload = DeviceResponse.model_validate(device).model_dump()
    payload["version"] = device.version
    return payload


def _discovery_response(devices) -> ResponseModel:
    items = [DeviceResponse.model_validate(d) for d in devices]
    return ResponseModel(
        code=201,
        message="设备发现完成",
        data={"items": items, "total": len(items), "owner_unchanged": True},
    )


def _adb_failure_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=build_error_body(
            "SERVICE_UNAVAILABLE",
            ADB_DISCOVERY_FAILED_MESSAGE,
            {"reason": "ADB调用未成功，设备状态未批量变更"},
        ),
    )


@discovery_router.post("/device-discoveries", response_model=ResponseModel, status_code=201)
async def create_device_discovery(
    payload: Optional[Dict[str, Any]] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """同步 ADB 发现（契约 §5）：请求体固定空对象 {}；非空对象/未知字段 400。

    成功 201，ADB 失败 503，发现不改既有 owner/PC/version。
    """
    if payload:
        # 契约 §5：请求体必须为空对象；任何键（含未知字段/owner_id 等）都非法
        return JSONResponse(
            status_code=400,
            content=build_error_body(
                "VALIDATION_ERROR",
                "请求体不合法",
                {"field": "body", "reason": "发现请求体必须为空对象 {}"},
            ),
        )
    if not (current_user.pc_identifier or "").strip():
        # 普通用户无 PC 标识也可发现（新设备 owner=null），此处不做限制
        pass
    try:
        devices = await device_service.discover_devices(
            db, current_user, current_user.pc_identifier or ""
        )
    except ADBDiscoveryError:
        return _adb_failure_response()
    return _discovery_response(devices)


@router.get("/{serial}/knowledge", response_model=ResponseModel)
async def get_device_related_knowledge(
    serial: str,
    entry_type: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取与设备画像相关的知识库条目。"""
    pc_identifier = current_user.pc_identifier or ""
    device = await device_service.get_device_by_serial(db, serial)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    ensure_device_access(current_user, device, pc_identifier)

    entry_types = [entry_type] if entry_type else None
    items = await get_device_knowledge(db, device, entry_types=entry_types, limit=limit)
    return ResponseModel(code=200, data={"items": items, "total": len(items)})


@router.get("", response_model=ResponseModel)
async def list_devices(
    status: Optional[DeviceStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取设备列表（契约 §3：page>=1、1<=page_size<=100，非法 400 VALIDATION_ERROR）"""
    pc_identifier = current_user.pc_identifier or ""

    devices = await device_service.get_devices_for_user(db, current_user, pc_identifier)
    # 按契约统一授权过滤（普通用户仅 owner=本人且 PC 一致），服务端生效，不只靠前端隐藏
    devices = filter_visible_devices(current_user, devices, pc_identifier)

    if status:
        devices = [d for d in devices if d.status == status]

    total = len(devices)
    start = (page - 1) * page_size
    page_items = devices[start:start + page_size]

    return ResponseModel(
        code=200,
        data={
            "items": [DeviceResponse.model_validate(d) for d in page_items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/refresh", response_model=ResponseModel, deprecated=True)
async def refresh_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[legacy] 刷新设备列表：委托同一发现服务（语义与 /device-discoveries 一致）。

    保留旧响应字段 found_devices，并补充 items/total/owner_unchanged。ADB 失败 503。
    """
    pc_identifier = current_user.pc_identifier or ""
    try:
        devices = await device_service.discover_devices(db, current_user, pc_identifier)
    except ADBDiscoveryError:
        return _adb_failure_response()

    return ResponseModel(
        code=200,
        message="刷新成功",
        data={
            "found_devices": len(devices),
            "items": [DeviceResponse.model_validate(d) for d in devices],
            "total": len(devices),
            "owner_unchanged": True,
        },
    )


@router.get("/{serial}", response_model=ResponseModel)
async def get_device(
    serial: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取设备详情"""
    pc_identifier = current_user.pc_identifier or ""

    device = await device_service.get_device_by_serial(db, serial)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 统一授权：非管理员仅 owner=本人且 PC 一致；403 时 details 需含 field=serial
    try:
        ensure_device_access(current_user, device, pc_identifier)
    except HTTPException as exc:
        if exc.status_code == 403:
            return JSONResponse(
                status_code=403,
                content=build_error_body(
                    "FORBIDDEN",
                    DEVICE_FORBIDDEN_MESSAGE,
                    {"field": "serial", "reason": "owner或PC分组不满足"},
                ),
            )
        raise

    return ResponseModel(code=200, data=DeviceResponse.model_validate(device))


@router.patch("/{serial}", response_model=ResponseModel)
async def assign_device(
    serial: str,
    payload: DeviceAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """管理员改派设备归属/PC 分组（契约 §6，乐观并发 version 条件更新）。"""
    device = await device_service.get_device_by_serial(db, serial)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    target_pc = (payload.pc_identifier or "").strip()
    if not target_pc:
        return JSONResponse(
            status_code=400,
            content=build_error_body(
                "VALIDATION_ERROR", "设备归属参数不合法",
                {"field": "pc_identifier", "reason": "去除首尾空白后不能为空"},
            ),
        )

    target_owner_id = payload.owner_id
    if target_owner_id is not None:
        target_user = await db.get(User, target_owner_id)
        if target_user is None:
            return JSONResponse(
                status_code=404,
                content=build_error_body("NOT_FOUND", "目标用户不存在", {"field": "owner_id"}),
            )
        if target_user.status != "active":
            return JSONResponse(
                status_code=400,
                content=build_error_body(
                    "VALIDATION_ERROR", "设备归属参数不合法",
                    {"field": "owner_id", "reason": "目标用户未激活"},
                ),
            )

    # 完全重放（相同 owner + 相同 pc）即使 version 旧也返回当前设备（幂等）
    if device.owner_id == target_owner_id and (device.pc_identifier or "") == target_pc:
        return ResponseModel(code=200, message="设备归属已更新", data=_device_payload(device))

    if device.version != payload.version:
        return JSONResponse(
            status_code=409,
            content=build_error_body(
                "CONFLICT", "设备已被其他操作更新",
                {"field": "version", "reason": "请重新读取后提交"},
            ),
        )

    # 条件更新：WHERE id=? AND version=?，version 递增，防止并发覆盖
    result = await db.execute(
        update(Device)
        .where(Device.id == device.id, Device.version == payload.version)
        .values(owner_id=target_owner_id, pc_identifier=target_pc, version=Device.version + 1)
    )
    if result.rowcount == 0:
        await db.rollback()
        await db.refresh(device)
        if device.owner_id == target_owner_id and (device.pc_identifier or "") == target_pc:
            return ResponseModel(code=200, message="设备归属已更新", data=_device_payload(device))
        return JSONResponse(
            status_code=409,
            content=build_error_body(
                "CONFLICT", "设备已被其他操作更新",
                {"field": "version", "reason": "请重新读取后提交"},
            ),
        )

    await db.commit()
    await db.refresh(device)
    return ResponseModel(code=200, message="设备归属已更新", data=_device_payload(device))


@router.put("/{serial}/status", response_model=ResponseModel)
async def update_device_status(
    serial: str,
    status_update: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新设备状态（管理员）"""
    device = await device_service.get_device_by_serial(db, serial)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    if status_update.status:
        await device_service.update_device_status(db, device.id, status_update.status)

    return ResponseModel(code=200, message="状态更新成功")


@router.delete("/{serial}", response_model=ResponseModel)
async def delete_device(
    serial: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除设备（管理员）"""
    device = await device_service.get_device_by_serial(db, serial)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    await db.delete(device)
    await db.commit()

    return ResponseModel(code=200, message="设备已删除")
