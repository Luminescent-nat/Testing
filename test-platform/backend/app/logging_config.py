"""集中式日志配置：RotatingFileHandler（10MB × 5 份）+ 控制台输出。

解决当前服务日志靠裸重定向（python ... > server.log）无轮转、文件无限
膨胀的问题。

接线方法（本模块未在 main.py 中接线，由后续任务完成，二选一）：

1. 模块级（推荐，尽早生效）：在 backend/app/main.py 顶部、
   `app = FastAPI(...)` 之前加两行：

       from app.logging_config import setup_logging
       setup_logging()

2. lifespan 内：在 lifespan 函数启动段第一行调用：

       setup_logging()

调用后：
- 所有 logger（含 uvicorn、uvicorn.error、uvicorn.access、sqlalchemy、
  应用自身的 app.* logger）统一输出到滚动文件与控制台；
- 文件写入 logs/server.log（相对于后端工作目录），单文件满 10MB 轮
  转，最多保留 5 份历史（server.log.1 ~ server.log.5）；
- 启动命令不再需要 `> server.log` 重定向。

重复调用是安全的（内部有幂等保护，不会叠加 handler）。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# 幂等标记：防止 uvicorn --reload 或多次 import 场景下重复挂 handler
_FLAG_ATTR = "_test_platform_logging_configured"


def setup_logging(
    log_path: str | Path = "logs/server.log",
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> Path:
    """初始化全局日志：滚动文件 + 控制台，并接管 uvicorn 的 logger。

    参数：
        log_path:     日志文件路径（相对路径基于进程工作目录，通常为 backend/）。
        level:        全局日志级别，默认 INFO。
        max_bytes:    单个日志文件最大字节数，默认 10MB。
        backup_count: 保留的历史文件份数，默认 5。

    返回日志文件的实际路径。
    """
    root = logging.getLogger()
    if getattr(root, _FLAG_ATTR, False):
        # 已配置过，直接返回，避免重复添加 handler 导致日志翻倍
        for handler in root.handlers:
            if isinstance(handler, RotatingFileHandler):
                return Path(handler.baseFilename)
        return Path(log_path).resolve()

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_DEFAULT_FORMAT)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # 接管 uvicorn 自带 logger：清空其独立 handler，改为向 root 传播，
    # 避免 uvicorn 自己的默认配置绕过轮转文件。
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True
        uv_logger.setLevel(level)

    setattr(root, _FLAG_ATTR, True)
    logging.getLogger(__name__).info("日志系统初始化完成，文件: %s", log_path.resolve())
    return log_path.resolve()
