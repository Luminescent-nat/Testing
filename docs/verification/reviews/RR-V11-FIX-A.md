# RR-V11-FIX-A：契约 v1.1 变更包 1——工具清单 A1～A5（task-23 / task-A+D）

- 评审编号：RR-V11-FIX-A
- 评审对象/任务编号：task-23（task-A/D；变更包 1 = scheduler §6.1 A1～A5）
- 评审日期：2026-11-13
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/CHANGES-DRAFT-v1.1-20261113.md`（GWT A1～A7）、`docs/design/scheduler-and-data.md` §6.1、`RR-V1-REFINAL-20261112.md` §3.1（F1～F4）
- 环境与 commit/变更集：Windows 10；Python 3.12.10；**基线 HEAD `387279e`** + 工作区（task-23/24/26 未提交变更并存）。task-23 变更：`app/services/tool_manifest.py`（A1~A5）、`tests/unit/test_v1_tool_manifest.py`（6 反例+反转）、`tests/unit/test_tool_manifest.py`（2 处适配）、`tests/unit/test_secret_strength.py`（A5 连带夹具适配，Lead 批准）、`docker-compose.yml`（task-D image 对齐）、`scripts/check_image_tools.py`（compose 对齐核对）
- 证据路径：`docs/verification/tasks/T-17/result.md` §10、`pytest-v1-1-A1-A5-red/green-20261113.log`、`manifest-failopen-repro-v2-20261113.log`、`tool-manifest-validate-repo-v1-1-20261113.log`、`check-image-tools-v1-1-20261113.log`、`image-tools-summary-v1-1.json`、`regression-full-v1-1-20261113.log`；评审方独立重跑 `reviews/evidence/v11-fix-20261113/manifest-failopen-repro-v2-reviewer.log`（9/9 CLOSED）、`v11-fix-a-focused-reviewer.log`（44 passed）

## 1. 门禁与检查项

| # | 门禁/检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | G9 契约 diff 空（本轮复核） | `git diff HEAD -- docs/contracts` | 0 行 | 通过 |
| 2 | G1 红：8 failed / 15 passed | 读红测日志 | `pytest-v1-1-A1-A5-red-20261113.log`（A1×2/A2/A3/A4/A5×2+反转×2 按预期失败） | 通过 |
| 3 | G1 绿：23 passed | 读绿测日志 + **独立重跑** | `pytest-v1-1-A1-A5-green-20261113.log`；评审方 3 文件 **44 passed**（23+21 secret_strength） | 通过 |
| 4 | GWT A1：host/shared 缺 sha256 → ToolManifestError 指 manifest+条目；validate 不得 ok=True | 独立运行销项脚本 F1 两断言（raised + needle=manifest 路径/条目） | 9/9 CLOSED | 通过 |
| 5 | GWT A1：sha256 篡改 → 哈希不符+门禁失败 | test_sha256_mismatch_fails（独立 44 passed 内） | 通过 | 通过 |
| 6 | GWT A2：`tools:{}` 四段全空+目录含 host/binaries → declaration_gaps+启动失败 | 销项 F2 两断言（gaps=1 + raised needle=demo） | 9/9 CLOSED | 通过 |
| 7 | GWT A3：`{host_tool_dir}/x.py` 未声明 → 加载失败、无 undeclared_reference 条目 | 销项 F3 三断言（含"undeclared_reference 类必需项已废除"） | 9/9 CLOSED | 通过 |
| 8 | GWT A3：已声明 runner 引用未声明 common.y → closure 失败 | test_undeclared_common_import_is_closure_violation（44 passed 内） | 通过 | 通过 |
| 9 | GWT A4：`../../etc/passwd` → 抛错含原始声明值 | 销项 F4 两断言（raised + needle=原始值） | 9/9 CLOSED | 通过 |
| 10 | GWT A5：空 TEST_TOOLS_PATH（无 manifest）→ 拒绝启动并指明路径 | test_no_manifest_root_rejected_a5 + test_a5_tools_root_without_any_manifest_rejects_startup | 通过（语义反转属契约预期） | 通过 |
| 11 | G4 F1～F4 全项销项 | **独立重跑** `manifest-failopen-repro-v2.py` | **9/9 CLOSED，RESULT: ALL CLOSED，exit 0** | 通过 |
| 12 | 原审计文件未动 | git status evidence | `manifest-failopen-repro.py`（v1-refinal）未改；其当前运行为抛错（A1 硬失败，评审方独立复跑 exit 1，符合修复后语义） | 通过 |
| 13 | 真实仓库 `--validate` ok=true | **独立运行** `-m app.services.tool_manifest --validate ../test-tools` | ok=true；missing/hash_mismatch/closure_violations/declaration_gaps 全空；27 必需+1 skip（APK） | 通过 |
| 14 | A5 连带夹具适配非放宽 | 读 test_secret_strength diff（tools_root 补最小合法 manifest，sha256 实算） | test_main_startup_validation_accepts_legal_secret 仍断言合法密钥可启动 | 通过（非放宽） |
| 15 | task-D compose image 对齐 | docker-compose 补 `image: test-platform:v1-08-check` + check_image_tools `check_compose_image_alignment` | check-image-tools static **15/15**（含对齐 PASS），runtime=UNVERIFIABLE exit 2（无 docker，如实） | 通过 |
| 16 | 全量口径 | 开发 459 passed / 1 failed（唯一失败=变更包 2 B3 在途红测态，非本任务） | `regression-full-v1-1-20261113.log`；B3 已由 task-24 收口 | 通过（口径留痕） |
| 17 | dd/binaries 无 manifest 观察项 | result §9.5.2 | ddr 无 manifest 不被门禁——待用户 ABI 矩阵裁决（沿用 V1-08 待确认限制） | 如实记录 |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `python manifest-failopen-repro-v2.py`（task-23 销项脚本） | **9/9 CLOSED，RESULT: ALL CLOSED** | 0 | `evidence/v11-fix-20261113/manifest-failopen-repro-v2-reviewer.log` |
| `python manifest-failopen-repro.py`（原审计文件，现应抛错） | ToolManifestError：A1 host 条目缺必填 sha256（契约 v1.1 §6.1 A1） | 1 | 符合修复后语义（fail-open→抛错） |
| `python -m app.services.tool_manifest --validate ../test-tools` | ok=true；四类违例全空；27 必需+1 skip | 0（JSON 输出） | 评审方独立运行（本记录 §1 #13） |
| `pytest test_v1_tool_manifest + test_tool_manifest + test_secret_strength` | **44 passed** | 0 | `evidence/v11-fix-20261113/v11-fix-a-focused-reviewer.log` |
| 开发证据：红/绿 | 8F/15P → 23P | 1→0 | `pytest-v1-1-A1-A5-red/green-20261113.log` |
| 最终严格全量 | 待 Lead 两轮日志，届时补记 | — | — |

## 3. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V11A-1 | ddr 目录无 manifest，其 memtester/stress-ng/stressapptest 不被启动门禁 | result §9.5.2 | 镜像整体复制但门禁不覆盖；arm64 是否入 V1 待用户 ABI 矩阵 | 中（待用户） | 用户/后续 |
| P-V1T23-2 | 设备二进制 version=unspecified | result §9.5.3 | sha256 已锁定；version 未实测 | 低 | 记录性 |
| P-V1T23-3 | 哈希绑定文件内容：合法修改 test-tools 必须同步 manifest sha256 | result §9.5.4 | 变更流程约束（设计如此） | 低 | 变更流程 |
| P-V1T23-4 | Docker 运行时 UNVERIFIABLE | 无 docker | R27 未核验（沿用） | 中 | 运维 |

## 4. 限制/无法核验项

Docker 运行时（build/up/health/容器内发现）无法核验——脚本 UNVERIFIABLE 如实。其余无。

## 5. 待用户确认项

沿用 V1-08 待确认：ddr/ABI 支持矩阵、二进制 version 字段。

## 6. 最终结论

**通过（变更包 1 A1～A5）。** 先红后绿证据完整（红 8F/15P → 绿 23P，评审方独立 3 文件 44 passed）；GWT A1～A5 逐条通过且 **F1～F4 销项 9/9 CLOSED（评审方独立重跑）**；原审计复现现按 A1 语义抛错（fail-open 废除）；真实仓库 `--validate ok=true` 四类违例全空；A5 行为变更（空目录静默→拒绝启动）与 3 处夹具适配均未放宽；task-D compose image 对齐静态 15/15。遗留：ddr/ABI、二进制 version、Docker 运行时（沿用）。全量口径 459/1（B3 在途）已留痕，最终以 Lead 连续 2 轮严格全量为准。

## 7. 签名

reviewer，2026-11-13；本记录基于源码 diff、红绿日志与独立销项/校验运行作出，未替开发修改任何代码。
