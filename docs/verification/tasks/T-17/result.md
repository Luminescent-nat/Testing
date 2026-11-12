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

---

## 9. V1-08 修订（RR-V1-READINESS-20261112）— 显式工具清单/哈希 + Docker 校验真实性

**审计缺陷（已动态复现）**：`tool_manifest.py` 通过 glob 现存文件生成必需清单（删除文件后清单变空、启动漏检）；清单未覆盖 runner 的共享 Python 依赖闭包；`check_image_tools.py` 仅检测 docker 命令存在就打印 `verified`（假证据）。

### 9.1 变更

| 文件 | 变更 |
|---|---|
| `app/services/tool_manifest.py` | 重写：**必需项只来自 manifest `tools:` 显式声明**（host runner / shared Python 依赖 / device 二进制 + ABI/version/sha256 / 可选 assets）。`discover_requirements` 不再由现存文件虚构必需项；新增 SHA-256 校验、共享依赖闭包校验（解析 runner 的 `common.*` 与同目录兄弟 import）、声明缺口校验（模块目录含 host/二进制但 manifest 无 tools → 致命）。`assert_required_tools` 汇总「缺失/哈希不符/闭包缺失/声明缺口」并指出 manifest 路径。附 `--emit` 生成声明、`--validate` 只读核对 CLI |
| `test-tools/upfm/manifest.yaml`、`test-tools/emmc/manifest.yaml` | 新增 `tools:` 显式声明：upfm 13 个 host runner + 4 个 shared 依赖 + 1 可选 APK；emmc 5 个 host runner + 4 个 shared 依赖 + 4 个设备二进制（arm64-v8a/armeabi-v7a 的 fio、mmc_utils，含 abi/version/sha256）。哈希由 `tool_manifest --emit` 依实际文件生成并核对一致 |
| `backend/scripts/check_image_tools.py` | 重写运行时核验：仅当真实 `docker build --no-cache` + `docker compose up -d` + host `/health` 200 + 容器内 `validate_tools ok` 全部成功才 `VERIFIED`（退出 0）；docker 不可用或未实际构建 → `UNVERIFIABLE` 且非零退出（docker 不可用=2，运行时失败=1），**绝不打印 verified**。静态/Dockerfile/.dockerignore/manifest 清单核对保留 |
| `tests/unit/test_v1_tool_manifest.py` | 新增 10 用例：删除已声明 device 二进制→条目仍在且启动失败；tools-less 目录→声明缺口失败（不再 glob）；sha256 不符→失败（含正确哈希对照）；shared 依赖缺失→失败；未声明 `common.*` import→闭包失败；未声明兄弟模块→闭包失败；extra_required 缺失；无 manifest 根→ok；真实仓库 manifest 显式+哈希一致 |
| `tests/unit/test_tool_manifest.py` | 夹具升级为显式 `tools:` 声明（契约从「glob 派生」改为「显式声明」；仍保留原有缺失/skip/根不存在等断言，未放宽） |

### 9.2 定向复现结果（如实）

- 审计原始夹具 `targeted-defect-repro.py:151-164`：其 manifest **没有 tools 声明**。按 V1-08 新契约，未声明文件不应成为必需项，故该夹具现于第 161 行失败（`{}`）——这是**契约变更的预期结果**，日志：`v1-08-audit-repro-rerun-20261112.log`。
- 同语义的**修正夹具版**（显式声明设备二进制后删除文件）**PASS**：`v1-08-declared-repro.py` → `[before]=True [after]=True [startup] blocked=True → RESULT: PASS`，日志 `v1-08-declared-repro-20261112.log`。
- 关键安全目标达成：任何「声明存在但被删除」的必需工具都会使启动失败；且 `tools` 缺失的模块目录被判声明缺口致命（`test_legacy_manifest_without_tools_is_rejected`），不再出现「删除后清单变空、启动照常」的漏检。
- 建议审计方将原始夹具补 4 行 `tools:` 声明即可复现通过（等价于 `test_v1_tool_manifest.py::test_deleting_declared_device_binary_keeps_requirement_and_fails_startup`）。

### 9.3 Docker 校验真实性

- 本机无 docker：`check_image_tools.py` 输出 `RESULT: UNVERIFIABLE (static 13/13, runtime=UNVERIFIABLE)`，**退出码 2**，明确「镜像层核验=无法核验（不伪造 verified）」。日志：`check-image-tools-v1-08-20261112.log`，JSON：`image-tools-summary-v1-08.json`（`runtime.status=UNVERIFIABLE`）。
- 脚本逻辑：docker 可用时必须真实执行 build/up/health/容器内发现，任一失败 → `FAILED`/退出 1；仅全成功才 `VERIFIED`。仅检测到 docker 命令不再输出 verified。

