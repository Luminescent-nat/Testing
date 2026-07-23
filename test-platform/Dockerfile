# syntax=docker/dockerfile:1
# 测试平台一体化镜像：阶段 1 构建前端，阶段 2 运行 FastAPI 后端。
# 构建上下文为 test-platform/ 根目录：
#   docker build -t test-platform .
#
# 注意：当前 backend/app/main.py 未挂载前端静态文件，容器默认只提供 API（:8000）。
# 前端产物已打在镜像 /app/static 下，接线方法见 DEPLOYMENT.md「前端静态文件接线」。

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
# - weasyprint（requirements.txt 中声明但代码未使用）：pip 包本身为纯 Python，通常能装上；
#   若个别环境下安装失败，可直接从 requirements.txt 移除（无代码引用）。
#   如将来真正启用 weasyprint 生成 PDF，需追加系统库：
#   apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
RUN apt-get update && apt-get install -y --no-install-recommends \
        adb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码（.dockerignore 已排除 __pycache__ / *.db / *.log / tests / storage）
COPY backend/ ./

# 前端构建产物，供后续静态文件挂载接线使用（当前未被 serve）
COPY --from=frontend-build /build/dist ./static

# 数据目录：SQLite 数据库 + 上传文件/报告/测试日志，由 compose 挂载到宿主机 ./data 持久化。
# 通过环境变量覆盖 app/config.py 中的相对路径默认值，不改代码。
RUN mkdir -p /data/storage/tools /data/storage/reports /data/storage/logs
ENV DATABASE_URL="sqlite+aiosqlite:////data/test_platform.db" \
    STORAGE_PATH="/data/storage" \
    TOOLS_PATH="/data/storage/tools" \
    REPORTS_PATH="/data/storage/reports" \
    LOGS_PATH="/data/storage/logs"

EXPOSE 8000

# 单进程即可满足内网自用规模；init_db/种子数据/状态恢复在 lifespan 中自动完成
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
