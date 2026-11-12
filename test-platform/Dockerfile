# syntax=docker/dockerfile:1
# 测试平台一体化镜像：阶段 1 构建前端，阶段 2 运行 FastAPI 后端。
# 构建上下文为 test-platform/ 根目录：
#   docker build -t test-platform .
#
# 前端产物打在镜像 /app/static，并通过 STATIC_PATH 环境变量挂载到 /，
# 容器启动后浏览器直接访问 :8000 即可看到前端页面（API 在 /api/v1 下）。

# ---------- 阶段 1：构建前端 ----------
FROM node:20-alpine AS frontend-build
WORKDIR /build

# 仅拷贝依赖清单，充分利用镜像层缓存
COPY frontend/package.json frontend/package-lock.json ./

# PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD：跳过 e2e 浏览器下载，缩小构建体积（容器内不跑 e2e）
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------- 阶段 2：后端运行时 ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 系统依赖：
# - adb：后端通过 subprocess 直接调用 adb CLI（backend/app/services/device.py），必须安装。
#   容器内 adb 连接设备的方式（网络 adb / 宿主机 adb server）见 DEPLOYMENT.md。
RUN apt-get update && apt-get install -y --no-install-recommends \
        adb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码（.dockerignore 已排除 __pycache__ / *.db / *.log / tests / storage）
COPY backend/ ./

# test-tools：manifest + runner + 各架构二进制（T-17）。
# 干净镜像必须包含 manifest 声明的全部工具；启动时由 app/services/tool_manifest.py
# 做只读校验，缺失必需工具直接拒绝启动（范围内 APK 等可选资源缺失记 skip）。
COPY test-tools/ ./test-tools/

# 前端构建产物，由 STATIC_PATH 指向并在 main.py 中挂载到 /
COPY --from=frontend-build /build/dist ./static

# 数据目录：SQLite 数据库 + 上传文件/报告/测试日志，由 compose 挂载到宿主机 ./data 持久化。
# 通过环境变量覆盖 app/config.py 中的相对路径默认值，不改代码。
# TEST_TOOLS_PATH/STATIC_PATH 与镜像内工作目录 /app 对齐（host_exec 的 {host_tool_dir} 解析用）。
RUN mkdir -p /data/storage/tools /data/storage/reports /data/storage/logs
ENV DATABASE_URL="sqlite+aiosqlite:////data/test_platform.db" \
    STORAGE_PATH="/data/storage" \
    TOOLS_PATH="/data/storage/tools" \
    REPORTS_PATH="/data/storage/reports" \
    LOGS_PATH="/data/storage/logs" \
    TEST_TOOLS_PATH="/app/test-tools" \
    STATIC_PATH="/app/static"

EXPOSE 8000

# 单进程即可满足内网自用规模；init_db/种子数据/状态恢复在 lifespan 中自动完成
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
