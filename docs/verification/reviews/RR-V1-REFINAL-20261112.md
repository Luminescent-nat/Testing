# RR-V1-REFINAL-20261112：开发方修复批次独立重新复核记录

- 评审编号：RR-V1-REFINAL-20261112
- 复核对象：开发方"六项缺陷闭环 + 448 passed 严格全量"陈述（HEAD `a4a32f2`，6 个修复 commit：59b4c43/f3eb4ef/7fdf269/88e1a5b/1fe4e22/a4a32f2）
- 复核日期：2026-11-12
- 复核人：reviewer（独立评审方）
- 复核方式：代码走查 + 独立动态复现 + 两轮独立后端严格全量 + v2 反例基线重跑
- 证据目录：`evidence/v1-refinal-review-20261112/`（backend-full.log、backend-full-rerun.log、manifest-failopen-repro.py、v2-baseline-rerun.log）
- 前置说明：应用户要求重新复核，并指出 reviewer 此前评审状态有误。本记录对"已修复"与"未闭合"给出独立实证判定。

## 1. 总体判定

**维持"不通过"，但判定依据已变化。**

- 用户指出的"此前状态错误"**部分成立**：开发方声称的六项修复中，**五项已验证属实**（迁移常量、maintenance 枚举/409、owner_id 必填、discovery body 校验、分页约束），reviewer 此前"未修复"的判定对这些项已过时，予以更正。
- 但"全部 P0 动态缺陷闭合"的表述**与实证不符**：`tool_manifest.py` 四项 fail-open 机制与 AI 入口授权前知识读取/LLM 调用两项高严重度问题**仍未修复**，本轮均以独立动态复现确认。
- 另发现严格全量回归**不稳定**：reviewer 独立两轮全量各出现 1 个不同的失败项（均隔离通过），开发方"448 passed / 0 failed"不是可稳定复现的结论。

## 2. 已验证修复（代码路径 + 动态佐证，判定：闭合）

| # | 修复项 | 验证依据 | 佐证 |
|---|---|---|---|
| 1 | 迁移测试 HEAD_REVISION 过期 | `tests/unit/test_v1_migration.py:26` 与 `scripts/verify_migrations.py:73` 均为 `"004_task_deleted_at"` | 两轮独立全量中迁移测试全部通过 |
| 2 | DeviceStatus.MAINTENANCE 枚举 | `app/schemas.py:66` `MAINTENANCE = "maintenance"` | 全量通过；maintenance 序列化/过滤回归通过 |
| 3 | AI 创建设备 maintenance → 409 | `app/api/ai_tasks.py:80-81` | `test_v1_followup_audit.py::test_audit_ai_maintenance_device_cannot_start` 两轮全量均通过 |
| 4 | PATCH owner_id 必填（显式 null 取消分配） | `app/api/devices.py:38` `owner_id: Optional[int]` 无默认值 | `test_audit_patch_owner_id_is_required_even_when_nullable` 通过 |
| 5 | discovery 非空 body → 400 | `app/api/devices.py:80-89` | `test_audit_discovery_rejects_nonempty_body` 通过 |
| 6 | 设备分页约束 | `app/api/devices.py:126-127` `Query(1, ge=1)` / `Query(20, ge=1, le=100)` | `test_audit_device_list_rejects_invalid_pagination` 通过 |
| 7 | v2 反例永久基线 | reviewer 独立重跑 | **7 passed / 0 failed**（`v2-baseline-rerun.log`，EXIT=0） |

**对 reviewer 此前状态的更正**：此前复现的 5 项契约缺陷（AI maintenance 200、PATCH 缺 owner_id 200、discovery 非空 body 201、分页缺失、迁移常量 003/002）在当前 HEAD 的代码路径上均已修复，并经永久回归测试与两轮独立全量佐证。此前"未修复"判定作废。

## 3. 未闭合项（本轮独立实证，判定：不通过）

### 3.1 tool_manifest 四项 fail-open（P0 机制层）——动态复现全部确认

