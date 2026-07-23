from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

import asyncio
import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import init_db, close_db, AsyncSessionLocal
from app.api import auth, users, devices, modules, tasks, reports, ai_tasks, memory, tools, knowledge, records
from app import websocket
from app.models import Device, TestRecord, TestTask
from app.seed_data import seed_default_data
from app.services.device import ADBService
from app.services.scheduler import scheduler_loop
from app.logging_config import setup_logging

# 全局日志：滚动文件（10MB×5）+ 控制台，幂等，详见 app/logging_config.py
setup_logging()

settings = get_settings()
logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "服务重启导致任务中断"


async def recover_interrupted_state(db: AsyncSession):
    """服务启动时恢复上次异常退出留下的中间状态。

    - running/pending 的 TestTask 标记为 failed，并注明中断原因；
    - 这些任务下未完成的 TestRecord（running/pending）标记为 error；
    - testing 状态的 Device 恢复为 online（其他状态不动）。
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(TestTask).where(TestTask.status.in_(["running", "pending"]))
    )
    interrupted_tasks = result.scalars().all()
    recovered_count = 0
    for task in interrupted_tasks:
        # 调度中的任务（pending 且带 next_run_at，从未启动）不算中断，
        # 保留 pending 等待调度器到期触发
        if task.status == "pending" and task.next_run_at is not None:
            continue
        task.status = "failed"
        task.error_message = INTERRUPTED_MESSAGE
        task.completed_at = now
        recovered_count += 1

        rec_result = await db.execute(
            select(TestRecord).where(
                TestRecord.task_id == task.id,
                TestRecord.status.in_(["running", "pending"]),
            )
        )
        for record in rec_result.scalars().all():
            record.status = "error"
            record.fail_reason = INTERRUPTED_MESSAGE
            record.completed_at = now

    result = await db.execute(select(Device).where(Device.status == "testing"))
    for device in result.scalars().all():
        device.status = "online"
        device.last_seen_at = now

    if recovered_count:
        print(f"状态恢复：{recovered_count} 个被中断任务已标记为 failed")
    await db.commit()


async def device_heartbeat_loop():
    """后台设备心跳循环：按 HEARTBEAT_INTERVAL 周期同步设备 online/offline 状态。

    单次心跳异常（如 adb 不存在）只记日志，循环继续；仅 CancelledError 退出。
    """
    adb_service = ADBService()
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await adb_service.heartbeat_check(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("设备心跳检测失败，将在下个周期重试")
        await asyncio.sleep(settings.HEARTBEAT_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    await init_db()
    print("数据库初始化完成")

    async with AsyncSessionLocal() as db:
        # 恢复上次服务异常退出留下的中断状态
        await recover_interrupted_state(db)
        # 初始化默认用例模板
        await seed_default_data(db)

    # 启动后台设备心跳任务
    heartbeat_task = asyncio.create_task(device_heartbeat_loop())
    # 启动后台任务调度器
    scheduler_task = asyncio.create_task(scheduler_loop())
    try:
        yield
    finally:
        # 关闭时取消心跳与调度任务并等待其退出
        heartbeat_task.cancel()
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        with suppress(asyncio.CancelledError):
            await scheduler_task
        # 关闭时执行
        await close_db()
        print("数据库连接已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Android设备测试平台API",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "detail": str(exc) if settings.DEBUG else None
        }
    )


# 注册路由
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(modules.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(records.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(ai_tasks.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(tools.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(websocket.router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


class SPAStaticFiles(StaticFiles):
    """前端静态文件挂载，带 vue-router history 模式 fallback。

    路径对应文件不存在时回退到 index.html，由前端路由接管；
    API/WS 路由在挂载之前注册，优先匹配，不受影响。
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


# 前端静态文件挂载（必须在所有路由之后，避免遮蔽 /health 等内置路由）：
# 目录不存在时跳过挂载，仅提供 API（如前端未构建的场景）
if os.path.isdir(settings.STATIC_PATH):
    app.mount("/", SPAStaticFiles(directory=settings.STATIC_PATH, html=True), name="static")
else:
    logger.warning("前端静态目录 %s 不存在，跳过静态文件挂载（仅提供 API）", settings.STATIC_PATH)
