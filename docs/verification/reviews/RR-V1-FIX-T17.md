# RR-V1-FIX-T17：V1-08 显式工具清单/哈希与 Docker 校验真实性（task-13）

- 评审编号：RR-V1-FIX-T17（V1-08）
- 评审对象/任务编号：task-13（V1-08；对应 T-17 增量）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- **评审程序说明（如实记录）**：task-13 于 16:35 完成，但完成通知未送达 reviewer，导致本 RR 晚于其余任务补审（评审链缺口，已另行报 Lead）。本记录基于当前工作区实现与 T-17 增量证据独立作出。
- 依据文档与版本：`RR-V1-READINESS-20261112.md` V1-08、`docs/design/scheduler-and-data.md` §6、`targeted-defect-repro.py` R6
- 环境与 commit/变更集：Windows 10；Python 3.12.10；git HEAD `fa70d3b` + 工作区。变更：`app/services/tool_manifest.py`（重写：显式 `tools:` 声明 + sha256 + 依赖闭包 + declaration_gaps）、`test-tools/**/manifest.yaml`（显式声明）、`scripts/check_image_tools.py`（防假 verified）、新增 `tests/unit/test_v1_tool_manifest.py`(17)
- 证据路径：`docs/verification/tasks/T-17/`（v1-08-audit-repro-rerun-20261112.log、v1-08-declared-repro.py/.log、pytest-v1-08-green-20261112.log、check-image-tools-v1-08-20261112.log、image-tools-summary-v1-08.json、regression-full-v1-08-20261112.log）；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t17-toolmanifest-reviewer.log`（10 passed）、`v1-fix-t17-declared-repro-reviewer.log`（PASS）、`targeted-defect-repro-FINAL-6of6.log`（R6 FAILED）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 显式声明：discover_requirements 仅来自 manifest `tools:`（host/shared/device/assets，含 path/abi/version/sha256），不再 glob 现存文件生成必需项 | 读 tool_manifest.py:162-192 | 代码确认；未声明 host_exec 引用 → KIND_UNDECLARED_REFERENCE 必需标记 | 通过（实现） |
| 2 | sha256 校验（不符→失败） | validate_tools:278-284 | 单测 + check-image-tools「SHA-256 全部匹配」 | 通过 |
| 3 | 共享依赖闭包（common./兄弟模块未声明→失败） | _imported_common_modules/_imported_sibling_modules + validate | 单测 + check-image-tools「共享依赖闭包完整」 | 通过 |
| 4 | declaration_gaps：模块含 host/二进制但 manifest 未声明 tools → 致命 | validate_tools:313-327 | 单测 + 代码 | 通过 |
| 5 | 删除**已声明**文件 → 条目仍在 → 启动失败 | 独立运行 v1-08-declared-repro.py | **PASS**：before/after 均含 `demo/binaries/arm64-v8a/tool`，assert_required_tools 抛错且错误含该路径 | 通过 |
| 6 | 真实仓库 manifests 已显式声明且哈希匹配 | test_real_repo_manifests_are_explicit_and_hashes_match | 独立重跑 test_v1_tool_manifest **10 passed**；check-image-tools static 13/13（显式声明无缺口） | 通过 |
| 7 | check_image_tools 不假 verified：仅发现 docker 命令 ≠ verified；无 docker → UNVERIFIABLE | 读脚本 + check-image-tools-v1-08 日志 | `RESULT: UNVERIFIABLE (static 13/13, runtime=UNVERIFIABLE)`，未伪造 | 通过 |
| 8 | **永久基线反例 R6（审计原样）** | 独立重跑 targeted-defect-repro | **FAILED（line 161：`before`={}）**——R6 断言"未声明文件存在即成为必需项"（旧 glob 契约），与 V1-08 新契约"仅显式声明为必需"直接冲突 | **失败（见 §3 判定）** |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/unit/test_v1_tool_manifest.py` | **10 passed** | 0 | `evidence/v1-fix-20261112/v1-fix-t17-toolmanifest-reviewer.log` |
| `python v1-08-declared-repro.py`（修正夹具版：显式声明后删除） | **PASS**（before/after 均含条目、启动被拦且错误含路径） | 0 | `evidence/v1-fix-20261112/v1-fix-t17-declared-repro-reviewer.log` |
| `targeted-defect-repro.py`（永久基线，6 项终验） | **5 passed / 1 FAILED（R6）** | 1 | `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log` |
| check_image_tools.py | static 13/13；runtime=UNVERIFIABLE | 0 | `docs/verification/tasks/T-17/check-image-tools-v1-08-20261112.log` |

## 3. R6 失败分析与判定（重点）