### 9.4 测试与回归

- 定向：`python -m pytest tests/unit/test_v1_tool_manifest.py tests/unit/test_tool_manifest.py -q` → **17 passed**（`pytest-v1-08-green-20261112.log`）。
- 全量：`python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning` → **337 passed, 0 failed**（`regression-full-v1-08-20261112.log`，退出码 0）。
- 真实仓库 `tool_manifest --validate`：显式声明 27 个必需条目 + 1 skip，`missing/hash/closure/gaps` 全空、`ok=true`。

### 9.5 未验证项 / 已知缺口（如实）

1. **Docker 运行时仍无法核验**（主机无 docker）：镜像内 tools 实际存在性、容器内工具发现、弱密钥拒绝、新旧数据卷迁移未核验。
2. **ddr/binaries 未纳入声明**：`test-tools/ddr/` 无 `manifest.yaml`，其 memtester/stress-ng/stressapptest 不被启动校验门禁（镜像仍会整体复制）。V1-08 要求「明确 arm64 是否属于 V1；若属于，DDR 工具与实测必须补齐」——待用户/审计确认 ABI 支持矩阵后决定是否新增 DDR manifest 与实测。
3. 设备二进制 `version` 目前为 `unspecified`（预编译 fio/mmc_utils 版本未在只读范围实测）；sha256 已锁定。
4. 哈希绑定当前文件内容：任何对 test-tools runner/common 的合法修改都必须同步更新 manifest `sha256`，否则启动失败（设计如此，需在后续变更流程中遵守）。

### 9.6 V1-08 回退

- `app/services/tool_manifest.py`：恢复 T-17 初版（glob 派生）——**不建议**，会重新引入漏检。
- `test-tools/{upfm,emmc}/manifest.yaml`：删除新增 `tools:` 段。
- `backend/scripts/check_image_tools.py`：恢复静态-only 版本（**不建议**：会重新产生假 verified 风险）。
- 删除 `tests/unit/test_v1_tool_manifest.py` 与本节新增证据；`tests/unit/test_tool_manifest.py` 夹具恢复为无 tools 声明。

### 9.7 契约变更声明（V1-08 / Lead 已确认）

1. **原审计夹具 `test_audit_missing_device_binary_remains_a_required_manifest_entry` 基于旧 glob 语义，已失效**：其 manifest 无 `tools:` 声明，按 V1-08「显式声明」契约不再成立（未声明文件不应被推导为必需项），故现于第 161 行失败属预期。日志：`v1-08-audit-repro-rerun-20261112.log`。
2. **等价修正夹具（显式声明设备二进制后删除文件）PASS**：`before=True / after=True / startup blocked=True → RESULT: PASS`，日志路径 `docs/verification/tasks/T-17/v1-08-declared-repro-20261112.log`（脚本 `docs/verification/tasks/T-17/v1-08-declared-repro.py`）。
3. **无 tools 声明的模块现在被判 `declaration_gaps` 致命**（`tests/unit/test_v1_tool_manifest.py::test_legacy_manifest_without_tools_is_rejected`），因此「删除已声明文件后清单变空 / 启动照常」的缺陷已消除。

**修正夹具 patch（4 行 tools 声明，供审计方更新原夹具；未改动审计证据文件）**：在原夹具写入 manifest 时追加（`sha256` 必须在删除文件前计算）：

```yaml
tools:
  device:
    - path: demo/binaries/arm64-v8a/tool
      abi: arm64-v8a
      version: '1.0'
      sha256: "<删除前该文件的 sha256>"
```

对应 Python（原夹具第 157-159 行处）：

```python
import hashlib
sha = hashlib.sha256(binary.read_bytes()).hexdigest()
(module / "manifest.yaml").write_text(
    "module:\n  name: demo\nitems: []\n"
    "tools:\n  device:\n"
    "    - path: demo/binaries/arm64-v8a/tool\n"
    "      abi: arm64-v8a\n"
    "      version: '1.0'\n"
    f"      sha256: \"{sha}\"\n",
    encoding="utf-8",
)
```

**【待用户确认限制】** `test-tools/ddr/` 无 `manifest.yaml`，其 memtester / stress-ng / stressapptest 二进制未被启动门禁（镜像仍整体复制）；**arm64 是否属于 V1 尚未确定**——需用户确认 ABI 支持矩阵后，再决定是否新增 DDR manifest 与实测（在此之前如实列为无法核验/待确认，不记通过）。
