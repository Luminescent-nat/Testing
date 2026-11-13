# 演示环境指南（DEMO）

- 版本：2026-11-13（演示前部署收口，任务 T-27）
- 适用范围：内网演示 / 验收演示，**不是生产部署指南**（生产见 `test-platform/DEPLOYMENT.md`）
- 关键原则：**演示使用独立数据库与独立存储目录，历史库只读保留、绝不改动**

---

## 1. 演示数据库策略（务必先读）

| 项目 | 约定 |
|---|---|
| 历史库 `test-platform/backend/test_platform.db` | **保留不动（只读）**。它是历史 create_all 时代的库，结构与当前 `app.models` 存在漂移；生产严格 `init_db` 会做 DDL 指纹比对并以 `SchemaMismatchError` 明确拒绝启动——**这是预期行为，不是故障**。 |
| 严禁操作 | 严禁对真实库/历史库执行 `alembic downgrade base`、`drop`、手工改表等任何破坏性操作。 |
| 演示库 | 独立 `test-platform/backend/demo.db`（`DATABASE_URL=sqlite+aiosqlite:///./demo.db`）。首次启动在**空库**上执行 `alembic upgrade head`（迁移链 001→004：`0817df993d8b` 初始 → `002_idempotency` → `003_device_version` → `004_task_deleted_at`）。 |
| 演示存储 | 独立 `test-platform/backend/storage/demo/`：`tools/`、`reports/`、`logs/` 子目录；上传件/报告/日志都落在这里，与历史 `backend/storage/` 隔离。 |
| 如需保留历史数据做演示 | **另立迁移任务**处理（对历史库做备份副本、逐 revision 升级/校验、数据迁移演练）。本演示指南不把历史数据迁入 demo.db，避免把结构漂移与数据迁移风险带进演示现场。 |
| 历史库只读约束 | 演示前后对历史库计算 SHA-256 并比对**必须一致**（见第 5 节实测记录）；演示期间不得有任何进程以写方式打开历史库。 |

> 演示库随时可整体重置：停服务后删除 `backend/demo.db` 与 `backend/storage/demo/`，重新执行启动脚本即重建空库（`001→004`）。

---

## 2. 启动演示环境

### 2.1 Windows（PowerShell）

```powershell
cd test-platform
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
# 可选：指定端口 / 显式密钥 / 仅初始化演示库后退出
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1 -Port 8001
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1 -SecretKey "<至少32字符随机密钥>"
powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1 -MigrateOnly
```

### 2.2 Linux / macOS / Git Bash

```bash
cd test-platform
bash scripts/start_demo.sh
bash scripts/start_demo.sh --port 8001
bash scripts/start_demo.sh --secret-key "<至少32字符随机密钥>"
bash scripts/start_demo.sh --migrate-only
```

### 2.3 脚本做了什么

1. 显式导出（覆盖 `backend/.env` 中的同名项）：

   | 变量 | 值 |
   |---|---|
   | `DATABASE_URL` | `sqlite+aiosqlite:///./demo.db` |
   | `STORAGE_PATH` | `storage/demo` |
   | `TOOLS_PATH` | `storage/demo/tools` |
   | `REPORTS_PATH` | `storage/demo/reports` |
   | `LOGS_PATH` | `storage/demo/logs` |
   | `TEST_TOOLS_PATH` | `../test-tools`（启动时只读工具清单校验用） |

2. 解析 `SECRET_KEY`：`--secret-key`/`-SecretKey` 参数 → `DEMO_SECRET_KEY` 环境变量 → `SECRET_KEY` 环境变量 → `backend/.env` 的 `SECRET_KEY` → 本次运行临时随机生成（仅当次有效，会在控制台提示）。
   （`SECRET_KEY` 必须满足强度校验：≥32 字符、非示例占位值、非单字符重复，否则应用拒绝启动。）
3. 创建 `storage/demo/{tools,reports,logs}`。
4. 在 `backend/` 目录执行 `alembic upgrade head`（空库 001→004；已迁移库为幂等 no-op）并打印 `alembic current`。
5. 启动 `uvicorn app.main:app`（默认端口 8000）。

脚本不会触碰 `backend/test_platform.db`；请在启动输出中确认「历史库保留不动（只读）」提示。

---

## 3. A133P 只读演示清单（推荐流程）

