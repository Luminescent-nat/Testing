# T-17 干净镜像包含声明工具与启动清单校验 — 结果记录

- 任务编号：T-17（共享任务板 task-6，owner=infra-tools）
- 执行人：infra-tools（Agent Team）
- 日期：2026-11-12（Asia/Shanghai，UTC+08:00）
- 设计依据：`docs/design/scheduler-and-data.md` 第 6 节「干净部署契约」

## 1. 变更文件

| 文件 | 变更 |
|---|---|
| `test-platform/Dockerfile` | 构建上下文（test-platform/）新增 `COPY test-tools/ ./test-tools/`（manifest + runner + 各架构二进制进镜像）；ENV 新增 `TEST_TOOLS_PATH="/app/test-tools"`，与已有 `STATIC_PATH="/app/static"`、`WORKDIR /app` 对齐 |
| `test-platform/.dockerignore` | 移除 `test-tools/` 排除行（`__pycache__`/`*.pyc` 仍由全局规则排除；二进制保留） |
| `test-platform/backend/app/services/tool_manifest.py` | 新增：只读解析 `TEST_TOOLS_PATH/*/manifest.yaml`，提取声明工具（host_exec 的 `{host_tool_dir}/<rel>` runner → 必需；`binaries/<arch>/` 设备二进制 → 必需；`.apk` 等测试资源 → 可选，缺失记 skip 不伪造）。`validate_tools()` / `assert_required_tools()` / `ToolManifestError`，缺失清单必须指出 manifest 路径；拒绝越目录引用 |
| `test-platform/backend/scripts/check_image_tools.py` | 新增：Dockerfile/.dockerignore 静态核对 + manifest 工具发现 + docker 可用性探测（无 docker 明确输出「无法核验」），支持 `--report` JSON |
| `test-platform/backend/tests/unit/test_tool_manifest.py` | 新增 7 用例（先红后绿）：必需 runner/二进制存在、缺失必需工具→失败且指出 manifest 路径、缺失 APK→skip 不阻断、`extra_required` 注入缺失二进制→失败、无 manifest 仅告警、根目录不存在→失败、真实仓库 test-tools 一致性 |
| `test-platform/backend/app/main.py` | lifespan 接入 `validate_startup_config()`（T-17 工具清单校验 + T-18 密钥校验，一次原子修改；T-01 的 errors 区块未触碰） |

未触碰：`frontend/`、`judgement_engine/execution_engine/task_executor`、`test-tools/`（manifest 与脚本行为未改）。

## 2. 环境

- Windows 10（主机 MCTECH）；Python 3.12.10（venv）
- **docker 不可用**：`Get-Command docker` 为空（`Get-Command docker` exit 1，无输出）→ 干净镜像构建/容器启动**无法核验**（详见第 6 节）
- pytest 7.4.4 / pytest-asyncio 0.23.3；SQLAlchemy 2.0.25

## 3. 命令、起止时间与退出码

| # | 命令（WORKDIR） | 起 | 止 | 退出码 | 结果 |
|---|---|---|---|---|---|
| 1 | `python -m pytest tests/unit/test_tool_manifest.py -q`（backend，实现前红测） | 12:06:10 | 12:06:11 | 2 | 收集错误：`No module named 'app.services.tool_manifest'` |
| 2 | `python scripts/check_image_tools.py --report ../docs/verification/tasks/T-17/image-tools-summary.json`（backend） | 12:12:21 | 12:12:21 | 0 | 静态核对 10/10 PASS；docker 不可用明确「无法核验」 |
| 3 | `python -m pytest tests/unit/test_tool_manifest.py -q`（backend，实现后绿测） | 12:16+ | 12:16+ | 0 | 7 passed |
| 4 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`（backend，全量回归） | 12:16:33 | 12:18:46 | 0 | **310 passed**（0 failed，无删除/跳过/放宽） |

## 4. 原始日志与产物

- `docs/verification/tasks/T-17/pytest-T17-red-20261112.log`
- `docs/verification/tasks/T-17/check-image-tools-20261112.log`（含全部静态核对项、manifest 清单、工具发现 22 必需/1 skip、docker 不可用说明）
- `docs/verification/tasks/T-17/image-tools-summary.json`（机器可读，`docker_available=false`）
- `docs/verification/tasks/T-17/pytest-T17-green-20261112.log`
- `docs/verification/tasks/T-17/regression-full-20261112.log`

check_image_tools.py 关键原始输出：
```
[PASS] COPY test-tools/ 进镜像  (COPY test-tools/)
[PASS] TEST_TOOLS_PATH=/app/test-tools
[PASS] STATIC_PATH=/app/static
[PASS] WORKDIR /app（与 TEST_TOOLS_PATH/STATIC_PATH 对齐）
[PASS] .dockerignore 不排除 test-tools/  (bad=[])
[PASS] 发现 manifest  ([...\emmc\manifest.yaml, ...\upfm\manifest.yaml])
[PASS] 必需工具齐备  (missing=[])
[PASS] skip（不伪造）: upfm/assets/test_app.apk  (可选测试资源缺失，按 R3 记 skip（不伪造已就绪）)
[docker] 无法核验：当前主机无 docker 命令（Get-Command docker 为空），干净镜像构建（docker build）、
         容器启动与镜像内工具发现未执行；本脚本仅完成 Dockerfile/.dockerignore 静态核对与 host 侧 manifest 工具发现。
