"""
全局测试 fixture：测试数据库、HTTP 客户端、认证用户、Mock ADB/LLM。
"""
import asyncio
import os
import shutil
import sys
import tempfile
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# 将 backend 根目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 测试环境自包含配置：应用要求 SECRET_KEY 非空（lifespan 校验），
# 测试统一使用固定测试密钥，与生产密钥无关。
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production")

# 测试数据库隔离（V1-05）：部分用例用 `with TestClient(app)` 会真实触发 lifespan →
# app.database.init_db（生产迁移路径）。必须在导入 app 之前把 DATABASE_URL 指向
# 会话级临时 SQLite 文件，确保 init_db 绝不触碰真实 backend/test_platform.db。
# 未显式设置 DATABASE_URL 时才启用（尊重外部显式配置）。
if "DATABASE_URL" not in os.environ:
    _PYTEST_SESSION_DB_DIR = tempfile.mkdtemp(prefix="pytest_session_db_")
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(
        _PYTEST_SESSION_DB_DIR, "session.db"
    ).replace("\\", "/")
    os.environ["_PYTEST_SESSION_DB_DIR"] = _PYTEST_SESSION_DB_DIR


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """会话结束清理 pytest 会话级临时数据库目录（不触碰真实库）。"""
    session_dir = os.environ.get("_PYTEST_SESSION_DB_DIR")
    if session_dir:
        shutil.rmtree(session_dir, ignore_errors=True)

from app.config import get_settings  # noqa: E402
from app.database import AsyncSessionLocal, Base, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Device, TestItem, TestModule, TestTool, User  # noqa: E402
from app.seed_data import seed_default_data  # noqa: E402
from app.services.auth import create_access_token, get_password_hash  # noqa: E402
from app.services.device import ADBService  # noqa: E402
from app.services.task_executor import DeviceLock, TaskExecutor  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """将每个用例的工具、日志和报告写入独立临时目录。"""
    settings = get_settings()
    storage_path = tmp_path / "storage"
    paths = {
        "STORAGE_PATH": storage_path,
        "TOOLS_PATH": storage_path / "tools",
        "REPORTS_PATH": storage_path / "reports",
        "LOGS_PATH": storage_path / "logs",
    }
    for setting_name, path in paths.items():
        monkeypatch.setattr(settings, setting_name, str(path))
        path.mkdir(parents=True, exist_ok=True)
    return storage_path


async def _cleanup_background_tasks():
    """在测试数据库关闭前，取消并等待执行器及报告后台任务。"""
    current = asyncio.current_task()
    tasks = set(TaskExecutor._running_tasks.values())
    tasks.update(
        task
        for task in asyncio.all_tasks()
        if task is not current
        and task.get_name().startswith(("task-", "report-"))
    )
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()


@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """
    每个测试函数使用独立的临时文件 SQLite 数据库，并替换全局 engine / AsyncSessionLocal，
    保证 lifespan、seed_data、services 中直接使用的 AsyncSessionLocal 都落在测试库上。
    使用文件数据库 + NullPool，避免内存数据库单连接被后台任务与请求会话争抢。
    """
    fd, db_path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite")
    os.close(fd)
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        poolclass=NullPool,
        # task-C1（Lead 授权，仅测试夹具）：SQLite busy_timeout 默认 5s，
        # 并发取消/收尾与轮询读交错时写写冲突会等满超时后抛 database is locked，
        # 导致执行器正常路径误判平台异常；放宽到 30s 让瞬态争用靠等待化解。
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # task-C1（Lead 授权域，仅测试夹具）：WAL 模式——回滚日志模式下读者会被
        # PENDING 写锁直接拒（busy_timeout 不覆盖），并发取消用例的鉴权 SELECT
        # 因此偶发 database is locked；WAL 下读者与写者互不阻塞，写者间仍串行。
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")

    test_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # 替换 app.database 中的全局对象
    original_engine = engine
    original_session_local = AsyncSessionLocal
    import app.database as db_module
    import app.main as main_module
    import app.services.execution_engine as ee_module
    import app.services.task_executor as te_module
    import app.websocket as ws_module
    import app.api.reports as reports_module

    # 备份并替换
    original_locals = {
        "db_module.engine": db_module.engine,
        "db_module.AsyncSessionLocal": db_module.AsyncSessionLocal,
        "main_module.AsyncSessionLocal": getattr(main_module, "AsyncSessionLocal", None),
        "ee_module.AsyncSessionLocal": getattr(ee_module, "AsyncSessionLocal", None),
        "te_module.AsyncSessionLocal": getattr(te_module, "AsyncSessionLocal", None),
        "ws_module.AsyncSessionLocal": getattr(ws_module, "AsyncSessionLocal", None),
        "reports_module.AsyncSessionLocal": getattr(reports_module, "AsyncSessionLocal", None),
    }

    db_module.engine = test_engine
    db_module.AsyncSessionLocal = test_session_maker
    main_module.AsyncSessionLocal = test_session_maker
    ee_module.AsyncSessionLocal = test_session_maker
    te_module.AsyncSessionLocal = test_session_maker
    ws_module.AsyncSessionLocal = test_session_maker
    reports_module.AsyncSessionLocal = test_session_maker

    session = test_session_maker()
    try:
        yield session
    finally:
        await _cleanup_background_tasks()
        await session.close()
        db_module.engine = original_locals["db_module.engine"]
        db_module.AsyncSessionLocal = original_locals["db_module.AsyncSessionLocal"]
        main_module.AsyncSessionLocal = original_locals["main_module.AsyncSessionLocal"]
        ee_module.AsyncSessionLocal = original_locals["ee_module.AsyncSessionLocal"]
        te_module.AsyncSessionLocal = original_locals["te_module.AsyncSessionLocal"]
        ws_module.AsyncSessionLocal = original_locals["ws_module.AsyncSessionLocal"]
        reports_module.AsyncSessionLocal = original_locals["reports_module.AsyncSessionLocal"]
        await test_engine.dispose()
        try:
            os.remove(db_path)
        except OSError:
            pass
        # WAL sidecar 文件清理
        for suffix in ("-wal", "-shm"):
            try:
                os.remove(db_path + suffix)
            except OSError:
                pass


