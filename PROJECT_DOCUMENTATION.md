# AI 测试自动化平台 - 项目开发文档

**文档版本**: v2.3  
**最后更新**: 2026-07-20  

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [目录结构](#3-目录结构)
4. [开发环境搭建](#4-开发环境搭建)
5. [核心模块说明](#5-核心模块说明)
6. [接口规范](#6-接口规范)
7. [测试工具管理](#7-测试工具管理)
8. [AI 任务使用](#8-ai-任务使用)
9. [报告导出](#9-报告导出)
10. [部署说明](#10-部署说明)
11. [版本历史](#11-版本历史)

---

## 1. 项目概述

### 1.1 项目背景

面向 Android 硬件板卡（如 rk3568、A133P 等）的 AI 测试自动化平台。接入 ADB 设备后，平台可通过自然语言或手动方式创建测试任务，自动执行 DDR、EMMC、WIFI、蓝牙、以太网、CPU 等通用基础用例，并生成可导出的测试报告。

### 1.2 核心目标

- 支持不同 Android 版本、不同 CPU 架构、不同 DDR/EMMC/WIFI/蓝牙模组的硬件板卡测试。
- 通过自然语言指令快速创建测试任务（AI 入口）。
- 自动判定测试结果：规则断言 + Rubrics 评分 + AI 兜底。
- 沉淀测试经验：失败模式库、统计基线、黄金案例。
- 支持单任务 / 批量 / 全部任务的报告导出（JSON / Excel / HTML / Markdown / Word）。

### 1.3 术语定义

| 术语 | 定义 |
|------|------|
| **测试模块** | 测试任务的分类单元，如 DDR、EMMC、WIFI、蓝牙、以太网、CPU |
| **测试项** | 具体的测试执行单元，包含执行命令、参数、判定规则 |
| **测试任务** | 一次测试执行的实例，包含选中的测试项列表和目标设备 |
| **测试记录** | 单个测试项的执行结果、日志和提取数据 |
| **执行引擎** | 负责实际执行测试命令的核心组件 |
| **测试工具** | 需要推送到设备或 PC 端调用的二进制文件 / 脚本 |
| **硬件画像** | 设备的型号、Android 版本、CPU、DDR、EMMC、WIFI/蓝牙芯片等信息 |

---

## 2. 系统架构

### 2.1 技术栈选型

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 前端 | Vue 3 + Element Plus + Pinia | 响应式 UI（当前主要完成后端 API） |
| 后端 | FastAPI (Python 3.12+) | 异步 Web 框架 |
| 数据库 | SQLite + SQLAlchemy 2.0 | 开发测试环境，可迁移到 PostgreSQL |
| ADB | 系统 adb 命令 | 需提前安装并加入 PATH |
| 进度推送 | WebSocket | 任务执行实时进度 |
| 任务执行 | asyncio.create_task | 后台异步执行 |
| 报告导出 | openpyxl / python-docx / jinja2 | Excel / Word / HTML / Markdown |

### 2.2 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        客户端层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Web 浏览器  │  │  API 调用端  │  │  前端开发界面 │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                        API 网关层                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              FastAPI Application                      │  │
│  │  ├─ CORS 中间件                                       │  │
│  │  ├─ 全局异常处理                                      │  │
│  │  └─ 路由依赖注入鉴权 (get_current_user / admin)        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                        业务服务层                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │  用户服务    │ │  设备服务    │ │    测试编排服务      │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │  任务服务    │ │  报告服务    │ │    记忆体服务        │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │  知识库服务  │ │  工具管理服务│ │    任务调度器        │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              AI 服务 (自然语言/判定)                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                        核心引擎层                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              测试执行引擎 (ExecutionEngine)            │  │
│  │  ├─ ADB Shell 执行器                                   │  │
│  │  ├─ 推送执行器 (Push & Execute)                        │  │
│  │  ├─ 本地执行器 (Host Execution)                        │  │
│  │  └─ 结果判定引擎 (JudgementEngine)                     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                        数据存储层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   SQLite     │  │   WebSocket  │  │   文件系统    │       │
│  │  (业务数据)   │  │  (实时进度)   │  │  (工具/报告)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 目录结构

```
D:/MCTEST/
├── AGENTS.md                          # AI Agent 开发规范
├── PROJECT_DOCUMENTATION.md           # 项目架构、接口、部署说明
├── DEVELOPMENT_WORKFLOW.md            # 标准开发任务流程
├── 测试平台开发需求文档.md             # 历史需求文档（v1.0）
│
├── test-platform/
│   ├── backend/                       # 后端服务
│   │   ├── app/
│   │   │   ├── api/                   # API 路由
│   │   │   ├── models/                # 数据库模型
│   │   │   ├── services/              # 业务服务
│   │   │   ├── schemas.py             # Pydantic 模型
│   │   │   ├── config.py              # 配置
│   │   │   ├── database.py            # 数据库连接
│   │   │   ├── websocket.py           # WebSocket
│   │   │   ├── seed_data.py           # 默认数据
│   │   │   └── main.py                # 应用入口
│   │   ├── storage/                   # 文件存储
│   │   │   ├── tools/                 # push_exec 工具
│   │   │   ├── logs/                  # 测试执行日志（task_{id}/record_{id}.log）
│   │   │   └── reports/               # 生成报告
│   │   ├── app/storage/knowledge/     # 知识库上传的原始文档
│   │   ├── requirements.txt
│   │   ├── start.py                     # 启动脚本
│   │   └── README.md
│   │
│   ├── frontend/                      # 前端项目
│   │   ├── src/
│   │   ├── package.json
│   │   └── README.md
│   │
│   ├── test-tools/                    # 项目级测试工具目录
│   │   ├── README.md
│   │   ├── common/                    # 通用基础设施（复用）
│   │   │   ├── adb_runner.py
│   │   │   ├── device_info.py
│   │   │   └── logger.py
│   │   │
│   │   ├── ddr/
│   │   │   └── binaries/
│   │   │       └── armeabi-v7a/
│   │   │           ├── memtester
│   │   │           ├── stress-ng
│   │   │           └── stressapptest
│   │   │
│   │   └── emmc/
│   │       ├── README.md
│   │       ├── binaries/
│   │       │   ├── arm64-v8a/
│   │       │   │   ├── fio
│   │       │   │   └── mmc_utils
│   │       │   └── armeabi-v7a/
│   │       │       ├── fio
│   │       │       └── mmc_utils
│   │       └── host/
│   │           ├── emmc_tester.py
│   │           ├── emmc_extcsd_runner.py
│   │           ├── emmc_fio_runner.py
│   │           └── emmc_report.py
```

---

## 4. 开发环境搭建

### 4.1 前置依赖

- Python 3.12+
- ADB 工具（`adb` 命令可执行，已加入系统 PATH）
- 真实 Android 设备或模拟器（用于测试）

### 4.2 后端启动

```bash
cd test-platform/backend
pip install -r requirements.txt

# 首次运行需配置 SECRET_KEY（参考 .env.example），然后启动服务
python start.py
```

服务启动后：
- API 地址：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 默认不自动创建用户，第一个通过 `/auth/register` 注册的用户自动成为 `admin`。
- 为 E2E 测试准备固定管理员可执行：`python scripts/ensure_e2e_admin.py`（账号：`e2e-admin / e2e-admin-pass`）。

### 4.3 前端启动

```bash
cd test-platform/frontend
npm install
npm run dev
```

前端地址：http://localhost:3000（或 Vite 实际分配的端口）

### 4.4 测试

#### 后端测试

```bash
cd test-platform/backend
python -m pytest tests/ -v
```

覆盖范围（当前 166 个用例全绿）：
- **单元测试**：认证服务、执行引擎、判定引擎（规则断言 / Rubrics / AI fallback 无 Key 降级）、参数渲染、记忆体、任务执行器（设备锁 / 重复启动）、任务调度器、设备心跳、执行杀进程、日志流、启动恢复、知识库转换。
- **集成测试**：认证、设备、模块、任务、报告（含统计端点）、用户、AI 任务、知识库、工具上传边界（空文件 / 正常文件 / 权限）、WebSocket 连接与鉴权。
- **端到端测试**：完整任务创建 → 执行 → 报告导出流程。

#### 前端 E2E 测试

```bash
cd test-platform/frontend
npx playwright install chromium   # 首次安装浏览器
npm run test:e2e                  # 运行全部 E2E 测试
```

覆盖范围：登录态初始化、仪表盘 / 设备 / 模块 / 任务 / 报告 / 用户管理导航、创建任务页模块选择与设备选择、报告列表时间显示。

---

## 5. 核心模块说明

### 5.1 用户管理

- 注册 / 登录使用 JWT Token，Token 有效期 24 小时。
- 角色分为 `admin` 和 `user`。
- 普通用户只能看到本机 PC 标识符下的设备，管理员可查看所有设备。

### 5.2 设备管理

- `POST /api/v1/devices/refresh`：扫描 ADB 设备并同步到数据库。
- 设备发现时会自动采集硬件画像：
  - 基础信息：型号、品牌、Android 版本、SDK、CPU 架构、分辨率
  - 硬件画像：主板、DDR 信息、EMMC 信息、WIFI/蓝牙芯片、以太网接口、能力特征
- **心跳监控**：后台心跳循环（`HEARTBEAT_INTERVAL`，默认 30 秒）周期性探活，自动将设备标记为 online / offline。
- **设备锁（DeviceLock）**：同一设备上的任务按 FIFO 排队执行，pending 任务可取消；避免同一设备并发执行冲突。
- **测试项间探活**：连续执行测试项之间做 8 秒快速探活，设备掉线时快速失败而非等到超时。

### 5.3 测试编排

- 默认预置 6 个模块：DDR、EMMC、WIFI、蓝牙、以太网、CPU。
- 每个模块包含若干测试项，支持 `adb_shell` / `push_exec` / `host_exec` 三种执行类型。
- 测试项可配置：执行命令、参数、兼容性、判定规则、超时时间。

### 5.4 执行引擎

| 引擎 | 适用场景 |
|------|---------|
| `adb_shell` | 直接执行设备原生命令，如 `dumpsys wifi` |
| `push_exec` | 推送二进制工具到设备后执行，如 memtester |
| `host_exec` | 在 PC 端执行脚本，适用于 fio、mmc_utils 等需要 PC 端调度的工具 |

执行可靠性：

- **超时控制**：超过测试项 `timeout` 即终止底层 adb / 本地子进程，记录 `timeout` 状态（区别于 fail）。
- **任务取消**：取消任务会真正杀掉正在运行的 adb / 本地子进程，不会残留。
- **断点恢复**：服务启动时自动恢复被中断的任务状态（running → 标记中断，pending 重新可调度）。
- **自动重试**：测试项配置 `retry_count` 时失败自动重试，重试输出带 `=== 重试 N/M ===` 标记。
- **数据库并发**：SQLite 开启 WAL 模式，支撑多设备并行写与 WebSocket 查询并发。

### 5.5 判定引擎

三层判定机制：

1. **规则断言**：通过 `conditional_rules` 对输出中的数值进行条件判断。
2. **Rubrics 评分**：通过 `rubric_criteria` 按阈值评分，最终转换为 pass/fail。
3. **AI 兜底**：当规则无法判定或配置为 `ai_fallback` 时，调用 LLM 进行判定（需配置 API Key）。

### 5.6 AI 任务入口

- `POST /api/v1/ai/tasks/natural`
- 请求示例：`{"text": "对 rk3568 设备做 DDR 稳定性测试"}`
- 系统自动识别目标设备、测试模块、测试类型，并创建任务开始执行。

### 5.7 记忆体

- **失败模式库**：任务失败时自动匹配失败模式，累计出现次数。
- **统计基线**：通过的测试记录中的数值指标会自动聚合为基线。
- **黄金案例**：通过的测试记录会自动沉淀为设备型号 + 测试项的黄金案例。

### 5.8 报告管理

- 单任务报告：`GET /api/v1/reports/{task_id}`
- 批量导出：`GET /api/v1/reports/batch/export?task_ids=1,2,3&format=excel`
- 全部任务总报告：`GET /api/v1/reports/summary/all`
- 支持格式：`json`、`html`、`markdown`、`excel`、`word`
- **任务结果语义**：任务完成后写入 `result` 字段（`passed` / `failed`），由测试记录状态聚合得出。
- **统计分析**：
  - `GET /api/v1/reports/stats/trend?days=N`：近 N 天任务通过/失败趋势，前端仪表盘用 echarts 趋势图展示。
  - `GET /api/v1/reports/stats/by-module`：按测试模块统计通过率。

### 5.9 任务调度与重跑

- **调度类型**（`schedule_type`）：
  - `immediate`：创建后立即执行（默认）。
  - `once`：按 `scheduled_time`（`YYYY-MM-DD HH:MM`，服务器本地时间）一次性触发。
  - `daily`：按 `scheduled_time`（`HH:MM`，服务器本地时间）每日定时触发。
- 创建任务时由调度器计算 `next_run_at`（UTC），后台调度循环（`SCHEDULER_INTERVAL`，默认 30 秒）扫描到期任务并启动。
- **失败重跑**：`POST /api/v1/tasks/{id}/rerun-failed` 基于原任务创建仅含失败测试项的新任务。
- 老库结构升级统一走 alembic 迁移：在 `backend/` 目录执行 `alembic upgrade head`（全新库 create_all 后 `alembic stamp head`）。

### 5.10 执行日志

- 测试项执行的 stdout/stderr 逐行通过 WebSocket 推送（消息格式 `{"type": "log", ...}`）。
- 完整日志实时落盘到 `storage/logs/task_{task_id}/record_{record_id}.log`。
- 数据库 `test_records.output` 仅保留截断后内容（上限 64KB），完整日志以文件为准。
- 下载完整日志：`GET /api/v1/records/{record_id}/log`（FileResponse）。

### 5.11 测试知识库

知识库子系统用于沉淀测试资料（规范、手册、故障案例、测试用例），并为 AI 判定与任务规划提供上下文。前端页面位于 `frontend/src/views/knowledge/`。

- **条目管理**：知识条目 CRUD、分类/标签聚合、草稿/已审核状态流转；条目详情自动累计命中次数。
- **文档上传**：`POST /api/v1/knowledge/upload` 支持 txt / Markdown / PDF / DOCX / XLSX / 图片（≤20MB），自动解析为条目；XLSX 测试用例表格可经 AI 提取为结构化用例。
- **语义搜索**：`POST /api/v1/knowledge/search` 关键词 + 向量相似度混合检索；`POST /api/v1/knowledge/recommend` 面向 AI 规划的条目推荐。
- **AI 提取与转换**：`POST /{id}/extract` 用 LLM 提取标题/分类/标签/摘要；`POST /{id}/convert/preview` 与 `POST /{id}/convert` 将条目转换为测试模块/测试项/失败模式/基线等实际测试资产（转换为管理员权限）。
- **嵌入管理**：`POST /{id}/embed` 重新生成向量（需配置嵌入模型，未配置时检索降级为关键词匹配）。

知识库相关服务（`app/services/knowledge_*.py`）：

| 服务 | 职责 |
|------|------|
| `knowledge_parser` | 解析上传文档（txt/md/pdf/docx/xlsx/图片 OCR 兜底）为纯文本并分片 |
| `knowledge_embedder` | 生成、缓存文本嵌入向量，提供余弦相似度计算 |
| `knowledge_search` | 关键词过滤 + 向量相似度的混合语义搜索 |
| `knowledge_extractor` | 用 LLM 从文档提取标题、分类、标签、摘要、关联测试项 |
| `knowledge_converter` | 将知识条目转换为测试模块/测试项/失败模式/基线等测试资产 |
| `knowledge_judge_context` | 为 AI 判定组装相关规则、基线、黄金案例、失败模式上下文 |
| `knowledge_matcher` | 按设备硬件画像匹配推荐相关知识条目 |
| `knowledge_feedback` | 测试执行反哺知识库：更新条目命中/通过/失败统计 |

### 5.12 测试工具管理 API

除本地 `test-tools/` 目录外，平台提供工具管理接口（`app/api/tools.py`），上传的工具存入 `storage/tools/` 并登记到 `test_tools` 表，供 `push_exec` 类型测试项通过 `tool_id` 引用：

- `GET /api/v1/tools`：工具列表（可按 `architecture` 过滤）。
- `GET /api/v1/tools/{id}`：工具详情。
- `POST /api/v1/tools`：上传工具文件（管理员，自动计算 MD5 与文件大小）。
- `DELETE /api/v1/tools/{id}`：删除工具（管理员，同时删除物理文件）。

---

## 6. 接口规范

### 6.1 通用响应格式

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

### 6.2 认证方式

所有需要认证的接口在 Header 中携带：

```http
Authorization: Bearer <access_token>
```

### 6.3 主要接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/register | 用户注册 |
| POST | /api/v1/auth/login | 用户登录 |
| GET | /api/v1/devices | 设备列表 |
| POST | /api/v1/devices/refresh | 刷新 ADB 设备 |
| GET | /api/v1/modules | 测试模块列表 |
| POST | /api/v1/tasks | 创建测试任务（支持 `schedule_type` / `scheduled_time` 调度字段） |
| GET | /api/v1/tasks | 任务列表 |
| GET | /api/v1/tasks/{id} | 任务详情 |
| POST | /api/v1/tasks/{id}/cancel | 取消任务（杀正在执行的子进程） |
| POST | /api/v1/tasks/{id}/rerun-failed | 失败测试项重跑（生成新任务） |
| GET | /api/v1/records/{id}/log | 下载测试记录完整日志文件 |
| POST | /api/v1/ai/tasks/natural | 自然语言创建 AI 任务 |
| GET | /api/v1/reports/{task_id} | 单任务报告 |
| GET | /api/v1/reports/{task_id}/export | 导出单任务报告 |
| GET | /api/v1/reports/batch/export | 批量导出报告 |
| GET | /api/v1/reports/summary/all | 全部任务总报告 |
| GET | /api/v1/reports/stats/trend?days=N | 近 N 天通过/失败趋势 |
| GET | /api/v1/reports/stats/by-module | 按模块统计通过率 |
| GET | /api/v1/memory/failure-patterns | 失败模式库 |
| GET | /api/v1/memory/baselines | 统计基线 |
| GET | /api/v1/memory/golden-cases | 黄金案例 |
| GET | /api/v1/tools | 测试工具列表 |
| POST | /api/v1/tools | 上传测试工具（管理员） |
| DELETE | /api/v1/tools/{id} | 删除测试工具（管理员） |
| GET | /api/v1/knowledge | 知识库条目列表（分页/过滤） |
| POST | /api/v1/knowledge | 创建知识库条目 |
| PUT/DELETE | /api/v1/knowledge/{id} | 更新/删除知识库条目（删除为管理员） |
| POST | /api/v1/knowledge/upload | 上传文档自动解析为条目 |
| POST | /api/v1/knowledge/search | 语义/混合搜索 |
| POST | /api/v1/knowledge/recommend | AI 规划辅助推荐 |
| POST | /api/v1/knowledge/{id}/embed | 重新生成嵌入向量 |
| POST | /api/v1/knowledge/{id}/extract | AI 提取条目信息 |
| POST | /api/v1/knowledge/{id}/convert/preview | 预览转换为测试资产 |
| POST | /api/v1/knowledge/{id}/convert | 转换为测试资产（管理员） |

---

## 7. 测试工具管理

### 7.1 目录规范

所有测试工具统一存放在 `test-platform/test-tools/` 下，按模块分类，并复用通用基础设施：

```
test-tools/
├── README.md                # 工具目录说明与使用方式
├── common/                  # 通用基础设施（各模块复用）
│   ├── adb_runner.py        # 统一 ADB 命令执行器
│   ├── device_info.py       # 设备架构 / 节点 / 工具路径解析
│   └── logger.py            # 统一日志配置
├── <module>/                # 按硬件模块划分，如 ddr、emmc、wifi_bt、ethernet
│   ├── binaries/<arch>/     # 设备端可执行二进制
│   └── host/                # PC 端运行器 / 报告脚本
```

`<arch>` 目前支持：
- `arm64-v8a`：64 位 ARM 设备
- `armeabi-v7a`：32 位 ARM 设备

### 7.2 当前已集成的工具

| 模块 | 工具 | 架构 | 用途 |
|------|------|------|------|
| DDR | memtester | armeabi-v7a | 内存压力测试 |
| DDR | stress-ng | armeabi-v7a | 通用压力测试 |
| DDR | stressapptest | armeabi-v7a | 内存/CPU 压力测试 |
| EMMC | fio | arm64-v8a / armeabi-v7a | 存储性能测试 |
| EMMC | mmc_utils | arm64-v8a / armeabi-v7a | eMMC EXT_CSD 读取 |

### 7.3 添加新工具流程

1. 将二进制文件放入对应模块的 `binaries/<arch>/` 目录。
2. 如需 PC 端调度，编写 `host/<tool>_runner.py` 脚本。
3. 在 `backend/app/seed_data.py` 中新增或更新测试项模板。
4. 删除旧数据库或手动更新 `test_items` 表，使新模板生效。
5. 重启后端服务。

---

## 8. AI 任务使用

### 8.1 自然语言创建任务

```bash
curl -X POST http://localhost:8000/api/v1/ai/tasks/natural \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text": "对 rk3568 设备做 DDR 稳定性测试"}'
```

### 8.2 支持的模块关键词

| 模块 | 关键词 |
|------|--------|
| DDR | ddr、内存、ram、memory |
| EMMC | emmc、存储、flash、disk、硬盘 |
| WIFI | wifi、wi-fi、无线 |
| 蓝牙 | 蓝牙、bt、bluetooth |
| 以太网 | 以太网、eth、有线、ethernet |
| CPU | cpu、处理器、processor |

### 8.3 支持的测试类型关键词

| 类型 | 关键词 |
|------|--------|
| functional | 功能、基础、常规、开关、状态 |
| performance | 性能、速度、吞吐量、信号、强度、rssi、读写 |
| stability | 稳定性、稳定 |
| stress | 压力、压测、stress |

### 8.4 LLM 配置

在 `backend/.env` 中配置：

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

未配置时，AI 相关功能降级为规则匹配和规则判定。

---

## 9. 报告导出

### 9.1 单任务导出

```bash
curl -O -J "http://localhost:8000/api/v1/reports/9/export?format=excel" \
  -H "Authorization: Bearer <token>"
```

### 9.2 批量导出

```bash
curl -O -J "http://localhost:8000/api/v1/reports/batch/export?task_ids=9,8,7&format=html" \
  -H "Authorization: Bearer <token>"
```

### 9.3 全部任务总报告

```bash
curl "http://localhost:8000/api/v1/reports/summary/all" \
  -H "Authorization: Bearer <token>"
```

> 注：`/reports/summary/all` 默认返回 JSON 汇总。若需导出为 HTML / Excel / Word，可先获取全部任务 ID，再调用 `/reports/batch/export?task_ids=1,2,3&format=html`。

### 9.4 导出格式说明

| 格式 | 文件扩展名 | 适用场景 |
|------|-----------|---------|
| JSON | .json | 程序化处理、数据归档 |
| HTML | .html | 浏览器查看、邮件发送 |
| Markdown | .md | 文档集成、Git 展示 |
| Excel | .xlsx | 数据分析、表格查看 |
| Word | .docx | 正式交付文档 |

---

## 10. 部署说明

### 10.1 Windows 本地部署

```bash
cd test-platform/backend
pip install -r requirements.txt
python start.py
```

或使用 nohup 常驻运行：

```bash
nohup python start.py > server.log 2>&1 &
```

### 10.2 Docker 部署

提供 `test-platform/Dockerfile`、`docker-compose.yml` 与 `.dockerignore`，支持一键容器化部署；数据库备份脚本为 `test-platform/scripts/backup_db.py`。完整步骤（数据迁移、SECRET_KEY 配置、备份策略）见 **`test-platform/DEPLOYMENT.md`**。

### 10.3 生产环境建议

- 数据库：当前为 SQLite（已开启 WAL），高并发场景可迁移到 PostgreSQL。
- 任务队列：当前使用 asyncio 后台任务 + 内置调度循环，**未使用 Celery / Redis**；更高并发需求可作为未来可选项接入。
- 静态文件：使用 Nginx 反向代理。
- 日志：后端已通过 `app/logging_config.py` 配置日志轮转。

---

## 11. 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2024-XX-XX | 初始需求文档 |
| v2.0 | 2026-07-13 | 完成 Phase 1-4：执行引擎、设备画像、AI 入口、记忆体、报告导出增强 |
| v2.1 | 2026-07-13 | 修复测试项管理页面（列表为空、添加按钮失效）、拆解 EMMC 工具目录、新增工具 API 与通用 common 模块、完善开发流程文档 |
| v2.2 | 2026-07-14 | 建立完整测试体系：后端单元/集成/WebSocket/边界测试、前端 Playwright E2E（登录、导航、任务创建、报告时间）、修复 UI 与时间显示 bug、更新测试文档 |
| v2.3 | 2026-07-20 | 文档与实现对齐：补充测试知识库子系统、工具管理 API；新增任务调度（immediate/once/daily）、失败重跑、设备锁排队、设备心跳、执行日志流与日志下载、统计端点（trend/by-module）、任务 result 语义；架构图修正为依赖注入鉴权；明确未使用 Celery/Redis；部署章节指向 test-platform/DEPLOYMENT.md |

---

**维护人员**: AI 测试平台开发团队  
**联系方式**: （待补充）
