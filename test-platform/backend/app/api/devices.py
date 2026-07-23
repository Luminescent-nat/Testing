from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin
from app.models import User, Device
from app.schemas import (
    DeviceResponse, DeviceUpdate, DeviceList, ResponseModel,
    DeviceStatus
)
from app.services.device import DeviceService
from app.services.knowledge_matcher import get_device_knowledge

router = APIRouter(prefix="/devices", tags=["设备管理"])
device_service = DeviceService()


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

    if not await device_service.check_device_access(db, current_user, device, pc_identifier):
        raise HTTPException(status_code=403, detail="无权限访问此设备")

    entry_types = [entry_type] if entry_type else None
    items = await get_device_knowledge(db, device, entry_types=entry_types, limit=limit)
    return ResponseModel(code=200, data={"items": items, "total": len(items)})


@router.get("", response_model=ResponseModel)
async def list_devices(
    status: Optional[DeviceStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取设备列表"""
    pc_identifier = current_user.pc_identifier or ""
    
    # 获取设备列表
    devices = await device_service.get_devices_for_user(db, current_user, pc_identifier)
    
    # 筛选状态
    if status:
        devices = [d for d in devices if d.status == status]
    
    return ResponseModel(
        code=200,
        data={
            "items": [DeviceResponse.model_validate(d) for d in devices],
            "total": len(devices)
        }
    )


@router.post("/refresh", response_model=ResponseModel)
async def refresh_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """刷新设备列表（重新扫描ADB设备）"""
    pc_identifier = current_user.pc_identifier or ""
    
    try:
        # 发现和同步设备
        devices = await device_service.discover_devices(db, current_user, pc_identifier)
        
        return ResponseModel(
            code=200,
            message="刷新成功",
            data={
                "found_devices": len(devices),
                "items": [DeviceResponse.model_validate(d) for d in devices]
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刷新设备失败: {str(e)}"
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
    
    # 检查权限
    if not await device_service.check_device_access(db, current_user, device, pc_identifier):
        raise HTTPException(status_code=403, detail="无权限访问此设备")
    
    return ResponseModel(code=200, data=DeviceResponse.model_validate(device))


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
