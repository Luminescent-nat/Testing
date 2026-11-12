# RR-T17：干净镜像包含声明工具与启动清单校验

- 评审编号：RR-T17
- 评审对象/任务编号：T-17（task-6，owner infra-tools）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/design/scheduler-and-data.md` v1.0 §6（干净部署契约：构建上下文/镜像含 manifest 声明 test-tools/runner/二进制、启动只读工具发现、缺失必需工具失败指 manifest、可选 APK/外设 skip）、`docs/verification/verification-rules-v1.0.md` §6（Docker/工具/密钥）、`docs/plan/task-board-v1.0.md` T-17
- 环境与 commit/变更集：Windows 10，Python 3.12.10；**主机无 docker 命令**（`Get-Command docker` 为空）；git HEAD `d0b415d` + 工作区。变更：`test-platform/Dockerfile`（COPY test-tools + TEST_TOOLS_PATH）、`.dockerignore`（放开 test-tools）、新增 `app/services/tool_manifest.py`、新增 `scripts/check_image_tools.py`、新增 `tests/unit/test_tool_manifest.py`、`app/main.py` lifespan 接入 `validate_startup_config()`
- 证据路径：`docs/verification/tasks/T-17/`（result.md、check-image-tools-20261112.log、image-tools-summary.json、pytest-T17-red/green、regression-full）；评审方独立全量 `docs/verification/reviews/evidence/test-rerun-20261112/backend-final-full-regression-reviewer.log`

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 只改声明 scope | git diff/status | Dockerfile/.dockerignore/tool_manifest.py/check_image_tools.py/test_tool_manifest.py/main.py(lifespan)；未改 test-tools 行为/frontend/judgement 等 | 通过 |
| 2 | Dockerfile 真携带 test-tools（manifest+runner+二进制） | 读 Dockerfile:48 `COPY test-tools/ ./test-tools/`；.dockerignore diff | 构建上下文 test-platform/，COPY 整目录；.dockerignore 移除 `test-tools/` 排除（仅全局规则排除 __pycache__/*.pyc） | 通过（静态） |
| 3 | TEST_TOOLS_PATH/STATIC_PATH/WORKDIR 一致 | 读 Dockerfile:37,62-63 + check_image_tools 10/10 | WORKDIR=/app、TEST_TOOLS_PATH=/app/test-tools、STATIC_PATH=/app/static 对齐 | 通过 |
| 4 | manifest 声明工具发现（必需 22 / skip 1） | check-image-tools 日志 / image-tools-summary.json | 发现 emmc/upfm manifest；22 必需工具齐备 missing=[]；`upfm/assets/test_app.apk` 缺失 → skip 不伪造 | 通过（host 侧静态发现） |
| 5 | 缺失必需工具→启动失败并指 manifest 路径 | 读 tool_manifest.py assert_required_tools:191-207；test_tool_manifest 7 用例 | ToolManifestError 列出缺失工具名/kind/声明 manifest 路径/source；root 不存在亦失败 | 通过 |
| 6 | 可选 APK/外设缺失→skip 不阻断 | tool_manifest.py:31-33,103,167-171；单测 test_missing_apk_is_skip | .apk 缺失记 skip 日志+JSON，不阻断启动 | 通过 |
| 7 | lifespan 接入不影响既有启动 | 读 main.py validate_startup_config + lifespan try/except；T-18 启动矩阵 legal/fresh /health=200；独立全量 310 passed | 合法密钥+齐全工具时启动正常；缺失/弱配置拒绝启动 | 通过（host 侧等效） |
| 8 | Docker 不可用是否如实写"无法核验"、未伪造 | 读 result.md §6、check-image-tools 日志尾、image-tools-summary docker_available | 明确 `docker build/start verification: UNVERIFIABLE (no docker)`，未伪造镜像内发现/启动 | 通过（如实） |
| 9 | 7 单测真实（先红后绿） | pytest-T17-red/green；独立全量含 test_tool_manifest | 红：收集错误；绿：7 passed；独立全量含该 7 用例通过 | 通过 |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-T17-1 | **Docker 干净构建与容器内启动无法核验**：主机无 docker，镜像内 `/app/test-tools` 实际内容、容器内工具发现、容器 lifespan 启动、多架构二进制在容器内可用性均未执行 | result.md §6；check-image-tools 日志 | R27/干净部署契约核心运行时项**无法核验**；静态核对与 host 侧等效验证不能等同镜像核验 | 中-高 | 运维/验收（需有 docker 环境） |
| P-T17-2 | tool_manifest 的 device 二进制发现依赖 `binaries/<arch>/*` 目录约定；manifest 若声明其它形式二进制可能漏检 | tool_manifest.py:113-129 | 覆盖当前 emmc/ddr 结构；未来新工具形态需同步 | 低 | T-36/T-17 后续 |
| P-T17-3 | 可选资源仅识别 `.apk` 后缀；其它外设/人工资源缺失是否 skip 依赖 manifest exec_command 引用形态 | tool_manifest.py:33 | 非 .apk 可选资源可能被判必需 | 低 | 记录性 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | `docker build` 干净镜像构建 | 主机无 docker | 镜像内工具/路径/二进制**无法核验** |
| L2 | 容器内 uvicorn+lifespan 启动链路与工具发现 | 同上 | 无法核验；仅有 host 侧等效（T-18 矩阵） |
| L3 | 多架构二进制容器内可用性、Alpine adb 等 | 同上 | 无法核验 |
| L4 | 容器内干净空库首次启动 | 同上 | host 侧 fresh-empty-db 通过（seed 修复后），容器内无法核验 |

## 4. 待用户确认项

| # | 事项 | 建议 |
|---|---|---|
| U-T17-1 | 是否需在有 docker 的 CI/主机补做干净构建+启动核验以关闭 R27 | 建议在具备 docker 环境处实际 `docker build`/`docker compose up` 并保存镜像内工具清单与 /health 日志，当前 R27 记"无法核验" |

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| 评审方独立严格全量 `pytest tests -q -W error::...`（含 test_tool_manifest 7 用例） | **310 passed / 0 failed** | 0 | `evidence/test-rerun-20261112/backend-final-full-regression-reviewer.log` |
| Lead 最终全量日志 | 310 passed（135.09s） | 0 | `docs/verification/tasks/FULL-REGRESSION-final-20261112.log` |
| 静态核对 check_image_tools.py | 10/10 PASS；docker=UNVERIFIABLE | 0 | `docs/verification/tasks/T-17/check-image-tools-20261112.log` |
| 开发绿测 test_tool_manifest.py | 7 passed | 0 | `docs/verification/tasks/T-17/pytest-T17-green-20261112.log` |

## 6. 最终结论

**有条件通过 / Docker 运行时无法核验。** 静态与代码层通过并独立复核：Dockerfile 真携带 test-tools（manifest+runner+二进制）、.dockerignore 放开、TEST_TOOLS_PATH/STATIC_PATH/WORKDIR 对齐一致；tool_manifest 实现"必需工具缺失→启动失败并指 manifest 路径"与"可选 APK 缺失→skip 不伪造"；main.py lifespan 接入在合法配置下启动正常（T-18 矩阵 /health=200），既有无回归（独立严格全量 310 passed）。**但 R27/干净部署核心——`docker build` 干净镜像构建、容器内工具发现与启动、多架构二进制容器可用性——因主机无 docker 无法核验，开发已如实标注未伪造。** 该运行时项须在有 docker 环境补做后才可判通过；本轮不得声称干净镜像部署通过。

## 7. 签名

reviewer，2026-11-12；本记录基于源码、静态核对、单测与独立全量日志作出，未替开发修改任何代码；未执行 docker（本机不可用）。
