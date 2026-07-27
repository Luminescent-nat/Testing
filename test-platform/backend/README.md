# 测试平台后端

基于 FastAPI 的 Android 设备 AI 测试自动化平台后端。

## 技术栈

- **框架**: FastAPI (Python 3.12+)
- **数据库**: SQLite + SQLAlchemy 2.0（异步 aiosqlite）；可通过 `DATABASE_URL` 切换为 PostgreSQL
- **ORM**: SQLAlchemy 2.0
- **认证**: JWT Token + bcrypt
- **ADB**: 系统 adb 命令（需提前安装并加入 PATH）
- **进度推送**: WebSocket
- **报告导出**: JSON / Excel / HTML / Markdown / Word

## 项目结构

```
backend/
├── app/
│   ├── api/                 # API 路由
│   │   ├── auth.py          # 认证接口
│   │   ├── users.py         # 用户管理
│   │   ├── devices.py       # 设备管理
│   │   ├── modules.py       # 测试模块/测试项
│   │   ├── tasks.py         # 任务管理（含取消/失败重跑）
│   │   ├── records.py       # 测试记录（日志下载）
│   │   ├── reports.py       # 报告导出与统计
│   │   ├── ai_tasks.py      # AI 自然语言创建任务
│   │   ├── memory.py        # 记忆体（失败模式/基线/黄金案例）
│   │   ├── tools.py         # 测试工具管理
│   │   └── knowledge.py     # 测试知识库
│   ├── services/            # 业务逻辑层
│   │   ├── auth.py          # 认证服务
│   │   ├── device.py        # ADB 与设备服务（心跳/设备锁）
│   │   ├── device_profile.py# 设备画像采集
│   │   ├── execution_engine.py  # 执行引擎
│   │   ├── task_executor.py # 任务执行器
│   │   ├── scheduler.py     # 任务定时/周期调度器
│   │   ├── judgement_engine.py  # 结果判定引擎
│   │   ├── nl_task_planner.py   # 自然语言任务规划
│   │   ├── llm_client.py    # LLM 客户端
│   │   ├── parameter_renderer.py # 参数模板渲染
│   │   ├── memory_engine.py # 记忆体服务
│   │   └── knowledge_*.py   # 知识库服务（解析/嵌入/搜索/提取/转换/匹配/反哺）
│   ├── models/              # 数据库模型
│   ├── schemas.py           # Pydantic 模型
│   ├── config.py            # 配置项
│   ├── database.py          # 数据库连接（SQLite WAL）
│   ├── logging_config.py    # 日志配置（轮转）
│   ├── websocket.py         # WebSocket 进度推送
│   ├── seed_data.py         # 默认数据初始化
│   └── main.py              # 应用入口
├── scripts/                 # 维护脚本（E2E 管理员）
├── alembic/                 # alembic 迁移环境（env.py + versions/ 基线迁移）
├── alembic.ini              # alembic 配置（URL 从 DATABASE_URL 环境变量读取）
├── storage/                 # 文件存储
│   ├── tools/               # push_exec 使用的工具文件
│   ├── logs/                # 测试执行日志（task_{id}/record_{id}.log）
│   └── reports/             # 生成的报告文件
├── test-tools/              # 项目级测试工具目录（与 backend 同级）
│   ├── ddr/                 # DDR 测试工具
│   └── emmc/                # EMMC 测试工具与 PC 端运行器
├── requirements.txt         # 依赖列表
├── start.py                 # 启动脚本（等价于 uvicorn app.main:app）
└── .env.example             # 环境变量示例
```

## 核心功能模块

### 1. 用户管理 (M01)
- 用户注册 / 登录（JWT 认证）
- 角色权限控制（管理员 / 普通用户）
- PC 标识符绑定，设备按 PC 隔离

### 2. 设备管理 (M02)
- ADB 设备自动发现与同步
- 设备硬件画像采集（Android 版本、CPU、DDR、EMMC、WIFI、蓝牙、以太网等）
- 设备状态监控（online / offline / testing）
- 30 秒心跳循环（`HEARTBEAT_INTERVAL`）自动上下线
- 设备锁（DeviceLock）：同一设备任务 FIFO 排队，pending 可取消

