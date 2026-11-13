# 契约变更草案 v1.1（待用户确认）

- 草案编号：CHANGES-DRAFT-v1.1-20261113
- 日期：2026-11-13
- 状态：**已确认并落地**（2026-11-13 经用户授权确认；正式文本已落入 `docs/design/scheduler-and-data.md` §6.1、`docs/contracts/task-execution-v1.0.md` §10、`docs/contracts/README.md` 版本 v1.1 与变更记录）。本文件保留作为确认过程留痕，GWT 验收标准继续有效。
- 依据：`RR-V1-REFINAL-20261112.md` §3.1/§3.2/§3.3（F1～F4 fail-open 动态实证、AI 入口授权顺序与创建收口未闭合）
- 版本规则：契约版本 v1.0 → v1.1（+0.1）；变更经用户确认后分别落入 `docs/design/scheduler-and-data.md` §6 与 `docs/contracts/task-execution-v1.0.md` §10，并在 `docs/contracts/README.md` §5 追加变更记录
- 范围外：C3（discovery 响应可见性）不在本次变更；U1、U-D1、U-V1-05、U-V1-08、配置导入门禁不受影响

---

## 变更包 1（C2 + C1 口径 b）：工具清单显式声明语义收严

**目标文件**：`docs/design/scheduler-and-data.md` §6 干净部署契约（在现有两条之后新增声明规则小节）

### 现状（v1.0）

> - Docker 构建上下文和最终镜像必须包含 manifest 声明的 test-tools、runner 和对应架构二进制；启动时执行只读工具发现校验。
> - 声明存在但镜像缺失的必需工具使启动失败并指出 manifest 路径；范围内缺失 APK、外设或人工条件按 R3 记 skip，不伪造工具结果。

现状未规定声明结构本身的强约束，导致 F1～F4 四个 fail-open（证据：`evidence/v1-refinal-review-20261112/manifest-failopen-repro.py`，4 项全部复现成功，EXIT=0）。

### 变更后新增文本（草案）

> **6.1 工具清单声明规则**
>
> 每个模块目录的 `manifest.yaml` 必须显式声明 `tools` 段，结构如下：
>
> ```yaml
> tools:
>   host:                       # host runner
>     - path: upfm/host/mc_props_check.py
>       sha256: "<64 位十六进制>"   # 必填
>       version: "<可选>"
>   shared:                     # 共享 Python 依赖
>     - path: common/adb_runner.py
>       sha256: "<64 位十六进制>"   # 必填
>   device:                     # 设备二进制
>     - path: emmc/binaries/armeabi-v7a/fio
>       abi: armeabi-v7a          # 必填
>       sha256: "<64 位十六进制>"   # 必填
>   assets:                     # 可选测试资源
>     - path: upfm/assets/test_app.apk
>       sha256: "<可选>"
> ```
>
> - **A1（对应 F1）**：`tools.host` 与 `tools.shared` 条目 `path`、`sha256` 必填；缺失即 manifest 加载失败（`ToolManifestError`，错误信息指出 manifest 路径与问题条目）。声明了 sha256 的条目必须哈希匹配，不匹配启动失败（v1.0 语义保持）。
> - **A2（对应 F2）**：`tools` 段存在但四段全空（如 `tools: {}`）且模块目录含 `host/*.py` 或 `binaries/*/*`，视为声明缺口，启动失败；完全无 `tools` 段同此处理（v1.0 语义保持）。
> - **A3（对应 F3，C1 口径 b）**：`items[].exec_command` 中 `{host_tool_dir}/X` 引用的文件 X 必须在某 manifest 的 `tools.host` 显式声明；**未声明即 manifest 加载失败，废除 v1.0 的 undeclared_reference 降级条目**。已声明的 host runner 及其 `import common.*`、`from common import *`、同目录兄弟模块 import 的全部依赖必须在 `tools.shared`/`tools.host` 声明内（依赖闭包，v1.0 语义保持）。
> - **A4（对应 F4）**：声明 `path` 规范化后不得为空、为绝对路径或含 `..` 越界；违反即 manifest 加载失败，错误信息包含 manifest 路径与原始声明值。
> - **A5（对应 R-E）**：`TEST_TOOLS_PATH` 存在但不含任何 `manifest.yaml` 时启动失败，禁止空工具目录静默启动。
> - `tools.assets` 条目 `path` 必填、`sha256` 可选；缺失的已声明可选资源按 R3 记 skip，不伪造工具结果（v1.0 语义保持）。

### 验收标准（GWT，经用户确认后即为唯一验收依据）