演示目标：展示「创建任务 → 执行只读命令 → 判定通过 → 生成报告 → HTML 导出」的完整闭环，全程**不对设备做任何写入/烧录/重启/压测**。

前置：
- 设备 A133P 已通过 ADB 连接（`adb devices` 可见；serial 如 `5c000c2834414751c9d`，只读使用）。
- 登录后管理员执行设备发现/刷新，使设备出现在列表并分配 owner（管理员可见全部设备）。
- 测试项使用 `adb_shell` 且命令**只读**，例如 `cat /proc/meminfo`（本演示清单固定用它）。

| 步骤 | 操作 | 预期 |
|---|---|---|
| 1 | 登录（首个注册用户自动为 admin） | 200 登录成功，获得 token |
| 2 | `POST /api/v1/devices/refresh`（或 `POST /api/v1/device-discoveries`）发现设备 | 200/201，设备出现在列表 |
| 3 | 创建任务（`schedule_type=immediate`，选中只读测试项 `cat /proc/meminfo`） | **HTTP 201**，任务 `pending`，随即执行 |
| 4 | 轮询任务详情直至终态 | `completed`，记录 `pass`，`progress=100`，`result=passed` |
| 5 | 查看报告 | 通过率 100%（skip 不计入分母） |
| 6 | 导出 HTML 报告 | 下载/打开 HTML，报告内容与任务记录一致 |

只读演示命令示例（严禁替换为写操作）：

```bash
adb -s <serial> shell cat /proc/meminfo      # 只读
```

**明确不做**：不向设备写入/推送文件、不安装/卸载 APK、不烧录固件、不重启设备、不做 fio/memtester 等压测或稳定性写操作、不修改系统设置（如 settings put / svc）。

---

## 4. daily / once 定时演示：禁用

- 当前版本 **daily/once 定时任务的执行链路（T-11/T-12）尚未实施**，界面已禁用并标注「后续版本」。
- 演示时**不要**演示 daily/once 定时调度，也不要用它们作为「已实现」的证据。演示只用 `schedule_type=immediate` 的立即任务。
- 如需展示调度能力，明确说明其为规划中能力，不在本次演示范围。

---

## 5. AI / LLM 配置（演示口径）

- 后端仅支持 **OpenAI-compatible `/chat/completions`** 接口（`LLM_BASE_URL` 指向兼容服务，默认 `https://api.openai.com/v1`）。
- 相关环境变量（详见 `backend/.env.example`）：`LLM_PROVIDER`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_TEMPERATURE`、`LLM_MAX_TOKENS`、`LLM_TIMEOUT`。
- **未配置 `LLM_API_KEY` 时**：系统使用**规则规划**（基于模块/关键词/画像的确定性规则），**不得宣称调用了 AI/LLM**；演示话术应为「规则规划」。
- 配置了可用密钥与服务时，才可展示 AI 自然语言规划/判定；请在演示前用一次真实请求确认服务可达，未验证则不宣称 AI 可用。

---

## 6. 实测记录（演示库初始化 + 历史库只读）

见 `docs/verification/tasks/T-27/`：
- `demo-init-20261113.log`：干净临时目录中等价执行脚本逻辑，空库 `alembic upgrade head` → `004_task_deleted_at (head)`（001→004）成功，结构与 `app.models` 指纹一致；历史库 SHA-256 前后一致。
- `result.md`：脚本用法、文档清单、逐条 DoD 与未核验项。

历史库 SHA-256 基线（演示前后应一致）：
`2f919b0544e37618628ac358f1b5684ee16c9253596483b62919166a91b1a789`
（`test-platform/backend/test_platform.db`，1060864 字节）

---

## 7. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 启动报 `SchemaMismatchError`（历史库结构漂移） | 说明误把 `DATABASE_URL` 指向了历史库。演示请用启动脚本（固定 `./demo.db`）；**不要**对历史库 stamp/升级/降级。 |
| 启动报 `SECRET_KEY` 强度不足 | 按第 2.3 节提供 ≥32 字符随机密钥，或写入 `backend/.env`。 |
| 启动报工具清单校验失败 | 请确认在 `test-platform/` 下运行脚本（`TEST_TOOLS_PATH=../test-tools` 相对 `backend/` 解析）；不要删改 `test-tools` 下已声明文件。 |
| 端口占用 | 用 `--port/-Port` 指定其它端口。 |
| 想重置演示数据 | 停服务后删 `backend/demo.db` 与 `backend/storage/demo/`，重新启动。 |