@pytest_asyncio.fixture(scope="function")
async def client(test_db: AsyncSession, mock_adb) -> AsyncGenerator[AsyncClient, None]:
    """返回基于测试数据库的 AsyncClient，并默认 Mock ADB 与清理后台任务。"""

    # 基于当前测试引擎创建 session maker，供 API 请求独立使用
    request_session_maker = async_sessionmaker(
        test_db.bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        # 每个请求使用独立会话，避免与后台任务共享连接/事务
        async with request_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # 清理异步任务与设备锁状态，避免用例间相互影响
    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()

    # 手动管理 lifespan：初始化测试表结构及种子数据
    async with test_db.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_default_data(test_db)
    await test_db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # 取消并等待所有后台任务结束，避免 pending task 跨用例导致 GeneratorExit / 会话泄漏
    pending = list(TaskExecutor._running_tasks.values())
    for task in pending:
        if not task.done():
            task.cancel()
    if pending:
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True), timeout=5.0
            )
        except asyncio.TimeoutError:
            pass

    app.dependency_overrides.clear()
    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()


@pytest_asyncio.fixture(scope="function")
async def admin_user(test_db: AsyncSession) -> User:
    """创建一个管理员用户。"""
    user = User(
        username="admin",
        password_hash=get_password_hash("admin123"),
        role="admin",
        status="active",
        pc_identifier="test-pc-admin",
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def admin_token(client: AsyncClient, admin_user: User, test_db: AsyncSession) -> str:
    """登录管理员用户，返回 JWT token。"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    # 登录会更新 pc_identifier，先刷新再恢复为测试固定值，确保 ORM 标记为脏数据并提交
    await test_db.refresh(admin_user)
    admin_user.pc_identifier = "test-pc-admin"
    await test_db.commit()
    return response.json()["data"]["access_token"]


@pytest_asyncio.fixture(scope="function")
async def normal_user(test_db: AsyncSession) -> User:
    """创建一个普通用户。"""
    user = User(
        username="normal",
        password_hash=get_password_hash("normal123"),
        role="user",
        status="active",
        pc_identifier="test-pc-normal",
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def normal_token(client: AsyncClient, normal_user: User, test_db: AsyncSession) -> str:
    """登录普通用户，返回 JWT token。"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "normal", "password": "normal123"},
    )
    assert response.status_code == 200, response.text
    # 登录会更新 pc_identifier，先刷新再恢复为测试固定值，确保 ORM 标记为脏数据并提交
    await test_db.refresh(normal_user)
    normal_user.pc_identifier = "test-pc-normal"
    await test_db.commit()
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="function")
def mock_adb(monkeypatch) -> MagicMock:
    """
    Mock ADBService 全部方法，避免测试调用真实 adb。
    默认返回：单台 rk3568 在线设备，shell 命令返回成功输出。
    """
    mock = MagicMock(spec=ADBService)
    mock.execute_shell = AsyncMock(return_value=("mock output", "", 0))
    mock.push_file = AsyncMock(return_value=("mock push output", "", 0))
    mock.pull_file = AsyncMock(return_value=("mock pull output", "", 0))
    mock.get_devices = AsyncMock(
        return_value=[
            {
                "serial": "rk3568-test",
                "state": "device",
                "product": "rk3568",
                "model": "rk3568",
                "device": "rk3568",
            }
        ]
    )
    mock.get_device_info = AsyncMock(
        return_value={
            "serial_number": "rk3568-test",
            "model": "rk3568",
            "brand": "rockchip",
            "android_version": "11",
            "sdk_version": "30",
            "cpu_abi": "arm64-v8a",
            "resolution": "1080x1920",
            "battery_level": 80,
        }
    )
    mock.is_device_online = AsyncMock(return_value=True)

    # 1) 替换 ADBService 类，使后续实例化返回 mock
    monkeypatch.setattr("app.services.device.ADBService", lambda: mock)

    # 2) 已导入模块中保存的是旧 ADBService 类引用，需要同步替换
    import app.services.execution_engine as ee_module
    import app.services.device_profile as dp_module
    import app.main as main_module

    ee_module.ADBService = lambda: mock
    dp_module.ADBService = lambda: mock
    # TestClient lifespan 在 main.py 中使用导入时绑定的类引用，也必须替换，
    # 否则后台心跳会绕过 fixture 并创建真实 ADB 子进程。
    monkeypatch.setattr(main_module, "ADBService", lambda: mock)

    # 3) devices.py 在模块导入时已创建 DeviceService 实例，直接替换其实例
    import app.api.devices as devices_api

    devices_api.device_service.adb = mock
    if hasattr(devices_api.device_service, "profile_service"):
        devices_api.device_service.profile_service.adb = mock

    return mock