### 3. 测试编排 (M04)
- 测试模块 / 测试项 CRUD
- 3 种执行类型：
  - `adb_shell`: ADB Shell 命令执行
  - `push_exec`: 推送二进制后执行
  - `host_exec`: PC 端执行脚本
- 兼容性配置（Android 版本、架构、能力特征、主板平台）
- 结果解析规则（pass_pattern / fail_pattern / extract_pattern）

### 4. 测试执行引擎 (M05)
- 工厂模式匹配执行引擎
- 异步任务执行 + WebSocket 实时进度（stdout/stderr 逐行推送）
- 设备锁机制，防止同一设备并发执行
- 失败跳过 / 停止策略
- 超时/取消真正杀掉 adb 与本地子进程，超时记录 `timeout` 状态
- `retry_count` 自动重试，重试输出带 `=== 重试 N/M ===` 标记
- 执行日志实时落盘 `storage/logs/`，DB output 截断 64KB
- 服务启动时自动恢复中断任务状态

### 4.1 任务调度
- `schedule_type`：`immediate`（默认）/ `once` / `daily`
- `scheduled_time`：服务器本地时间（once: `YYYY-MM-DD HH:MM`；daily: `HH:MM`）
- 调度器按 `SCHEDULER_INTERVAL`（默认 30 秒）循环触发到期任务（`next_run_at`）
- `POST /tasks/{id}/rerun-failed` 失败测试项重跑

### 5. AI 任务入口 (M07)
- 自然语言创建测试任务（例："对 rk3568 做 DDR 稳定性测试"）
- 规则匹配模块 / 测试类型
- LLM 辅助规划与 AI 兜底判定（需配置 API Key）

### 6. 判定引擎 (M08)
- 规则断言（conditional_rules）
- Rubrics 评分
- AI 兜底判定
- ADB 设备异常模式识别

### 7. 记忆体与经验沉淀 (M09)
- 失败模式库：自动归类 ADB/权限/超时/兼容性等失败
- 统计基线：按设备型号 + 测试项聚合指标
- 黄金案例：积累同一型号设备的标准通过输出

### 8. 报告管理 (M06)
- 单任务报告查询（任务含 `result`：passed / failed）
- 批量任务聚合报告
- 全部任务总报告
- 统计分析：`/reports/stats/trend?days=N`、`/reports/stats/by-module`
- 导出格式：JSON / Excel / HTML / Markdown / Word

### 9. 测试工具管理
- 工具上传 / 列表 / 详情 / 删除（上传与删除为管理员权限）
- 上传自动计算 MD5 与文件大小，供 push_exec 测试项按 `tool_id` 引用

### 10. 测试知识库
- 知识条目 CRUD、分类/标签聚合、文档上传自动解析（txt/md/pdf/docx/xlsx/图片）
- 关键词 + 向量混合语义搜索与推荐
- AI 提取条目信息；条目转换为测试模块/测试项/失败模式/基线
- 为 AI 判定提供知识上下文，测试执行反哺条目统计

## 数据库表结构

- **users**: 用户表
- **devices**: 设备表（含硬件画像扩展字段）
- **test_tools**: 测试工具表
- **test_modules**: 测试模块表
- **test_items**: 测试项表
- **test_tasks**: 测试任务表（含 schedule_type / scheduled_time / next_run_at / result）
- **test_records**: 测试记录表
- **failure_patterns**: 失败模式库
- **baselines**: 统计基线表
- **golden_cases**: 黄金案例表
- **knowledge_entries**: 测试知识库条目表

## 快速开始

### 1. 环境准备

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 配置环境变量（SECRET_KEY 必填，未配置应用拒绝启动）
cp .env.example .env
# 生成随机密钥并写入 .env：
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> .env
# 按需编辑 .env 配置 LLM_API_KEY 等
```

### 2. 数据库初始化

启动服务时会自动执行 `init_db()` 和 `seed_default_data()` 创建表并初始化默认数据。默认不自动创建用户，第一个通过 `/auth/register` 注册的用户自动成为 `admin`。如需为 E2E 测试准备固定管理员，可执行：

```bash
python scripts/ensure_e2e_admin.py
```

该脚本会创建/更新 `e2e-admin / e2e-admin-pass` 管理员账号。

对已有老库升级表结构，统一走 alembic 迁移（`alembic/` 目录，`alembic.ini` 为配置）：

```bash
# 存量库升级到最新结构（URL 从环境变量 DATABASE_URL 读取，未设置时用 app 默认）
alembic upgrade head

