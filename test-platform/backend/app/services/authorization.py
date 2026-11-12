"""统一设备与任务授权策略（契约 v1.0：docs/contracts/device-authorization-v1.0.md §1）。

本模块是设备/任务访问授权的唯一事实来源，供以下入口复用，避免各入口各写一套
权限语义（不得只靠前端隐藏）：

- 手动创建任务（app/api/tasks.py create_task）
- AI 自然语言创建任务（app/api/ai_tasks.py）
- 失败重跑（app/api/tasks.py rerun_failed_items）
- 设备列表/详情/知识（app/api/devices.py）
- 报告读取/导出/缓存（app/api/reports.py）
- 任务进度 WS 首消息订阅（app/websocket.py，由调用方转成 1008 关闭）

授权真值表（摘要）：
| 当前用户 | owner_id | PC 分组 | 设备可见/创建任务 |
|---|---|---|---|
| active 管理员 | 任意 | 任意 | 允许（设备可用性另判） |
| active 普通用户 | 本人 | 一致 | 允许（设备可用性另判） |
| active 普通用户 | 本人 | 不一致 | 403 |
| active 普通用户 | 他人或 null | 任意 | 403 |
| disabled/无效 token | 任意 | 任意 | 403/401 |

说明：disabled 用户由 get_current_user 在 REST 层返回 403；本模块再做一次
防御性 active 校验，WS 等不经过 get_current_user 的入口直接复用本模块。
设备可用性（offline/maintenance/testing 排队）不属于授权判断，由各入口另行处理。
"""
from typing import Iterable, List, Optional

from fastapi import HTTPException

from app.models import Device, TestTask, User

DISABLED_MESSAGE = "用户已被禁用"
DEVICE_FORBIDDEN_MESSAGE = "无权限访问此设备"
TASK_CREATE_FORBIDDEN_MESSAGE = "无权限使用此设备创建任务"
REPORT_FORBIDDEN_MESSAGE = "无权限查看报告"


def is_admin(user: Optional[User]) -> bool:
    return bool(user) and getattr(user, "role", None) == "admin"


def is_active(user: Optional[User]) -> bool:
    return bool(user) and getattr(user, "status", None) == "active"


def ensure_active(user: Optional[User]) -> None:
    """disabled（或缺失）用户一律 403 FORBIDDEN。"""
    if not is_active(user):
        raise HTTPException(status_code=403, detail=DISABLED_MESSAGE)


def _user_pc(user: User) -> str:
    return (getattr(user, "pc_identifier", None) or "").strip()


def _device_pc(device: Device) -> str:
    return (getattr(device, "pc_identifier", None) or "").strip()


def can_access_device(
    user: Optional[User], device: Optional[Device], pc_identifier: Optional[str] = None
) -> bool:
    """判断用户是否可访问（列表可见/详情/在其上创建任务）该设备。

    - 管理员：任意设备；
    - 普通用户：owner 必须为本人，且设备 PC 分组与用户 PC 一致；owner=null/他人一律拒绝；
    - disabled/缺失用户：拒绝。
    """
    if not is_active(user) or device is None:
        return False
    if is_admin(user):
        return True
    if getattr(device, "owner_id", None) is None:
        return False
    if device.owner_id != getattr(user, "id", None):
        return False
    effective_pc = _user_pc(user) if pc_identifier is None else (pc_identifier or "").strip()
    return _device_pc(device) == effective_pc


def ensure_device_access(
    user: Optional[User],
    device: Optional[Device],
    pc_identifier: Optional[str] = None,
    message: str = DEVICE_FORBIDDEN_MESSAGE,
) -> None:
    """设备详情/知识等读取入口的统一校验，不满足抛 403。"""
    ensure_active(user)
    if not can_access_device(user, device, pc_identifier):
        raise HTTPException(status_code=403, detail=message)


def filter_visible_devices(
    user: Optional[User],
    devices: Iterable[Device],
    pc_identifier: Optional[str] = None,
) -> List[Device]:
    """设备列表按契约过滤：普通用户仅返回 owner=本人且 PC 一致的设备。"""
    return [d for d in devices if can_access_device(user, d, pc_identifier)]


def ensure_can_create_task_on_device(user: Optional[User], device: Optional[Device]) -> None:
    """手动创建 / AI 创建 / 失败重跑统一授权：写前校验，不满足抛 403 且零写入。"""
    ensure_active(user)
    if not can_access_device(user, device):
        raise HTTPException(status_code=403, detail=TASK_CREATE_FORBIDDEN_MESSAGE)


def can_read_task(user: Optional[User], task: Optional[TestTask]) -> bool:
    """任务/报告读取：管理员任意；普通用户仅本人任务；disabled 拒绝。"""
    if not is_active(user) or task is None:
        return False
    if is_admin(user):
        return True
    return getattr(task, "user_id", None) == getattr(user, "id", None)


def ensure_can_read_task(
    user: Optional[User], task: Optional[TestTask], message: str = REPORT_FORBIDDEN_MESSAGE
) -> None:
    """报告读取/导出/缓存与任务订阅的统一校验，不满足抛 403。"""
    ensure_active(user)
    if not can_read_task(user, task):
        raise HTTPException(status_code=403, detail=message)