| 编号 | GWT |
|---|---|
| A1 | 给定 `tools.host` 条目缺 `sha256` 的 manifest，当加载/校验时，则抛 `ToolManifestError` 并指明 manifest 路径与条目；`validate_tools` 不得返回 `ok=True` |
| A1 | 给定声明 sha256 的 host 文件被篡改，当校验时，则哈希不匹配且启动门禁失败（v1.0 反例保持） |
| A2 | 给定 `tools: {}` 且目录含 host 文件的 manifest，当校验时，则记 declaration_gaps 且启动失败 |
| A3 | 给定 `exec_command` 含 `{host_tool_dir}/x.py` 且 `tools.host` 未声明 x.py 的 manifest，当加载时，则抛错；不再产生 undeclared_reference 条目 |
| A3 | 给定已声明 host runner 引用未声明的 `common.y`，当校验时，则 closure_violations 非空且启动失败 |
| A4 | 给定 path 为 `../../etc/passwd` 的声明，当加载时，则抛错且信息含原始值 |
| A5 | 给定空 `TEST_TOOLS_PATH`（无 manifest.yaml），当应用启动时，则拒绝启动并指明路径 |

### 影响面

- 实现：`backend/app/services/tool_manifest.py`（`_declared_tools` 强制 sha256、`_add` 非法路径硬失败、`discover_requirements` 删除 undeclared 降级并改为硬失败、`validate_tools`/`assert_required_tools` 空根拒绝）
- 测试：`tests/unit/test_v1_tool_manifest.py` 新增 A1～A5 反例各 1 项；`manifest-failopen-repro.py` 4 项复现全部转为"修复后抛错"；`test_no_manifest_root_warns_but_ok` 语义反转（由 ok=True 改为抛错），属预期行为变更
- 兼容性：真实仓库 manifest 已全部带 sha256（`test_real_repo_manifests_are_explicit_and_hashes_match` 现行断言），实施零迁移成本；CI/构建唯一行为变化为"空目录误配置由静默启动变拒绝启动"，属本变更意图

---

## 变更包 2（R-B）：AI 任务入口授权顺序与创建收口

**目标文件**：`docs/contracts/task-execution-v1.0.md` §10 Legacy 路径（line 348 现有条款之后追加）

### 现状（v1.0）

> AI 创建入口无论是否保留独立路径，都必须先转换为完全相同的任务创建对象，再调用同一校验、设备授权和幂等服务，不得自行写任务。

现状未规定授权与知识读取/LLM 调用的先后顺序，导致授权前披露（证据：`RR-V1-REFINAL-20261112.md` §3.2，`ai_tasks.py:48-71` 先 `planner.plan()` 后授权）。

### 变更后追加文本（草案）

> **授权顺序**：AI 入口在确定目标设备后，必须先完成与手动创建完全相同的设备授权校验；**校验通过后才允许读取该设备相关知识条目与调用 LLM**。授权拒绝（403）或设备不可用（409）时，本次请求的知识库读取次数与 LLM 调用次数必须为零。任务对象转换与写入仍统一收口到同一创建服务（本条 v1.0 语义保持）。

### 验收标准（GWT）

| 编号 | GWT |
|---|---|
| B1 | 给定普通用户对他人设备提交 AI 文本，当请求处理时，则返回 403，且 `get_device_knowledge` 与 LLMClient 调用计数为 0（monkeypatch 断言） |
| B2 | 给定 maintenance/offline 设备，当走 AI 入口时，则返回 409 且知识读取与 LLM 调用计数为 0（现行 409 行为保持） |
| B3 | 给定 AI 创建成功，当落库时，则任务行、设备状态推进与幂等语义和手动创建路径逐字段一致（差分断言走同一创建服务） |

### 影响面

- 实现：`backend/app/api/ai_tasks.py`（先授权后规划）、`backend/app/services/nl_task_planner.py`（规划与知识/LLM 调用解耦，授权回调或设备白名单注入）
- 测试：`tests/integration/test_v1_followup_audit.py` 新增 B1、B2 两项永久回归
- 前端：无接口形状变更，无影响

---

## `docs/contracts/README.md` 变更记录追加行（确认后落表）

| 版本 | 日期 | 状态 | 内容 |
|---|---|---|---|
| v1.1 | 2026-11-13 | 待确认 | ① 工具清单显式声明语义收严（scheduler-and-data §6.1 新增 A1～A5：host/shared sha256 必填、空 tools 段视为声明缺口、`{host_tool_dir}` 引用必须显式声明并废除 undeclared 降级、非法路径硬失败、空 TEST_TOOLS_PATH 拒绝启动）② AI 任务入口授权顺序：设备授权先于知识读取与 LLM 调用，调用计数零披露，任务写入收口统一创建服务（task-execution §10 追加） |

---

## 确认请求

请逐项确认：

1. 变更包 1（A1～A5）语义与 GWT 验收标准；
2. 变更包 2（B1～B3）语义与 GWT 验收标准；
3. A5（空 tools 根拒绝启动）是否接受"误配置由静默变拒绝"的行为变更；
4. 变更记录行内容。

确认后本草案落为契约 v1.1 正文，开发方据此按"先反例测试（红）后实现（绿）"动工；reviewer 以 GWT 逐条验收。
