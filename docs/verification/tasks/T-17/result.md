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

---

## 10. 契约 v1.1 §6.1 A1~A5（task-23，2026-11-13）

对应 `docs/design/scheduler-and-data.md` §6.1（A1~A5 正文，用户已确认）与
`docs/contracts/CHANGES-DRAFT-v1.1-20261113.md` GWT A1~A7；修复
`RR-V1-REFINAL-20261112.md` §3.1 的 F1~F4 fail-open 动态实证。

### 10.1 变更（严格先红后绿）

| 文件 | 变更 |
|---|---|
| `app/services/tool_manifest.py` | A1：`_declared_tools` 对 tools.host/shared 强制 sha256 必填（缺失即 ToolManifestError，指明 manifest 路径与条目）。A2：declaration_gaps 判定扩展为「无 tools 段 **或** tools 四段全空（tools:{} 等）且目录含 host/*.py 或 binaries/*/*」。A3：`discover_requirements` 对未声明的 `{host_tool_dir}/X` 引用**硬失败**（删除 undeclared_reference 降级分支与常量）。A4：`_add` 对非法 path（空/绝对/含 ..）抛 ToolManifestError 且信息含原始声明值（替换静默丢弃；Windows/POSIX 双判定）。A5：`validate_tools` 对零 manifest 根记 declaration_gaps（ok=False），`assert_required_tools` 抛错并指明根路径 |
| `tests/unit/test_v1_tool_manifest.py` | 新增 A1 host/A1 shared/A2/A3/A4/A5 共 6 项反例；`test_no_manifest_root_warns_but_ok` 反转为 `test_no_manifest_root_rejected_a5`（断言抛错，预期行为变更） |
| `tests/unit/test_tool_manifest.py` | `test_no_manifest_root_warns_but_ok` 同步反转；`test_missing_required_runner_fails_and_names_manifest` 按 A3 语义适配（validate 即抛错并指明 manifest+引用值，断言未放宽） |
| `tests/unit/test_secret_strength.py`（lead 批准加入 scope） | `test_main_startup_validation_accepts_legal_secret` 夹具按 A5 适配：tools_root 补最小合法 manifest（host+shared，sha256 实算）——A5 连带夹具适配（非放宽） |
| `test-platform/docker-compose.yml` | task-D：app 服务补 `image: test-platform:v1-08-check`（与 check_image_tools `--tag` 默认值一致），消除 RR-V1-REFINAL §3.5 指出的「docker build 与 compose up 验证不同镜像」验证分裂 |
| `backend/scripts/check_image_tools.py` | 新增 `check_compose_image_alignment()` 静态核对 compose image 与 --tag 一致 |

### 10.2 红/绿与销项证据

| 项 | 结果 | 日志 |
|---|---|---|
| 红（先） | `pytest tests/unit/test_v1_tool_manifest.py tests/unit/test_tool_manifest.py -q` → **8 failed / 15 passed**（A1×2、A2、A3、A4、A5×2 + 反转用例×2，全部按预期失败） | `pytest-v1-1-A1-A5-red-20261113.log` |
| 绿（后） | 同命令 → **23 passed / 0 failed** | `pytest-v1-1-A1-A5-green-20261113.log` |
| F1~F4 销项 | `manifest-failopen-repro-v2.py`（原审计文件未动）→ **9/9 CLOSED，RESULT: ALL CLOSED**，EXIT=0 | `manifest-failopen-repro-v2-20261113.log`（脚本 `manifest-failopen-repro-v2.py`） |
| 真实仓库回归 | `python -m app.services.tool_manifest --validate ../test-tools` → **ok=true**，declaration_gaps=[]，EXIT=0 | `tool-manifest-validate-repo-v1-1-20261113.log` |
| 镜像静态+清单 | `check_image_tools.py` → static **15/15**（含 compose image 对齐 PASS），runtime=UNVERIFIABLE（主机无 docker，如实不伪造），EXIT=2 | `check-image-tools-v1-1-20261113.log` / `image-tools-summary-v1-1.json` |
| 全量 pytest | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning` → **459 passed / 1 failed**，退出码 1 | `regression-full-v1-1-20261113.log` |

### 10.3 GWT 逐条

| GWT | 结果 | 证据 |
|---|---|---|
| A1 host 缺 sha256 → 抛错指明 manifest+条目；validate 不得 ok=True | ✅ | test_a1_host_entry_missing_sha256_raises |
| A1 sha256 被篡改 → 哈希不匹配且门禁失败（v1.0 反例保持） | ✅ | test_sha256_mismatch_fails |
| A2 tools:{} 四段全空 + host 文件 → gaps+启动失败 | ✅ | test_a2_empty_tools_section_with_host_files_is_declaration_gap |
| A3 {host_tool_dir}/x.py 未声明 → 抛错，无 undeclared 条目 | ✅ | test_a3_undeclared_host_tool_reference_hard_fails + repro-v2 F3 |
| A3 已声明 runner 引用未声明 common.y → closure 非空+启动失败 | ✅ | test_undeclared_common_import_is_closure_violation |
| A4 path ../../etc/passwd → 抛错含原始值 | ✅ | test_a4_illegal_path_raises_with_original_value + repro-v2 F4 |
| A5 空 TEST_TOOLS_PATH → 拒绝启动并指明路径 | ✅ | test_no_manifest_root_rejected_a5 / test_a5_tools_root_without_any_manifest_rejects_startup |
| F1~F4 销项全 CLOSED | ✅ | manifest-failopen-repro-v2（9/9 CLOSED） |

### 10.4 全量 pytest 与并发说明（如实）

最终全量（`regression-full-v1-1-20261113.log`，2026-11-13 09:0x）为
**459 passed / 1 failed**：唯一失败项
`tests/integration/test_v1_followup_audit.py::test_b3_ai_and_manual_creation_parity`
属**变更包 2（B1~B3 AI 入口授权顺序，另一队友在途实施）**的红测/中间态（AI 创建
409 vs 期望 201），与 task-23 的 tool_manifest/compose 改动无关——task-23 全部
新增/受影响用例（23 项 focused + test_secret_strength 21 项）均绿。期间共享树还出现
过 tasks.py 暂缺 `BackgroundTasks` 导入的瞬态（已由对应队友修复）。
待变更包 2 落地后全量应 0 failed；本任务范围内无未闭合项。

### 10.5 task-D 与未验证项

- task-D compose 镜像统一已完成并通过静态核对（`check_compose_image_alignment` PASS）；docker 运行时仍 UNVERIFIABLE（主机无 docker，如实记录，不伪造 verified）。
- A5 行为变更：空 TEST_TOOLS_PATH 从静默启动改为拒绝启动（契约 v1.1 明确意图）；受影响的 3 处测试夹具均已适配且未放宽。
- 未验证项：docker 运行时（build/up/health/容器内发现）；其余无。
- 【Lead 裁决②存档】全量 459 passed / 1 failed，唯一失败 `test_b3_ai_and_manual_creation_parity` 归变更包 2（task-24）在途，最终全量由 Lead 连续 2 轮收口。（补记：交付后隔离复跑该项已由变更包 2 owner 修复并通过。）