证据：`evidence/v1-refinal-review-20261112/manifest-failopen-repro.py`，运行结果 **ALL PASS（fail-open 全部确认存在）**，EXIT=0。每项均构造最小 manifest 场景独立验证：

| # | 复现 | 代码位置 | 实证结果 |
|---|---|---|---|
| F1 | host/shared 声明 `sha256` 可选：删除 sha256 后篡改 host runner 仍 `ok=True` | `tool_manifest.py:144,148`（`row.get("sha256")`）；`278-279`（`if expected is not None` 才校验） | 确认：`ok=True, hash_mismatch=0` |
| F2 | manifest 写 `tools: {}` 空对象绕过 `declaration_gaps`（v2 R6b 语义只查 `"tools" not in data`） | `tool_manifest.py:322` | 确认：`gaps=0`（模块目录含 host 文件仍不告警） |
| F3 | `{host_tool_dir}` 引用降级为 `undeclared_reference`：无 sha256 哈希校验、不参与依赖闭包扫描（其 `import common.x` 漏检） | `tool_manifest.py:288`（`kind != KIND_HOST_RUNNER: continue`） | 确认：`undeclared=[('run.py', None)], closure=0, ok=True` |
| F4 | 非法路径（`../` 越界）在 `_add` 中被静默丢弃，无任何告警 | `tool_manifest.py:91-93` | 确认：`ok=True, requirements=0` |

**边界说明**：真实仓库当前 manifest 均带 sha256、tools 段非空，故 F1–F4 在现网数据下不可直接触发；但 V1-08 防线的机制完整性依赖"声明即校验"，上述四个洞意味着**恶意或笔误 manifest 可静默绕过哈希校验、声明缺口与闭包扫描**。v2 基线 R6a/R6b 覆盖的"删除已声明文件"与"完全无 tools 段"两类场景确实闭合，但不能推出 fail-open 机制闭合。

### 3.2 AI 入口授权前知识读取 / LLM 调用（高严重度）——未修复

`app/api/ai_tasks.py:48-71`：先 `planner.plan(text, ...)`（第 49 行），后 `ensure_can_create_task_on_device()`（第 71 行）。而 `NLTaskPlanner.plan` 内部：

- `nl_task_planner.py:55` `get_device_knowledge(...)`——授权前查询知识库；
- `nl_task_planner.py:63-66` 条件满足时调用外部 LLM API——授权前产生外部调用与 token 消耗。

后果：对无权限设备的探测文本可在 403 之前触发知识库读取与 LLM 计费调用，属授权顺序缺陷（先授权后规划，或 planner 接收设备可见域白名单）。

### 3.3 AI 入口未复用统一任务创建服务——未修复

`ai_tasks.py:84-99` 仍自行构造 `TestTask`、自行 `db.commit()`、自行改设备状态 `testing`（第 98 行），未复用手动创建路径的统一创建服务（契约 `task-execution-v1.0.md` 要求统一收口）。后果：幂等键、201 语义、设备状态推进等契约保证在 AI 路径独立实现，存在口径漂移面（TOCTOU 竞态同理：plan→授权→写库之间无设备锁）。

### 3.4 严格全量回归不稳定——新发现

| 轮次 | 结果 | 失败项 | 隔离复跑 |
|---|---|---|---|
| reviewer 第 1 轮（backend-full.log） | 447 passed / 1 failed | `test_export_report_html`（响应体空，`<html` 不在 `''`） | 3/3 通过；模块级 12/12 通过 |
| reviewer 第 2 轮（backend-full-rerun.log） | 447 passed / 1 failed | `test_cancel_running_task_keeps_cancelled`（`running` ≠ `cancelled`） | 与 Lead STRICT-2 记录的竞态为同一测试 |

两轮失败项不同且均隔离通过，判定为**跨用例时序/异步污染类不稳定**，与开发方 STRICT-2 的竞态同源。"448 passed / 0 failed"是单轮采样结果，不是稳定结论。全量回归作为上线门禁的可信度受此影响的结论：**门禁未失效，但需先治理不稳定项**（建议：export 报告落盘与读取的竞态、cancel 状态机竞态各立项修复并加反例回归）。