# 全新库由 create_all 建表后，标记为最新基线，避免 upgrade 重复建表
alembic stamp head

# models 变更后生成新迁移脚本
alembic revision --autogenerate -m "描述变更"
```

历史的手写 `migrate_*.py` 迁移脚本已移除，统一由 alembic 基线（`alembic/versions/`）接管。

### 3. 启动服务

```bash
# 直接启动（建表/种子数据在应用 lifespan 中自动完成）
python start.py

# 或使用 uvicorn（开发可加 --reload）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 访问 API 文档

启动后访问：http://localhost:8000/docs

## API 接口概览

### 认证接口
- `POST /api/v1/auth/register` - 用户注册
- `POST /api/v1/auth/login` - 用户登录

### 设备接口
- `GET /api/v1/devices` - 设备列表
- `POST /api/v1/devices/refresh` - 刷新 ADB 设备
- `GET /api/v1/devices/{serial}` - 设备详情

### 测试编排接口
- `GET /api/v1/modules` - 模块列表
- `POST /api/v1/modules` - 创建模块
- `GET /api/v1/modules/{id}/items` - 测试项列表
- `POST /api/v1/modules/{id}/items` - 创建测试项

### 任务接口
- `POST /api/v1/tasks` - 创建任务（支持 `schedule_type` / `scheduled_time` 调度字段）
- `GET /api/v1/tasks` - 任务列表
- `GET /api/v1/tasks/{id}` - 任务详情
- `POST /api/v1/tasks/{id}/cancel` - 取消任务
- `POST /api/v1/tasks/{id}/rerun-failed` - 失败测试项重跑

### 测试记录接口
- `GET /api/v1/records/{id}/log` - 下载测试记录完整日志文件

### AI 任务接口
- `POST /api/v1/ai/tasks/natural` - 自然语言创建任务

### 报告接口
- `GET /api/v1/reports/{task_id}` - 单任务报告
- `GET /api/v1/reports/{task_id}/export?format=json|html|markdown|excel|word` - 导出单任务报告
- `GET /api/v1/reports/batch/export?task_ids=1,2,3&format=html` - 批量导出
- `GET /api/v1/reports/summary/all` - 全部任务总报告
- `GET /api/v1/reports/stats/trend?days=N` - 近 N 天通过/失败趋势
- `GET /api/v1/reports/stats/by-module` - 按模块统计通过率

### 测试工具接口
- `GET /api/v1/tools` - 工具列表（可按 architecture 过滤）
- `GET /api/v1/tools/{id}` - 工具详情
- `POST /api/v1/tools` - 上传工具（管理员）
- `DELETE /api/v1/tools/{id}` - 删除工具（管理员）

### 知识库接口
- `GET /api/v1/knowledge` - 条目列表（分页/类型/分类/标签/关键词过滤）
- `POST /api/v1/knowledge` - 创建条目
- `GET /api/v1/knowledge/{id}` - 条目详情
- `PUT /api/v1/knowledge/{id}` - 更新条目
- `DELETE /api/v1/knowledge/{id}` - 删除条目（管理员）
- `POST /api/v1/knowledge/upload` - 上传文档自动解析为条目
- `POST /api/v1/knowledge/search` - 语义/混合搜索
- `POST /api/v1/knowledge/recommend` - AI 规划辅助推荐
- `POST /api/v1/knowledge/{id}/embed` - 重新生成嵌入向量
- `POST /api/v1/knowledge/{id}/extract` - AI 提取条目信息
- `POST /api/v1/knowledge/{id}/convert/preview` - 预览转换为测试资产
- `POST /api/v1/knowledge/{id}/convert` - 转换为测试资产（管理员）

### 记忆体接口
- `GET /api/v1/memory/failure-patterns` - 失败模式库
- `GET /api/v1/memory/baselines` - 统计基线
- `GET /api/v1/memory/golden-cases` - 黄金案例

