"""T-01：统一接口错误外层与目标路由适配的集成测试。

错误码真实触发方式（不修改生产代码制造错误）：
- 400 VALIDATION_ERROR：业务校验（离线设备/重跑无失败项）与 RequestValidationError
  （缺字段、数组元素类型错误、query 参数类型错误）；
- 401 UNAUTHENTICATED：无效 token、缺少 token（HTTPBearer 403 归并 401）；
- 403 FORBIDDEN：非 owner 查看/取消他人任务、普通用户访问管理员接口；
- 404 NOT_FOUND：任务不存在（GET 与目标别名 POST）；
- 409 CONFLICT：AI 任务目标设备 testing（ai_tasks.py 真实业务分支）；
- 503 SERVICE_UNAVAILABLE / 500 INTERNAL_ERROR：当前生产代码没有可触发路径
  （ADB 失败关闭与错误映射由 T-13 等后续任务实现），按任务约定用
  app.add_api_route 临时测试路由真实触发处理器，测试结束立即移除。
"""
import pytest
from contextlib import contextmanager
from httpx import ASGITransport, AsyncClient
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import get_settings
from app.main import app
from app.models import Device, TestItem, TestRecord, TestTask
from app.services.task_executor import TaskExecutor


CONTRACT_CODES = {
    "VALIDATION_ERROR",
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "NOT_FOUND",
    "CONFLICT",
    "INTERNAL_ERROR",
    "SERVICE_UNAVAILABLE",
}


def assert_error_contract(response, status_code, code):
    """严格核对契约错误外层：HTTP 状态、机器码、中文摘要、details 结构与无泄露。"""
    assert response.status_code == status_code, response.text
    body = response.json()  # 必须是合法 JSON
    assert set(body) == {"code", "message", "details"}, response.text
    assert isinstance(body["code"], str) and body["code"] == code
    assert body["code"] in CONTRACT_CODES
    assert isinstance(body["message"], str) and body["message"].strip()
    assert isinstance(body["details"], dict)
    assert set(body["details"]).issubset({"field", "item_id", "reason"})
    assert "detail" not in body  # 不再返回 legacy 顶层 detail 键
    text = response.text
    for forbidden in ("Traceback", "LEAK_SECRET_TOKEN_9527", "SELECT "):
        assert forbidden not in text, response.text
    return body


@contextmanager
def temporary_route(path, endpoint, methods=("POST",)):
    """临时挂载测试路由：插到路由表最前，避开末尾 SPA Mount，退出时移除。"""
    app.add_api_route(path, endpoint, methods=list(methods))
    route = app.router.routes.pop()
    app.router.routes.insert(0, route)
    try:
        yield
    finally:
        app.router.routes.remove(route)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- 400 VALIDATION_ERROR
@pytest.mark.asyncio
async def test_business_400_offline_device(client: AsyncClient, admin_token: str,
                                           sample_device: Device, sample_item: TestItem):
    """业务校验 400：离线设备创建任务，外层为契约结构且 message 保留中文安全摘要。"""
    res = await client.put(f"/api/v1/devices/{sample_device.serial_number}/status",
                           headers=auth(admin_token), json={"status": "offline"})
    assert res.status_code == 200
    response = await client.post("/api/v1/tasks", headers=auth(admin_token),
                                 json={"device_serial": sample_device.serial_number,
                                       "item_ids": [sample_item.id]})
    body = assert_error_contract(response, 400, "VALIDATION_ERROR")
    assert "离线" in body["message"]
    assert body["details"] == {}


@pytest.mark.asyncio
async def test_request_validation_400_missing_field(client: AsyncClient, admin_token: str,
                                                    test_db, sample_device: Device):
    """RequestValidationError(原 422) → 400，details.field 为缺失字段名。"""
    response = await client.post("/api/v1/tasks", headers=auth(admin_token),
                                 json={"item_ids": [1]})
    body = assert_error_contract(response, 400, "VALIDATION_ERROR")
    assert body["details"]["field"] == "device_serial"
    assert "reason" in body["details"]
    # 校验在业务写入前：数据库无新增任务
    count = await test_db.scalar(select(func.count()).select_from(TestTask))
    assert count == 0


@pytest.mark.asyncio
async def test_request_validation_400_dotted_array_index(client: AsyncClient, admin_token: str,
                                                         sample_device: Device):
    """字段路径数组下标使用点号：item_ids.0。"""
    response = await client.post("/api/v1/tasks", headers=auth(admin_token),
                                 json={"device_serial": sample_device.serial_number,
                                       "item_ids": ["not-an-int"]})
    body = assert_error_contract(response, 400, "VALIDATION_ERROR")
    assert body["details"]["field"] == "item_ids.0"