[docker] 明确结论：镜像内实际构建/启动核验 = 无法核验（不伪造通过）
RESULT: PASS(static) (10/10)
docker build/start verification: UNVERIFIABLE (no docker)
```

启动校验真实触发证据（来自 T-18 启动矩阵，非 docker）：
`app.services.tool_manifest: 工具清单校验: root=...\test-tools manifests=2 必需工具=22 缺失=0 skip=1 ok=True`，
以及 `工具清单 skip: upfm/assets/test_app.apk（可选测试资源缺失，按 R3 记 skip（不伪造已就绪））`。

## 5. DoD 逐条

| DoD | 状态 | 证据 |
|---|---|---|
| Dockerfile 构建上下文/镜像包含 manifest 声明的 test-tools（runner+各架构二进制） | ✅（静态核对） | `COPY test-tools/` + `.dockerignore` 放开；22 个必需工具（host runner + emmc 4 个 + ddr 3 个二进制）host 侧发现齐备 |
| 修正 TEST_TOOLS_PATH/STATIC_PATH 与镜像内路径 | ✅ | ENV `TEST_TOOLS_PATH="/app/test-tools"`、`STATIC_PATH="/app/static"`、`WORKDIR /app` |
| 启动时只读工具清单校验（缺失必需工具→启动失败并指出 manifest 路径） | ✅ | `tool_manifest.assert_required_tools()` 接入 lifespan；单测覆盖缺失→`ToolManifestError` 含 manifest 路径 |
| 范围内 APK/外设缺失如实 skip，不伪造 | ✅ | `upfm/assets/test_app.apk` 缺失 → skip 日志+JSON，不阻断、不伪造 |
| 干净构建/启动验证 | ⚠️ **无法核验** | 主机无 docker 命令；已明确记录原因，未伪造通过（见第 6 节） |
| 证据目录 `docs/verification/tasks/T-17/` | ✅ | 本目录 |
| 禁止改 frontend、judgement_engine、test-tools 行为 | ✅ 未改 | 见第 1 节 |

## 6. 无法核验项（如实记录）

1. **`docker build` 干净构建：无法核验**——主机未安装 docker（`Get-Command docker` 为空）。未执行镜像构建，未验证镜像内 `/app/test-tools` 实际内容、容器内工具发现与启动。补偿措施：`check_image_tools.py` 完成 Dockerfile/`.dockerignore` 静态核对 + host 侧 manifest 工具发现（全部通过），但**不等于镜像核验**。
2. **容器内启动链路（uvicorn + lifespan 工具清单校验）**：无法核验（同上）。host 侧等效验证已做：真实 uvicorn 启动（T-18 启动矩阵）中 lifespan 工具清单校验真实执行并打印 22 必需/1 skip（见 `T-18/startup-matrix-20261112.log`）。
3. **多架构二进制在容器内的可用性**（如 Alpine adb 与 armeabi 二进制推送）：无法核验。
4. **干净空库首次启动**：host 侧已验证可通过（`fresh-empty-db` /health=200，见 T-18 矩阵与 T-02 增补记录的 seed_data 修复）；容器内等价场景仍无法核验。

## 7. 发现与联动修复（T-02 引入，已修）

T-18 启动矩阵在 fresh 空库场景暴露真实回归：`PRAGMA foreign_keys=ON` 后，`app/seed_data.py` 在无用户时使用虚构 `created_by=1`，干净库首次启动直接 `FOREIGN KEY constraint failed` 崩溃（影响 Docker 空数据卷部署）。经 lead 授权（task-3 rev6 加入 seed_data.py scope）已修：`user_id = user.id if user else None`（created_by 可空），并新增回归测试 `test_clean_empty_db_startup_seeding_survives_foreign_keys_on`。详见 T-02 增补记录。

## 8. 回退说明

1. `Dockerfile`：删除 `COPY test-tools/ ./test-tools/` 块与 ENV 中 `TEST_TOOLS_PATH` 行。
2. `.dockerignore`：恢复 `test-tools/` 排除行。
3. 删除 `app/services/tool_manifest.py`、`backend/scripts/check_image_tools.py`、`tests/unit/test_tool_manifest.py`、`docs/verification/tasks/T-17/`。
4. `app/main.py`：lifespan 中的 `validate_startup_config()` 恢复为原 `if not settings.SECRET_KEY: raise RuntimeError(...)`（T-18 回退需一并处理，二者共用该函数）。
5. 本次未 git commit；回退需手工反向编辑或经 Lead 确认后 `git restore`。