## 执行引擎说明

### 引擎类型

1. **AdbShellEngine**: 执行 `adb shell` 命令
2. **PushExecEngine**: 推送工具到设备后执行
3. **HostExecEngine**: 在 PC 端执行命令（适用于 fio、mmc_utils 等需要 PC 端调度的场景）

### 执行流程

1. 用户创建任务（手动选择或自然语言）
2. 校验设备在线状态并占用设备
3. 按顺序执行测试项
4. 兼容性检查 → 工具推送 → 命令执行 → 结果判定
5. WebSocket 实时推送进度
6. 任务完成后释放设备，沉淀记忆体数据

## 权限控制

- **管理员**: 所有权限
- **普通用户**:
  - 只能看到本机 ADB 设备
  - 只能查看自己的历史记录
  - 可以创建和执行测试任务

## 环境变量

复制 `.env.example` 为 `.env`，可配置：

```env
# 必填：JWT 签名密钥（未配置应用拒绝启动）
SECRET_KEY=请用随机字符串替换

# LLM 配置（可选，未配置时 AI 相关功能降级为规则判定）
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# 应用配置
APP_NAME=Android测试平台
DEBUG=false
```

## 测试

项目已建立完整的 pytest 测试套件（当前 185 个用例全部通过），位于 `tests/` 目录：

```
tests/
├── conftest.py              # 全局 fixture：测试数据库、HTTP 客户端、Mock ADB/LLM
├── unit/                    # 单元测试
│   ├── test_auth_service.py
│   ├── test_execution_engine.py
│   ├── test_judgement_engine.py   # 含 AI fallback 无 Key 降级路径
│   ├── test_memory_engine.py
│   ├── test_parameter_renderer.py
│   ├── test_task_executor.py      # 设备锁与重复启动
│   ├── test_scheduler.py          # 调度器 next_run_at / 到期触发
│   ├── test_device_heartbeat.py   # 心跳自动上下线
│   ├── test_device_exec_kill.py   # 超时/取消杀子进程
│   ├── test_log_stream.py         # 日志逐行流式推送
│   ├── test_startup_recovery.py   # 启动恢复中断状态
│   └── test_knowledge_converter.py# 知识库条目转换
├── integration/             # 接口集成测试
│   ├── test_auth_api.py
│   ├── test_ai_tasks_api.py
│   ├── test_devices_api.py
│   ├── test_knowledge_api.py
│   ├── test_memory_api.py
│   ├── test_modules_api.py
│   ├── test_reports_api.py
│   ├── test_reports_stats_api.py  # 统计端点 trend / by-module
│   ├── test_tasks_api.py
│   ├── test_tools_api.py          # 含空文件/正常文件上传边界
│   ├── test_users_api.py
│   └── test_websocket.py          # WebSocket 连接与鉴权
└── e2e/                     # 端到端完整流程测试
    └── test_full_workflow.py
```

### 运行测试

```bash
# 安装依赖
pip install -r requirements.txt

# 运行全部测试
python -m pytest tests -q

# 运行指定层级
python -m pytest tests/unit
python -m pytest tests/integration
python -m pytest tests/e2e

# 生成覆盖率报告
python -m pytest --cov=app --cov-report=html
```

### 测试说明

- 测试数据库使用临时文件 SQLite，每个测试函数独立隔离。
- ADB 调用默认被 Mock，避免依赖真实 Android 设备或系统 adb。
- 后台任务在 fixture 中自动取消/等待，防止跨用例状态泄漏。
- **WebSocket**: `test_websocket.py` 验证无效 token 断开连接、ping/pong 存活。
- **设备锁与任务执行器**: `test_task_executor.py` 验证设备锁互斥、重复启动拒绝、任务结束后自动清理。
- **判定引擎**: `test_judgement_engine.py` 覆盖规则断言、Rubrics 评分、返回码默认行为，以及未配置 LLM API Key 时 AI fallback 降级为 `unknown`。
- **工具上传边界**: `test_tools_api.py` 覆盖空文件 400、正常文件上传成功、普通用户 403。

## License

MIT
