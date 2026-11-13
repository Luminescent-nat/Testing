# T-27 演示前部署收口：演示 DB 策略 + AI 配置与文档 — 结果记录

- 任务编号：task-31（演示前收口：demo.db/storage 隔离脚本、AI 配置与演示文档）
- 执行人：infra-tools（Agent Team）
- 日期：2026-11-13（Asia/Shanghai，UTC+08:00）
- 关联文档：`docs/DEMO.md`（新）、`test-platform/DEPLOYMENT.md` §6/§7

## 1. 变更文件

| 文件 | 变更 |
|---|---|
| `test-platform/scripts/start_demo.ps1`（新） | Windows 演示启动脚本：显式 `DATABASE_URL=sqlite+aiosqlite:///./demo.db`、`STORAGE_PATH/TOOLS_PATH/REPORTS_PATH/LOGS_PATH=storage/demo/*`、`TEST_TOOLS_PATH=../test-tools`；SECRET_KEY 解析（-SecretKey → DEMO_SECRET_KEY → SECRET_KEY → backend/.env → 临时生成并提示）；创建 storage/demo 目录；`alembic upgrade head`（空库 001→004，幂等）+ `alembic current`；启动 uvicorn。开关：`-Port/-SecretKey/-SkipMigrate/-MigrateOnly`（默认 `./demo.db` 与 `storage/demo`，可用 `-DemoDbPath/-StorageRoot` 覆盖用于隔离实测）。**UTF-8 with BOM**（Windows PowerShell 5.1 按 ANSI 读无 BOM 文件会中文乱码解析失败，实测确认后保留 BOM） |
| `test-platform/scripts/start_demo.sh`（新） | Linux/Git Bash 等价脚本：`--secret-key/--port/--skip-migrate/--migrate-only/--demo-db/--storage-root`；同一套环境变量与 SECRET_KEY 解析；`env_file_key()` 从 backend/.env 提取 |
| `docs/DEMO.md`（新） | 演示 DB 策略（历史库保留/只读/漂移 SchemaMismatchError 属预期/严禁 downgrade base/演示独立 demo.db+storage/demo/需保留历史数据则另立迁移任务）、历史库 SHA-256 只读约束与基线、启动用法、A133P 只读演示清单（201→`cat /proc/meminfo`→completed/passed→报告100%→HTML 导出）、明确不做写入/烧录/重启/压测、daily/once 演示禁用说明（T-11/T-12 未实施，界面已禁用）、AI/LLM 口径（无密钥=规则规划，不得宣称调 AI）、FAQ |
| `test-platform/backend/.env.example` | 新增 AI/LLM 配置块：`LLM_PROVIDER/LLM_API_KEY/LLM_BASE_URL/LLM_MODEL/LLM_TEMPERATURE/LLM_MAX_TOKENS/LLM_TIMEOUT`；注释明确「仅支持 OpenAI-compatible /chat/completions；无 LLM_API_KEY 时使用规则规划，不得宣称调用 AI」 |
| `test-platform/DEPLOYMENT.md` | 新增「§6 AI / LLM 配置」（变量表 + 规则规划口径 + 演示环境指到 docs/DEMO.md）；原 §6 检查清单顺延为 §7，其中 LLM 条目扩为 7 个变量并写明「不配置时使用规则规划、不得宣称调用了 AI」 |
| `docs/verification/tasks/T-27/` | 本记录 + 实测日志（见 §4） |

未触碰：`backend/app`、`frontend`、契约文档；历史库 `backend/test_platform.db` 全程只读（见 §3 哈希一致）。

## 2. 环境

- Windows 10；Windows PowerShell 5.1（实测真实运行脚本的解释器）；WSL Ubuntu-22.04（bash 语法核对）
- Python 3.12.10（`test-platform/.venv`）；alembic head = `004_task_deleted_at`（迁移链 0817df993d8b→002→003→004，即「001→004」）
- 历史库基线：`backend/test_platform.db`，1060864 字节，SHA-256 `2f919b0544e37618628ac358f1b5684ee16c9253596483b62919166a91b1a789`

## 3. 命令、起止时间与退出码（原始日志见 §4）

