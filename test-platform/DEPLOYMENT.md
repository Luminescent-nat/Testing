# 测试平台部署文档

适用环境：Windows 开发机 / Linux 内网服务器，FastAPI 后端 + Vue3 前端 + SQLite。

---

## 1. Docker 部署（推荐）

### 前提

- 宿主机已装 Docker Engine 20.10+ 与 Docker Compose v2（`docker compose version` 可查到即可）。
- 构建时需要能访问 npm 与 PyPI（内网可配置各自镜像源）。

### 首次部署

```bash
cd test-platform

# 如需迁移现有数据（全新部署可跳过）
mkdir -p data/storage
cp backend/test_platform.db data/
cp -r backend/storage/* data/storage/

# 生产环境务必设置 SECRET_KEY（写入 .env 文件，compose 自动读取）
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env

docker compose up -d --build
docker compose logs -f app
```

验证：`curl http://localhost:8000/health` 返回 `{"status":"healthy"}`。

### 说明

- 数据库与上传文件/报告/测试日志持久化在宿主机 `./data`（容器内 `/data`），
  由 Dockerfile 中的 `DATABASE_URL` / `STORAGE_PATH` 等环境变量指定，**不改动代码**。
- 升级：`docker compose up -d --build` 重建即可，`./data` 不受影响。
- 数据库迁移/建表由应用 lifespan 自动完成，无需手动执行。

### 前端静态文件接线（当前未接，需一次小改动）

`backend/app/main.py` 目前没有挂载前端静态文件（本任务未改动该文件），
因此容器默认**只提供 API**。前端产物已打在镜像 `/app/static` 下，接线只需在
`main.py` 注册路由之后加两行：

```python
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

- 容器内 `directory="static"` 即 `/app/static`；裸机部署时改为
  `directory="../frontend/dist"`（相对于 backend 工作目录）。
- 若前端使用 vue-router history 模式，直接刷新子路径会 404，届时需把
  静态挂载换成带 SPA fallback 的自定义路由（接线时处理）。

---

## 2. 裸机部署（无 Docker）

现有脚本仍然有效：

- Linux：`bash start_server.sh`（清缓存 → init_db → uvicorn 起 8000 端口）
- Windows：`bash start_windows.sh`

要点：

1. Python 3.12，先在 `backend/` 下建虚拟环境并 `pip install -r requirements.txt`。
2. 前端 `cd frontend && npm ci && npm run build`，产物在 `frontend/dist`；
   未做第 1 节的静态接线前，前端需用 `npm run preview` 或任意静态服务器单独托管。
3. 数据库为 `backend/test_platform.db`（相对工作目录），无需单独安装。
4. 日志目前为裸重定向 `> server.log`，接入日志轮转（第 4 节）后不再需要重定向。

---

## 3. 数据库备份

脚本：`scripts/backup_db.py`（纯标准库，Windows/Linux 通用）。
使用 sqlite3 backup API **在线备份**，服务运行中可直接执行，无需停服。
默认保留最近 30 份，自动清理更旧的。

```bash
# 裸机部署（默认源 = backend/test_platform.db，输出到 backups/）
python scripts/backup_db.py

# Docker 部署（源指向宿主机挂载目录）
python scripts/backup_db.py --source data/test_platform.db

# 自定义
python scripts/backup_db.py --source /path/to.db --dest-dir /path/to/backups --keep 30
```

定时任务：

```bash
# Linux crontab：每天凌晨 3 点
0 3 * * * cd /opt/test-platform && /usr/bin/python3 scripts/backup_db.py >> backups/backup_cron.log 2>&1
```

```bat
:: Windows 计划任务：每天凌晨 3 点
schtasks /create /tn "TestPlatformBackup" ^
  /tr "D:\MCTEST\test-platform\.venv\Scripts\python.exe D:\MCTEST\test-platform\scripts\backup_db.py" ^
  /sc daily /st 03:00
```

备份文件建议定期再拷贝到另一台机器（内网共享目录即可），防单机故障。

---

## 4. 日志轮转接线

新文件 `backend/app/logging_config.py` 提供 `setup_logging()`：
滚动文件（10MB × 5 份，默认 `logs/server.log`）+ 控制台输出，
并接管 `uvicorn` / `uvicorn.error` / `uvicorn.access` 三个 logger。

**尚未接线**（本任务未改 main.py）。接线二选一：

```python
# 方式一（推荐）：main.py 顶部、app = FastAPI(...) 之前
from app.logging_config import setup_logging
setup_logging()

# 方式二：lifespan 启动段第一行
setup_logging()
```

接线后启动命令去掉 `> server.log` 重定向。函数幂等，重复调用不会叠加 handler。

---

## 5. ADB 注意事项

后端通过 subprocess 直接调用 `adb` CLI（`backend/app/services/device.py`）。

**裸机部署**：宿主机装好 platform-tools 并确保 `adb` 在 PATH 即可。

**Docker 部署**：

- 镜像已装 `adb` 包。容器内 adb server 是独立的，**看不到宿主机的 adb 会话**。
- 推荐用**网络 adb**：设备/测试夹具开启 adb over network（设备上
  `adb tcpip 5555` 或通过 USB 先执行一次），容器启动后
  `docker exec test-platform adb connect <设备IP>:5555`。
  也可把 connect 命令写进宿主机 cron 做保活。
- **USB 直连**（不推荐，仅实验）：compose 中放开 `privileged: true`，
  且 Linux 宿主机需配置 udev 规则；Windows 宿主机 Docker Desktop 无法透传 USB。
- 备选方案：让容器使用宿主机的 adb server——宿主机 `adb -a -P 5037 nodaemon server`
  监听所有网卡，容器设 `ADB_SERVER_SOCKET=tcp:<宿主机IP>:5037`。
  注意容器内外 **adb 版本必须一致**，否则协议不匹配会自动杀掉重起 server。
- 设备心跳线程在 adb 不可用时只记日志不崩溃，无设备场景下服务本身可正常运行。

---

## 6. 内网部署检查清单

- [ ] `SECRET_KEY` 已改（`.env` 或 compose environment），不使用默认值
- [ ] `curl http://<host>:8000/health` 返回 healthy
- [ ] `./data` 已挂载且宿主机可读写，`data/test_platform.db` 存在
- [ ] 前端静态文件已接线（第 1 节），浏览器可访问首页
- [ ] 备份脚本已挂定时任务，手动执行一次确认 `backups/` 有产物
- [ ] 备份有异地拷贝（共享目录/另一台机器）
- [ ] 日志轮转已接线，确认 `logs/server.log` 正常写入
- [ ] adb 连通：`docker exec test-platform adb devices` 能看到被测设备
- [ ] LLM 相关配置（`LLM_API_KEY` 等）按内网可用服务配置；不配置时 AI 功能降级但不影响主流程
- [ ] 防火墙/端口：内网只需开放 8000