**事实**：R6（`test_audit_missing_device_binary_remains_a_required_manifest_entry`）在当前实现下失败于第 161 行：审计夹具的 manifest **没有 `tools:` 声明**（`items: []`），而 V1-08 新契约下"文件存在但未声明"**不应**自动成为必需项（这正是被审计缺陷的根源——glob 现存文件生成清单，删除即漏检）；未声明场景由更严格的 **`declaration_gaps` 致命错误**兜底（模块含 host/二进制但未声明 tools → 启动失败），且**已声明**文件删除后条目持久、启动被拦（修正夹具版定向复现 PASS）。

**判定（按 Lead 规则"任何一项仍失败即判该项不通过"）**：
- **V1-08 = 不通过（按当前永久基线口径）**：R6 作为基线仍失败，不得判该项通过。
- **技术分析（供裁决）**：缺陷类别本身已闭合——新机制下（a）已声明文件删除→`missing_required` 持久+启动失败（修正复现 PASS）；（b）未声明文件/目录→`declaration_gaps` 致命（比旧 glob 更严）；（c）sha256/依赖闭包校验。R6 失败属**基线夹具与新契约前提不匹配**（旧夹具隐含"存在即必需"的 glob 语义，恰是 V1-08 要求废除的语义）。
- **建议（需 Lead/用户裁决，评审方不擅自改基线）**：将永久基线 R6 更新为"显式声明后删除"形态（等价于 `v1-08-declared-repro.py` 的断言），并保留"未声明即 declaration_gaps 致命"的补充断言；更新后重跑 6/6 作为 V1-08 通过依据。在基线更新裁决前，维持"不通过"。

## 4. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T17-1 | 永久基线 R6 与新契约前提冲突 → 按基线口径不通过 | FINAL-6of6.log line 161 | V1-08 不能判通过（直至基线更新裁决） | 高（口径） | Lead/用户裁决 |
| P-V1T17-2 | task-13 完成通知未达 reviewer，评审滞后 | 评审程序说明 | 评审链缺口，已报 Lead | 低（流程） | Lead |
| P-V1T17-3 | Docker 运行时仍无法核验 | 无 docker | R27 未核验 | 中 | 运维/验收 |
| P-V1T17-4 | runner 共享依赖闭包仅静态 import 分析（动态 import/插件加载未覆盖） | _imported_* 实现 | 极端场景依赖缺失可能运行时才暴露 | 低 | 记录性 |

## 5. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | Docker build/start/容器内发现 | 主机无 docker | R27 无法核验（脚本已防假 verified） |
| L2 | 真实库/镜像内哈希核对 | 同上 | 仅 host 侧静态 |

## 6. 最终结论（2026-11-12 Lead R6 基线裁决后更新）

**有条件通过（缺陷类别闭合：删除已声明文件必失败；基线语义更新待用户确认；Docker 运行时仍无法核验）。** 实现层面全部落地：显式 `tools:` 声明 + sha256 + 依赖闭包 + declaration_gaps 致命 + check_image_tools 防假 verified（独立 10 passed、修正夹具定向复现 PASS、static 13/13、runtime UNVERIFIABLE 如实）。原"按旧基线不通过"判定经 Lead 裁决更新：R6 永久基线改为显式声明形态（R6a）+ 未声明 declaration_gaps 断言（R6b），**更新后 v2 基线 7/7 通过（独立重跑 exit 0，`evidence/v1-fix-20261112/targeted-defect-repro-v2-7of7.log`）**。条件：①基线语义更新属契约变更，**待用户最终确认**；②Docker 运行时（R27）继续无法核验。详见 §8。

## 8. 基线语义更新说明（契约变更，待用户确认）

- **变更内容**：永久基线 R6 由"文件存在即成为必需项（glob 语义）"更新为"显式 `tools:` 声明 + 删除已声明文件 → 仍必需且启动失败（R6a）"并新增"无 tools 声明的模块 → declaration_gaps 致命（R6b）"。v1 审计原文件保持原样未改；v2 基线文件 `evidence/v1-fix-20261112/targeted-defect-repro-v2.py`（R1～R5 与 v1 逐字一致，R6 拆为 R6a/R6b）。
- **裁决记录**：Lead 2026-11-12 决定（V1-08 修复本意即废除 glob 行为，审计夹具前提与新契约冲突属预期）；**待用户最终确认**。确认前 V1-08 状态=有条件通过；确认后转正式通过（Docker 运行时项仍单独无法核验）。
- **程序改进记录**：task-13 完成通知未送达 reviewer，导致其评审滞后至终验阶段才补出（评审链缺口）。建议：任务 complete 通知必须显式 @ 评审方并要求回执；本轮已把该缺口记入流程改进，评审方在终验时以全量反例复跑兜底发现。

## 9. 签名

reviewer，2026-11-12；本记录基于源码、独立反例/定向复现与静态核对作出，未替开发修改任何代码，未擅自修改审计原文件；v2 基线按 Lead 裁决建立。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