@pytest.mark.asyncio
async def test_request_validation_400_query_field(client: AsyncClient, admin_token: str):
    """query 参数校验失败也返回 400，details.field 为参数名。"""
    response = await client.get("/api/v1/tasks?page=not-a-number", headers=auth(admin_token))
    body = assert_error_contract(response, 400, "VALIDATION_ERROR")
    assert body["details"]["field"] == "page"


# ---------------------------------------------------------------- 401 UNAUTHENTICATED
@pytest.mark.asyncio
async def test_401_invalid_token(client: AsyncClient):
    """无效 token → 401 UNAUTHENTICATED，且保留 WWW-Authenticate 头。"""
    response = await client.get("/api/v1/tasks", headers=auth("invalid.token.value"))
    body = assert_error_contract(response, 401, "UNAUTHENTICATED")
    assert "认证" in body["message"]
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_401_missing_token(client: AsyncClient):
    """缺少 Authorization 头（HTTPBearer 原 403）→ 契约 401 UNAUTHENTICATED。"""
    response = await client.get("/api/v1/auth/me")
    assert_error_contract(response, 401, "UNAUTHENTICATED")


# ---------------------------------------------------------------- 403 FORBIDDEN
@pytest.mark.asyncio
async def test_403_non_owner_task(client: AsyncClient, admin_token: str, normal_token: str,
                                  sample_device: Device, sample_item: TestItem, monkeypatch):
    """非 owner 查看他人任务 → 403 FORBIDDEN（角色/归属不允许）。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    created = await client.post("/api/v1/tasks", headers=auth(admin_token),
                                json={"device_serial": sample_device.serial_number,
                                      "item_ids": [sample_item.id]})
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]

    response = await client.get(f"/api/v1/tasks/{task_id}", headers=auth(normal_token))
    body = assert_error_contract(response, 403, "FORBIDDEN")
    assert "权限" in body["message"]


@pytest.mark.asyncio
async def test_403_admin_only_endpoint(client: AsyncClient, normal_token: str):
    """普通用户访问管理员接口 → 403 FORBIDDEN。"""
    response = await client.delete("/api/v1/tasks/1", headers=auth(normal_token))
    assert_error_contract(response, 403, "FORBIDDEN")


# ---------------------------------------------------------------- 404 NOT_FOUND
@pytest.mark.asyncio
async def test_404_task_not_found(client: AsyncClient, admin_token: str):
    """任务不存在 → 404 NOT_FOUND。"""
    response = await client.get("/api/v1/tasks/999999", headers=auth(admin_token))
    body = assert_error_contract(response, 404, "NOT_FOUND")
    assert "任务不存在" in body["message"]


# ---------------------------------------------------------------- 409 CONFLICT（真实业务分支）
@pytest.mark.asyncio
async def test_409_ai_task_device_busy(client: AsyncClient, admin_token: str,
                                       sample_device: Device, mock_adb):
    """AI 任务目标设备 testing → 409 CONFLICT（状态冲突真实触发）。"""
    res = await client.put(f"/api/v1/devices/{sample_device.serial_number}/status",
                           headers=auth(admin_token), json={"status": "testing"})
    assert res.status_code == 200
    response = await client.post("/api/v1/ai/tasks/natural", headers=auth(admin_token),
                                 json={"text": "对 rk3568 设备做 DDR 功能测试"})
    body = assert_error_contract(response, 409, "CONFLICT")
    assert "设备正在执行其他任务" in body["message"]


# ---------------------------------------------------------------- 503（临时路由触发处理器）
@pytest.mark.asyncio
async def test_503_service_unavailable(client: AsyncClient):
    """503 SERVICE_UNAVAILABLE：当前 ADB 失败关闭尚未实现，用临时路由真实触发映射。"""

    async def adb_unavailable():
        raise HTTPException(status_code=503, detail="ADB 服务不可用")

    with temporary_route("/api/v1/__t01__/adb-unavailable", adb_unavailable):
        response = await client.post("/api/v1/__t01__/adb-unavailable")
    body = assert_error_contract(response, 503, "SERVICE_UNAVAILABLE")
    assert "ADB" in body["message"]


# ---------------------------------------------------------------- 500（临时路由触发处理器）
@pytest.mark.asyncio
async def test_500_unexpected_exception_no_leak_even_in_debug(client: AsyncClient, monkeypatch):
    """未预期异常 → 500 INTERNAL_ERROR：DEBUG 开关下也不返回异常文本/路径/堆栈。"""
    monkeypatch.setattr(get_settings(), "DEBUG", True)

    async def boom():
        raise RuntimeError("LEAK_SECRET_TOKEN_9527 D:\\MCTEST\\db.sqlite SELECT * FROM users")

    # ServerErrorMiddleware 会在发送处理器响应后重新抛异常；测试客户端需关闭
    # raise_app_exceptions 才能读取已发出的 500 响应（生产 uvicorn 行为一致）
    with temporary_route("/api/v1/__t01__/boom", boom):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as raw_client:
            response = await raw_client.post("/api/v1/__t01__/boom")
    body = assert_error_contract(response, 500, "INTERNAL_ERROR")
    assert body["details"] == {}
    assert "LEAK_SECRET_TOKEN_9527" not in response.text
    assert "db.sqlite" not in response.text
    assert "服务器内部错误" in body["message"]


# ---------------------------------------------------------------- 目标路由别名与成功外层
@pytest.mark.asyncio
async def test_cancellations_alias_delegates_cancel(client: AsyncClient, admin_token: str,
                                                    sample_device: Device, sample_item: TestItem,
                                                    monkeypatch, test_db):
    """POST /tasks/{id}/cancellations 委托 cancel_task：取消成功且落库，成功外层不变。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    created = await client.post("/api/v1/tasks", headers=auth(admin_token),
                                json={"device_serial": sample_device.serial_number,
                                      "item_ids": [sample_item.id]})
    task_id = created.json()["data"]["id"]

    response = await client.post(f"/api/v1/tasks/{task_id}/cancellations",
                                 headers=auth(admin_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"code", "message", "data"}
    assert body["code"] == 200 and "已取消" in body["message"]
    test_db.expire_all()
    task = await test_db.get(TestTask, task_id)
    assert task.status == "cancelled"

    # 同一业务语义：已终态任务再取消返回 400（非另一套逻辑），legacy 亦同
    again = await client.post(f"/api/v1/tasks/{task_id}/cancellations", headers=auth(admin_token))
    assert_error_contract(again, 400, "VALIDATION_ERROR")
    legacy = await client.post(f"/api/v1/tasks/{task_id}/cancel", headers=auth(admin_token))
    assert_error_contract(legacy, 400, "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_cancellations_alias_same_auth(client: AsyncClient, admin_token: str,
                                             normal_token: str, admin_user, sample_device: Device,
                                             sample_item: TestItem, test_db):
    """别名沿用同一鉴权：非 owner 经目标路径取消他人任务仍 403。"""
    task = TestTask(user_id=admin_user.id, device_id=sample_device.id,
                    name="OwnerTask", selected_items=[sample_item.id], status="pending")
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    response = await client.post(f"/api/v1/tasks/{task.id}/cancellations",
                                 headers=auth(normal_token))
    body = assert_error_contract(response, 403, "FORBIDDEN")
    assert "无权限取消此任务" in body["message"]
    await test_db.refresh(task)
    assert task.status == "pending"  # 越权无写入


@pytest.mark.asyncio
async def test_reruns_alias_delegates_rerun(client: AsyncClient, admin_token: str,
                                            admin_user, sample_device: Device,
                                            sample_item: TestItem, test_db, monkeypatch):
    """POST /tasks/{id}/reruns 委托 rerun_failed_items：无失败项 400，有失败项创建重跑任务。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    task = TestTask(user_id=admin_user.id, device_id=sample_device.id,
                    name="RerunSrc", selected_items=[sample_item.id], status="completed")
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    empty = await client.post(f"/api/v1/tasks/{task.id}/reruns", headers=auth(admin_token))
    assert_error_contract(empty, 400, "VALIDATION_ERROR")

    test_db.add(TestRecord(task_id=task.id, item_id=sample_item.id,
                           status="fail", fail_reason="断言失败"))
    await test_db.commit()

    response = await client.post(f"/api/v1/tasks/{task.id}/reruns", headers=auth(admin_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"code", "message", "data"}
    assert body["code"] == 200
    assert body["data"]["name"] == "RerunSrc（重跑）"
    assert body["data"]["device_serial"] == sample_device.serial_number


@pytest.mark.asyncio
async def test_alias_not_found_404(client: AsyncClient, admin_token: str):
    """目标路径任务不存在 → 404（与 legacy 一致）。"""
    for path in ("/api/v1/tasks/999999/cancellations", "/api/v1/tasks/999999/reruns",
                 "/api/v1/tasks/999999/cancel", "/api/v1/tasks/999999/rerun-failed"):
        response = await client.post(path, headers=auth(admin_token))
        assert_error_contract(response, 404, "NOT_FOUND")