| # | 命令 | 起 | 止 | 退出码 | 结果 |
|---|---|---|---|---|---|
| 1 | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start_demo.ps1 -MigrateOnly -DemoDbPath <tmp>\demo.db -StorageRoot <tmp>\storage\demo`（干净临时目录） | 14:25:47 | 14:25:49 | 0 | 空库 alembic **001→004** 全链成功（日志逐行 INFO），`alembic current` = `004_task_deleted_at (head)`；历史库 SHA-256 前后一致（`HIST_SHA_UNCHANGED: True`） |
| 2 | 结构指纹核验 `app.database._verify_schema_matches_models('demo-probe')`（等价应用启动校验） | 同上 | 同上 | 0 | demo.db 12 张业务表 + alembic_version，**schema_matches_models: true** |
| 3 | 演示环境启动冒烟（等价 start_demo 环境变量 + uvicorn 临时端口 + /health） | 14:29± | 14:30± | 0 | `/health` → `{"status":"healthy"}`（**HEALTHY=True**）；demo.db 自动迁移到 004、13 张表（含 alembic_version）；工具清单/SECRET_KEY 校验通过 |
| 4 | `wsl -d Ubuntu-22.04 -- bash -n scripts/start_demo.sh` | 14:32± | 14:32± | 0 | sh 语法通过（stdout 无错误输出） |
| 5 | `python -m pytest tests/unit/test_secret_strength.py -q`（.env.example 变更回归） | 14:31± | 14:31± | 0 | 21 passed |
| 6 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`（全量） | 14:29± | 14:33± | 0 | **472 passed / 0 failed** |

## 4. 原始日志与产物（docs/verification/tasks/T-27/）

- `demo-init-20261113.log` — 脚本真实运行（-MigrateOnly）原始输出 + alembic 全链 INFO + `alembic current` + 结构指纹核验 JSON + 历史库 SHA-256 前后值与 `HIST_SHA_UNCHANGED: True`
- `demo-server-smoke-20261113.log` — 演示环境 uvicorn 启动冒烟：`HEALTHY=True`、`HEALTH_BODY={"status":"healthy"}`、demo.db 表清单与 `alembic_version=004_task_deleted_at`、uvicorn stdout/stderr
- `script-syntax-20261113.log` — ps1（PS 5.1 解析 OK + BOM 字节 239,187,191）与 sh（WSL bash -n 退出码 0）
- `pytest-focused-20261113.log` — test_secret_strength 21 passed
- `regression-full-20261113.log` — 全量 472 passed / 0 failed

## 5. DoD 逐条

| DoD | 状态 | 证据 |
|---|---|---|
| scripts/start_demo.ps1 + .sh：显式 DATABASE_URL=sqlite+aiosqlite:///./demo.db、storage/demo/*、SECRET_KEY 从 .env/参数、首跑 alembic upgrade head、历史库提示 | ✅ | 两脚本（§1）；实测 #1（001→004 + current=head） |
| 提示历史 test_platform.db 保留不动（漂移 SchemaMismatchError 属预期，严禁 downgrade base） | ✅ | 脚本头部与运行输出均打印；DEMO.md §1 |
| docs/DEMO.md：演示 DB 策略 + 历史库只读 SHA-256 约束 + A133P 只读演示清单（201→meminfo→completed/passed→报告100%→HTML）+ 不做写入/烧录/重启/压测 | ✅ | docs/DEMO.md §1/§3/§5/§6 |
| daily/once 演示禁用说明（T-11/T-12 未实施，界面已禁用） | ✅ | docs/DEMO.md §4 |
| backend/.env.example 补 7 个 LLM 变量 + 仅支持 OpenAI-compatible /chat/completions、无密钥=规则规划不得宣称调用 AI | ✅ | .env.example 尾部块 |
| DEPLOYMENT.md 同步 | ✅ | §6 AI/LLM 配置 + §7 清单更新 |
| 实测：干净临时目录 demo.db 空库 001→004 成功、历史库 SHA-256 不变 | ✅ | demo-init-20261113.log（含额外结构指纹一致 + /health 冒烟） |

## 6. 未验证项（如实）

1. `start_demo.sh` **未在真实 Linux 主机运行**（仅 WSL Ubuntu-22.04 `bash -n` 语法核对通过；WSL 启动器 stderr 有 localhost/NAT 网络提示，与脚本无关）。逻辑与 .ps1 逐段对应。
2. 演示完整闭环（注册→发现 A133P→创建任务 201→报告→HTML）属演示现场操作，未在本任务执行（A133P 只读清单已写入 DEMO.md；本任务未对设备做任何操作）。
3. demo.db 默认路径（`backend/demo.db`）未在仓库内实际生成——实测均在干净临时目录完成，避免向仓库引入演示数据文件。
4. Docker 部署的演示路径未涉及（主机无 docker）。

## 7. 回退说明

1. 删除 `test-platform/scripts/start_demo.ps1`、`start_demo.sh`、`docs/DEMO.md` 与本目录证据。
2. `backend/.env.example` 移除 LLM 配置块；`DEPLOYMENT.md` 恢复 §6 检查清单（原 LLM 行）并删除 AI/LLM 小节与演示指引。
3. 本任务零应用代码改动，回退不影响任何测试；历史库 `backend/test_platform.db` 未被触碰（SHA-256 基线见 §2）。