### 3.5 其他维持项

| 项 | 状态 | 说明 |
|---|---|---|
| R27 Docker 干净镜像运行时 | 无法核验 | 主机无 docker；且 `check_image_tools.py:105-110` 存在验证分裂：`docker build -t test-platform:v1-08-check` 与 `docker compose up`（compose 无 `image:` 名，自行构建项目名镜像）**验证的不是同一镜像**，verified 结论力度存疑 |
| 空 test-tools 目录启动 | 不通过（维持） | `assert_required_tools` 对无 manifest 根 `ok=True`（`test_no_manifest_root_warns_but_ok` 显式断言），误配置部署静默启动 |
| discovery 响应可见性 | 契约观察项 | 契约 §5 定义发现响应返回"本次发现并完成只读同步的设备"，未要求按 owner 过滤；当前实现与契约一致。如要求普通用户不可见他人设备，属契约变更，须走 +0.1 流程 |
| U1 / U-D1 / U-V1-05 / U-V1-08 | 仍待用户决策 | 本轮无变化 |
| 配置导入 R32–R59 | 仍待用户确认 | 需求草案未确认，未实施 |

## 4. 与开发方陈述的对照

| 开发方陈述 | 复核结论 |
|---|---|
| 六项缺陷闭环（迁移/maintenance/owner_id/discovery/分页/AI maintenance 409） | **属实**（§2，七行佐证） |
| 严格全量 448 passed / 0 failed | **单轮属实、不可稳定复现**（§3.4，两轮独立全量各 1 failed） |
| "全部 P0 动态缺陷闭合" | **不属实**（§3.1 fail-open 四项 + §3.2/§3.3 AI 入口两项高严重度问题未修复） |
| 前端 56/0e/exit0 | 本轮未重跑，维持前次评审记录（V1-10 通过） |

## 5. 复核结论

1. **已闭合**：六项声称修复属实，v2 反例基线 7/7 独立复核通过，reviewer 此前相关判定更正为"通过"。
2. **未闭合**：tool_manifest 四项 fail-open（F1–F4 动态实证）+ AI 入口授权前知识/LLM 披露 + AI 未复用统一创建服务（含 TOCTOU）。
3. **新发现**：严格全量回归不稳定（两个不同测试各轮次单发失败），需治理后方可作为可信上线门禁。
4. **总体维持"不通过"**：P0 动态反例类别虽已闭合，但机制层 fail-open 与 AI 授权顺序两项高严重度问题未闭合，加上回归不稳定与既有环境/门禁项，不得签 V1.0 整体验收通过。

## 6. 修订建议（最小集，按优先级）

1. **P0**：`tool_manifest.py` 四洞修复——host/shared/device 声明强制 sha256 必填（对齐 device 现有校验）；`declaration_gaps` 增加"tools 存在但四段全空且目录有 host/二进制"判定；闭包扫描扩至 `undeclared_reference`；`_add` 对非法路径抛 `ToolManifestError` 而非静默 return。每项配反例回归。
2. **P0**：AI 入口改为先授权（设备候选确定后立即 `ensure_can_create_task_on_device`）再读知识/调 LLM；任务创建收口到统一创建服务（含幂等键与 201）。
3. **P1**：治理全量不稳定——`test_export_report_html`（落盘/读取竞态）与 `test_cancel_running_task_keeps_cancelled`（cancel 状态机竞态）各加同步/等待原语，连续 3 轮全量 0 failed 方可恢复门禁可信度。
4. **P1**：`check_image_tools.py` 补 `image:` 名使 build 与 compose 同一镜像；空 tools 根启动改拒绝（或至少告警留痕）。
5. 待用户决策项不变：U1、U-D1、U-V1-05、U-V1-08、配置导入门禁。

## 7. 签名

reviewer，2026-11-12。本轮复核未修改任何业务代码；复现脚本与全部日志存于 `evidence/v1-refinal-review-20261112/`。对"此前状态错误"的更正见 §2 末段。