@pytest.fixture(scope="function")
def mock_llm(monkeypatch) -> MagicMock:
    """Mock LLMClient，避免真实网络请求。"""
    mock = MagicMock()
    mock.chat_completion_structured = AsyncMock(
        return_value={
            "status": "pass",
            "confidence": 0.95,
            "score": 4,
            "metrics": {},
            "evidence": ["AI 判定通过"],
            "fail_reason": "",
            "suggestions": "",
        }
    )
    # 让 get_default_client() 返回 mock 实例本身，便于 AI 判定/提取使用
    mock.get_default_client = MagicMock(return_value=mock)
    monkeypatch.setattr("app.services.llm_client.LLMClient", mock)
    monkeypatch.setattr("app.services.knowledge_extractor.LLMClient", mock)
    return mock


@pytest_asyncio.fixture(scope="function")
async def sample_device(test_db: AsyncSession, admin_user: User) -> Device:
    """创建一台示例设备。"""
    device = Device(
        serial_number="rk3568-test",
        model="rk3568",
        brand="rockchip",
        android_version="11",
        sdk_version="30",
        cpu_abi="arm64-v8a",
        resolution="1080x1920",
        battery_level=80,
        status="online",
        owner_id=admin_user.id,
        pc_identifier=admin_user.pc_identifier,
        board="rk3568",
        hardware="rk3568-evb",
        ddr_info={"total_mb": 2048, "type": "LPDDR4", "frequency_mhz": 1600},
        emmc_info={"total_gb": 32, "model": "Samsung", "health": "good"},
        wifi_chip="AP6255",
        bt_chip="AP6255",
        eth_interfaces=["eth0"],
        features=["wifi", "bluetooth", "ethernet"],
    )
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)
    return device


@pytest_asyncio.fixture(scope="function")
async def sample_module(test_db: AsyncSession, admin_user: User) -> TestModule:
    """创建一个示例测试模块。"""
    module = TestModule(
        name="TestModule",
        category="test",
        description="A sample module",
        created_by=admin_user.id,
    )
    test_db.add(module)
    await test_db.commit()
    await test_db.refresh(module)
    return module


@pytest_asyncio.fixture(scope="function")
async def sample_item(
    test_db: AsyncSession, sample_module: TestModule, admin_user: User
) -> TestItem:
    """创建一个示例 adb_shell 测试项。"""
    item = TestItem(
        module_id=sample_module.id,
        name="Sample Item",
        description="A sample item",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        result_parse={"pass_pattern": "ok"},
        timeout=30,
        created_by=admin_user.id,
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)
    return item


@pytest_asyncio.fixture(scope="function")
async def sample_tool(test_db: AsyncSession, admin_user: User) -> TestTool:
    """创建一个示例测试工具记录与占位文件。"""
    tool_path = os.path.join(get_settings().TOOLS_PATH, "sample_tool")
    os.makedirs(os.path.dirname(tool_path), exist_ok=True)
    with open(tool_path, "wb") as f:
        f.write(b"#!/system/bin/sh\necho ok\n")

    tool = TestTool(
        name="sample_tool",
        filename="sample_tool",
        description="sample tool",
        version="1.0",
        architecture="arm64-v8a",
        file_size=os.path.getsize(tool_path),
        file_path=tool_path,
        created_by=admin_user.id,
    )
    test_db.add(tool)
    await test_db.commit()
    await test_db.refresh(tool)
    return tool
