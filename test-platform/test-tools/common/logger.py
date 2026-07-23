#!/usr/bin/env python3
"""统一日志配置。"""

import logging
import sys


def setup_logger(name: str = "test_tool", level: int = logging.INFO) -> logging.Logger:
    """配置并返回一个带标准格式的 logger。"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
