# 开发委派任务清单

- 版本：v1.0
- 日期：2026-11-12
- 状态规则：未开始/进行中/已完成；只有 DoD 和实际验证证据齐全才可标已完成
- 通用要求：新增正常/边界/异常测试，保存原始日志；写操作核对落库；每个任务独立变更集可单独回退
- 交接门禁：按 `docs/verification/stage1-handoff.md` 分包执行；T-22～T-34须等待新组件/页面契约和规格经用户确认，T-35等待全部前端任务完成

## T-01 统一接口错误与目标路由适配
- 改动：在 FastAPI 全局错误处理和响应模型中落地统一成功/错误外层及目标路由兼容适配。
- 依赖：无，可与 T-02/T-17/T-19/T-20 并行。
- DoD：
  - [ ] 适用异常只返回契约 `{"code","message","details"}`，校验在业务写入前，无堆栈泄露。
  - [ ] legacy 仅委托同一服务，不形成第二套权限或统计语义。
- 验证：运行新增 `test_contract_errors.py` 及现有 API 集成测试；每个适用错误码真实触发且 JSON 合法。
- 回退：单独还原错误处理与路由适配，不影响后续业务服务逻辑。
- 状态：已完成（2026-11-12；RR-T01 评审通过；证据 [docs/verification/tasks/T-01/](../verification/tasks/T-01/)、[RR-T01](../verification/reviews/RR-T01-unified-errors.md)）

## T-02 建立 Alembic 与外键迁移基础
- 改动：补齐新装/存量 Alembic 升级、SQLite 每连接外键和迁移副本验证脚本。
- 依赖：无，可与 T-01 并行。
- DoD：
  - [ ] 新装与存量副本均可到同一 head，外键/唯一约束实际生效。
  - [ ] 升级、回滚、异常路径保留行数/结构/完整性证据，不删历史记录。
- 验证：在空库和备份副本执行 upgrade/downgrade/非法关联写入，结果符合 R20。
- 回退：还原迁移基础设施并恢复演练副本，不触碰真实库。
- 状态：进行中/有条件（2026-11-12 V1 轮更新；V1-05 五项修复落地：新装仅走 alembic（无 create_all，fresh-init 冲突消除）、初始迁移 downgrade base 非空库保护、002_idempotency additive 可逆回滚数据保留（10/98 行全程保留）、verify_migrations DDL 指纹/WAL 一致性备份/74 checks PASS。[RR-V1-FIX-T02](../verification/reviews/RR-V1-FIX-T02.md) 判 R20 **revision 级可逆回滚通过**。**上线阻塞遗留**：真实 backend/test_platform.db 存在历史结构漂移（knowledge_entries 默认值/索引、test_tasks.plan/schedule_type），生产 init_db 将 fail-closed 拒绝 stamp；需用户选择对账方案 A（规范化副本重建基线）或 B（显式 reconciling revision）后方可真实库上线；真实库严禁 downgrade base。证据 [T-02](../verification/tasks/T-02/)）

## T-03 实现共享设备授权策略
- 改动：在设备服务和设备 API 中统一 owner+PC 授权、发现不认领及管理员版本改派。
- 依赖：T-01。
- DoD：
  - [ ] 列表/详情/发现/改派符合授权真值表，普通用户不能写 owner。
  - [ ] 版本条件更新、完全重放和旧版本冲突符合契约。
- 验证：运行 `test_device_authorization.py`，覆盖他人/null/PC不一致、并发10改派及落库。
- 回退：单独还原设备授权模块和对应 API。
- 状态：已完成（2026-11-12 V1 轮；[RR-V1-FIX-T03T04T05](../verification/reviews/RR-V1-FIX-T03T04T05.md)、[RR-V1-FIX-T19V1-01](../verification/reviews/RR-V1-FIX-T19V1-01.md) 评审通过：authorization.py 统一策略接入手动/AI/重跑/设备列表详情/报告/WS，POST /device-discoveries、PATCH 版本条件改派、Device.version+003 迁移；审计反例 R1 fail→pass 且零写入，14+17 真值表用例。遗留：真机 discovery 端到端无法核验。证据 [T-03](../verification/tasks/T-03/)、[T-04](../verification/tasks/T-04/)、[T-05](../verification/tasks/T-05/)）

## T-04 手动与 AI 创建复用设备授权
- 改动：将手动任务和 AI 任务创建统一接入 T-03 的设备授权后再进入任务服务。
- 依赖：T-03。
- DoD：
  - [ ] 他人、未分配、PC不一致设备均403且无任务/归属写入。
  - [ ] 合法管理员和普通用户路径均使用同一校验结果。
- 验证：运行 `test_task_device_authorization.py`，手动/AI各覆盖允许与拒绝路径。
- 回退：单独还原两个创建入口的授权接入。
- 状态：已完成（2026-11-12 V1 轮 + 2026-11-13 契约 v1.1 增补：AI 入口改为「resolve_device→设备授权 403→状态 409→知识/LLM（plan_for_device）→统一创建服务」，授权拒绝/不可用时知识与 LLM 调用计数为 0（B1/B2 永久回归）；统一创建服务 [task_creation.py](../../test-platform/backend/app/services/task_creation.py) 手动/AI 共用、AI 独立幂等 operation、成功 201；B3 差分逐字段一致。[RR-V11-FIX-B](../verification/reviews/RR-V11-FIX-B.md) 通过；交付后独立复核发现 AI 响应形状（契约 Task/201）前端未同步（跳转 task_id undefined、预览 plan TypeError），已由 task-28 修复：导航改 `res.data.id`、预览改经 `GET /tasks/{id}` 拉 `TestTaskDetail.plan`（产品决策保留面板并留痕）、纯函数+9 Vitest、三件套 65 用例/lint 992w-0e/build exit0，独立闭环通过（[RR-V11-REVIEW §4](../verification/reviews/RR-V11-REVIEW-20261113.md)）。遗留：AI 缺失幂等键不强幂等（同手动，待 U-D1）、设备不存在仍 400。证据 [T-04](../verification/tasks/T-04/)）

## T-05 报告与 WS 统一用户状态及归属
- 改动：在报告读取/导出和 WS 首消息订阅中复用 active+创建者/管理员校验。
- 依赖：T-01、T-03。
- DoD：
  - [ ] disabled和无效token不能读取或建立订阅，他人403/1008。
  - [ ] 缓存报告和批量导出不能绕过授权或静默跳过越权任务。
- 验证：运行 `test_resource_authorization.py` 与 WS 测试，覆盖五类身份和缓存路径。
- 回退：单独还原报告/WS授权适配。
- 状态：已完成（2026-11-12 V1 轮；报告读取/导出/缓存与 WS 首消息统一 authorization 校验，disabled REST 403 / WS 1008，批量导出越权整体 403 不静默跳过。证据 [T-05](../verification/tasks/T-05/)、[RR-V1-FIX-T03T04T05](../verification/reviews/RR-V1-FIX-T03T04T05.md)）

## T-06 落地失败关闭与原生 SKIP 判定
- 改动：统一执行/判定优先级，移除无配置默认pass和unknown落库，支持独立行原生SKIP。
- 依赖：无，可与 T-03 并行。
- DoD：
  - [ ] 非零、双模式命中、无配置、异常、超时符合状态机。
  - [ ] SKIP原因保留，普通相似文本不误判，rc!=0优先fail。
- 验证：运行 `test_execution_failure_closed.py` 的 EXEC-01～05/SKIP-01～02全真值表。
- 回退：单独还原判定模块，不依赖统计任务回退。
- 状态：已完成（2026-11-12 V1 轮；V1-02 两条 fail-open 关闭：`or {}` 前按原始类型校验（[]/标量/null→error）、approx_ratio 零目标/NaN/Inf/非数值→error；32 新增用例 + 审计反例 R3/R4 fail→pass。[RR-V1-FIX-T06T07](../verification/reviews/RR-V1-FIX-T06T07.md) 通过。遗留：写入侧 400 拒绝部分由 T-15 完成，执行期 error 兜底保留。证据 [T-06](../verification/tasks/T-06/)）

## T-07 补齐 stop 与任务终态聚合
- 改动：在任务执行器中补停止项后的skip记录并统一status/result/进度收尾。
- 依赖：T-06。
- DoD：
  - [ ] 剩余项不执行、不重试、不伪造输出，所有选中项形成终态。
  - [ ] completed/running残留/取消/平台异常符合状态机。
- 验证：运行 `test_stop_on_failure.py`，STOP-01/02及running残留场景全部通过。
- 回退：单独还原执行器收尾改动。
- 状态：已完成（2026-11-12 V1 轮；stop 后剩余项补 `stopped_by_item_id=<id>` skip、不执行/不重试/无输出；fail/error/timeout 三触发；审计反例 R5 fail→pass（pass,fail,skip,skip,skip / completed / 100%）；执行器启动失败→error（INTERNAL_ERROR_RC=-2）、平台异常仅存安全摘要。证据 [T-07](../verification/tasks/T-07/)、[RR-V1-FIX-T06T07](../verification/reviews/RR-V1-FIX-T06T07.md)）

## T-08 统一 WS、Dashboard 与报告统计
- 改动：让所有读模型复用五类终态、result和统一通过率，报告改为number/null及稳定字段。
- 依赖：T-07。
- DoD：
  - [ ] running不计完成，skip不进分母，零分母为null。
  - [ ] Dashboard、趋势、模块、报告和导出同一数据结果一致。
- 验证：运行 `test_unified_statistics.py`，STAT/DASH/ZERO场景及报告导出核对。
- 回退：单独还原读模型，不改变T-07落库语义。
- 状态：已完成（2026-11-12 V1 轮 + 2026-11-13 契约 v1.1 增补：单一 [statistics.py](../../test-platform/backend/app/services/statistics.py) 聚合复用（running/pending 不计完成、skip 不进分母、零分母 null、Dashboard today 10 键分列、前端改后端口径）；**HTML 导出写读竞态治理**——根因写时截断+后台重写竞窗，临时文件+fsync+os.replace 原子替换、读侧重试、缓存契约 TC-RPT-011 未放宽，20 连跑+并发重写 20 轮通过。[RR-V1-FIX-T08](../verification/reviews/RR-V1-FIX-T08.md)、[RR-V1-FIX-T08B](../verification/reviews/RR-V1-FIX-T08B.md)、[RR-V11-FIX-C](../verification/reviews/RR-V11-FIX-C.md) 通过。遗留：浏览器级页面走查与真实联调未做。证据 [T-08](../verification/tasks/T-08/)）

## T-09 修复任务参数写前校验与渲染
- 改动：按item_id嵌套标量结构统一创建校验、保存和目标项参数渲染。
- 依赖：T-04。
- DoD：
  - [ ] 非法选择/参数在任何写入前400且details字段路径准确。
  - [ ] 0/false/空串/合法URL保留，非法shell输入拒绝，参数只作用于目标项。
- 验证：运行 `test_custom_parameters_contract.py`，每字段四组非法值并核对实际命令与无新增落库。
- 回退：单独还原参数schema和渲染改动。
- 状态：已完成（2026-11-14 P0 修复轮：新建 `param_contract.py` 契约校验服务（外层键=已选 item_id 十进制串、内层参数名∈parameters_schema.properties、值白名单 string/有限number/boolean 禁 object/array/null、参数名正则、≤1000 字符、禁 NUL/CR/LF、shell 控制符拒绝 + 合法 http/https URL 放行查询字符禁凭据）；`task_creation` 精确 field 路径 400；执行侧 `validate_param_value` 值级兜底；历史"合法分组必误拒"缺陷修复（`{"12":{"target":"8.8.8.8"}}` 201）；存量扁平结构安全测试改写为嵌套。证据 [test_param_contract_v1.py](../../test-platform/backend/tests/integration/test_param_contract_v1.py) 15 用例）

## T-10 实现任务创建与重跑幂等
- 改动：增加用户范围Idempotency-Key、请求摘要唯一存储和原响应重放。
- 依赖：T-02、T-09。
- DoD：
  - [ ] 同键同请求只创建一次，同键不同请求409，不同合法请求互不干扰。
  - [ ] 并发10写无重复任务/执行，失败事务无部分落库。
- 验证：运行 `test_task_idempotency.py`，重放对比和并发10写核对数据库。
- 回退：还原幂等存储和入口接入，保留其他任务字段迁移。
- 状态：已完成/有条件（2026-11-12 V1 轮；IdempotencyRecord+UNIQUE、POST /tasks、/tasks/{id}/reruns、legacy rerun-failed 均 201 且复用幂等；同键同体重放同 ID、不同体 409、并发 10 至多一次；审计反例 R2 fail→pass。[RR-V1-FIX-T10](../verification/reviews/RR-V1-FIX-T10.md) 有条件通过：**缺失 Idempotency-Key=不强幂等（待用户确认是否强制必填）**、TTL 清理未做；offline/maintenance 已按 D2 改 409。证据 [T-10](../verification/tasks/T-10/)）。**2026-11-14 U-D1 已确认强制必填**：缺键 400 VALIDATION_ERROR（零任务零幂等记录写入），`resolve_idempotency_key` 收紧；前端 client.js 拦截器已自动带键（T-20 既有），conftest `_IdempotencyTransport` 对齐补键 + `X-Test-No-Idempotency-Key` 标记验证缺键 400。遗留：TTL 清理未做。

## T-11 增加 daily 模板/实例数据模型
- 改动：增量增加task_kind/template_id/scheduled_for/快照状态及计划时刻唯一约束。
- 依赖：T-02、T-07。
- DoD：
  - [ ] 模板与实例可区分，历史无快照标legacy，不伪造配置。
  - [ ] 唯一约束由数据库执行，迁移前后历史行数一致。
- 验证：运行 `test_daily_schema.py` 和存量副本迁移，重复计划插入被约束拒绝。
- 回退：执行对应down迁移并核对原结构/数据。
- 状态：已完成（2026-11-14 P0 修复轮：005 迁移原生 ALTER ADD COLUMN（task_kind server_default='instance'/template_id 自引用外键/scheduled_for/item_snapshot/item_snapshot_status）+ `uq_task_template_scheduled_for` 唯一索引（NULL 行不参与冲突，免表重建避开 004 已证 FK 失败）+ `ix_test_tasks_task_kind`；模型 Index/ForeignKey/server_default 与迁移 DDL 指纹逐项对齐；快照服务 `task_snapshot.py` 创建时固化测试项执行配置（历史无快照 legacy 不反填）。证据 [test_daily_templates_v1.py](../../test-platform/backend/tests/integration/test_daily_templates_v1.py)、[test_v1_migration.py](../../test-platform/backend/tests/unit/test_v1_migration.py) 10 用例）

## T-12 实现 daily 触发与重启恢复
- 改动：调度器按最近计划时刻创建独立实例并处理并发、跨天和未到期恢复。
- 依赖：T-11、T-13。
- DoD：
  - [ ] 持续触发且历史独立，前次running时新实例pending。
  - [ ] 并发10扫描至多一个实例，重启不重复、不逐日补跑。
- 验证：运行 `test_daily_scheduler.py` 两个时刻、并发、重启、跨天及非法时间用例。
- 回退：单独还原调度算法，保留T-11 additive字段。
- 状态：已完成（2026-11-14 P0 修复轮：调度器按契约 §2 六步重写——事务内算"不晚于 now 的最近计划时刻"、查重+唯一索引双兜底（IntegrityError 回滚后重载模板仅推进 next_run_at）、跨天不补跑、取消/删除模板不再触发；Dashboard/报告汇总排除 daily_template；列表 task_kind 过滤（instance/daily_template/all，默认 instance，非法 400）；daily 创建响应 201 "daily 模板创建成功"。证据 [test_daily_templates_v1.py](../../test-platform/backend/tests/integration/test_daily_templates_v1.py) 8 用例含 10 连扫与跨天）

## T-13 修复设备锁持有者及探活状态推进
- 改动：设备状态只由当前锁持有者或有效探活推进，ADB失败不再等同空列表。
- 依赖：T-03、T-07。
- DoD：
  - [ ] A执行B排队/旧收尾/刷新/心跳交错不释放错锁、不覆盖testing。
  - [ ] ADB异常保持状态并返回真实错误，不批量offline。
- 验证：运行 `test_device_state_ownership.py`，并发与故障注入后核对锁和数据库状态。
- 回退：单独还原锁与状态推进逻辑。
- 状态：已完成（2026-11-14 P0 修复轮：心跳链路 `heartbeat_check` 改走 `get_device_list` (devices, error) 契约——ADB 可执行失败/超时/非零退出/抛异常一律"探测失败"：保持全部设备现状（含 testing/online）零状态变更并记安全错误，绝不批量 offline；仅可信空扫描可推进非 testing/maintenance 状态；testing 心跳不再覆盖（TC-HEARTBEAT-001 断言反转 + 新增 TC-HEARTBEAT-006 故障注入）。证据 [test_device_heartbeat.py](../../test-platform/backend/tests/unit/test_device_heartbeat.py)）

## T-14 统一取消、软删除与启动恢复
- 改动：实现取消等待收尾、终态软删除幂等及未到期调度恢复保护。
- 依赖：T-07、T-12、T-13。
- DoD：
  - [ ] 取消无running/子进程残留，running删除409，软删除证据引用一致。
  - [ ] 重启不动未到期pending，旧收尾不覆盖cancelled。
- 验证：运行 `test_task_lifecycle.py` 各状态取消/删除/重启和越权路径。
- 回退：单独还原生命周期逻辑，保留其他迁移。
- 状态：已完成（2026-11-12 V1 轮 + 2026-11-13 契约 v1.1 增补：DELETE 软删除/409/幂等/越权、item_ids 400、004 迁移；**cancel 竞态治理**——状态推进全部条件更新（输掉竞态零写入、不调度报告/记忆体）、cancel 端点预检后条件更新+幂等语义保持、收尾移出异常作用域（根治 CancelledError 钉帧致收尾 BUSY）、cancel_task 单次投递、conftest WAL+busy_timeout（Lead 授权）；20 连跑双路径+并发 10 多轮全绿、全量连续 2 轮 467 passed。[RR-V11-FIX-C](../verification/reviews/RR-V11-FIX-C.md) 通过。证据 [T-14](../verification/tasks/T-14/)）

## T-15 统一知识转换条件规则结构
- 改动：预览/转换/执行共用conditional_rules对象schema并在写前拒绝非法规则。
- 依赖：T-06。
- DoD：
  - [ ] dict不再被转换成list写入，合法conditions确定pass/fail。
  - [ ] list/标量/未知操作符/空规则/非法正则均400且无资产写入。
- 验证：运行 `test_knowledge_rule_contract.py`，预览、转换、执行和重复规则幂等通过。
- 回退：单独还原知识转换schema和校验。
- 状态：已完成（2026-11-12 V1 轮；唯一 validate_conditional_rules：对象根+conditions 非空、非法正则/未知操作符/缺字段/零目标写前 400 零资产写入且 details.field 精确；“对象包成 list”已删除，执行期 error 兜底保留。[RR-V1-FIX-T15](../verification/reviews/RR-V1-FIX-T15.md) 通过。遗留：目标项不存在当前 400（契约 404 待收口）、规则 DB 唯一约束、test_item legacy list 透传。证据 [T-15](../verification/tasks/T-15/)）

## T-16 完成账号生命周期 API 闭环
- 改动：实现首管理员、会话、管理员建号、角色/状态更新及最后管理员保护的目标契约。
- 依赖：T-01。
- DoD：
  - [ ] 首注册后公开建号关闭，后续仅管理员创建且密码不回显。
  - [ ] 禁用REST/WS生效，同名并发和最后管理员并发安全。
- 验证：运行 `test_user_administration_contract.py`，核对实际落库、重放、并发10和禁用路径。
- 回退：单独还原账号API及校验，不影响其他资源。
- 状态：已完成（2026-11-14 P0 修复轮：新建 `user_admin.py` 服务——`POST /auth/registrations` 首管理员初始化（201 强制 admin、空库检查+IntegrityError→409 并发兜底、携带 role/status 400 extra=forbid）、`POST /users` 管理员建号（201/重名 409/非管理员与 disabled 403）、`PATCH /users/{id}` 与 legacy PUT 同函数（最后 active 管理员禁用/降级 409、事务内重查防并发、空对象/未知字段 400、幂等相同值 200；DELETE 软删除复用保护）、reset-password 改请求体（URL query 不再接受，前端 user.js 同步改 body）。证据 [test_user_administration_v1.py](../../test-platform/backend/tests/integration/test_user_administration_v1.py) 14 用例）

## T-17 让干净镜像包含声明工具
- 改动：修正Docker构建上下文/镜像复制和启动工具清单校验。
- 依赖：无。
- DoD：
  - [ ] manifest声明的runner和二进制在干净镜像可发现。
  - [ ] 必需工具缺失明确失败，范围内APK/外设缺失如实skip。
- 验证：干净构建/启动并导出工具清单和镜像内路径，保存完整日志。
- 回退：单独还原Docker与发现校验改动。
- 状态：已完成（2026-11-13 契约 v1.1 轮：§6.1 A1~A5 五规则落地——host/shared sha256 必填、空 tools 段判缺口、`{host_tool_dir}` 引用必须显式声明（废除 undeclared 降级）、非法路径硬失败、空 TEST_TOOLS_PATH 拒绝启动；F1~F4 销项 9/9 CLOSED（[manifest-failopen-repro-v2](../verification/tasks/T-17/manifest-failopen-repro-v2.py)）；真实仓库 --validate ok=true；compose image 与 check_image_tools tag 对齐（task-D）。[RR-V11-FIX-A](../verification/reviews/RR-V11-FIX-A.md) 通过。遗留：本机无 docker 干净构建无法核验；ddr/ABI 矩阵待用户。证据 [T-17](../verification/tasks/T-17/)）

## T-18 拒绝弱默认密钥
- 改动：启动校验拒绝空、短密钥和契约列出的占位值且不打印密钥。
- 依赖：T-01。
- DoD：
  - [ ] 合法密钥启动，弱/占位密钥启动失败。
  - [ ] 文档示例与实际校验一致，错误日志不泄露值。
- 验证：运行 `test_secret_strength.py` 并实际执行合法/非法启动矩阵。
- 回退：单独还原密钥校验和文档示例。
- 状态：已完成（2026-11-12；RR-T18 评审通过：8 类弱/占位/短密钥启动 exit=3 拒绝、合法密钥与 fresh 空库 /health=200、错误不打印密钥；容器内 compose `${SECRET_KEY:?}` 展开因无 docker 未核验。证据 [T-18](../verification/tasks/T-18/)、[RR-T18](../verification/reviews/RR-T18-weak-secret.md)）

## T-19 移除 ADB runner shell 拼接
- 改动：test-tools公共runner改用参数数组并处理空参数、失败和超时。
- 依赖：无。
- DoD：
  - [ ] 不使用shell=True拼接，合法参数保持原义，元字符不被解释为命令。
  - [ ] 异常输出和返回码可追踪，正常路径不回归。
- 验证：运行test-tools新增正常/边界/异常测试并检查实际调用参数。
- 回退：单独还原公共runner及测试。
- 状态：已完成（2026-11-12；RR-T19 评审通过：全参数数组 shell=False、shell(str) 兼容签名、30+ 调用方零改动、真机只读 7/7、25 单测。证据 [T-19](../verification/tasks/T-19/)、[RR-T19](../verification/reviews/RR-T19-adb-runner.md)）

## T-20 建立前端契约客户端与生成 mock
- 改动：按契约v1.0统一API路径、错误解析、幂等键并用mock-api生成开发mock。
- 依赖：无；不得等待后端时自编数据。
- DoD：
  - [ ] 请求/响应类型与契约一致，错误details可读，0/false/null不丢失。
  - [ ] mock明确标注且只用于隔离开发/测试，可切换真实API。
- 验证：运行API client Vitest和mock契约样例，覆盖正常、错误、重放键。
- 回退：单独还原客户端与生成mock，不影响页面业务。
- 状态：已完成/有条件（2026-11-12 V1 轮；V1-10 收口：49 处散落 `code===200` 全部改 `isSuccessResponse`（残留 0）、登录/注册注入 pc_identifier、200/201 双码兼容、重复提交守卫；RR-T20 有条件项剩 mock-api 偏差 U1 待用户确认；lint 994w/0e（T-35 前端门禁未清）。证据 [T-20](../verification/tasks/T-20/)、[RR-V1-FIX-T20](../verification/reviews/RR-V1-FIX-T20.md)）

## T-21 映射已确认 UI token
- 改动：将双主题token v1.0映射到主题变量并移除共享样式中的冲突裸值。
- 依赖：无；token已确认。
- DoD：
  - [ ] 七色、六字号、间距、圆角、阴影及扩展token均来自确认表。
  - [ ] 亮暗主题无表外魔法值，间距均4倍数。
- 验证：运行样式静态检查和构建，输出token差异及实测核心对比度。
- 回退：单独还原主题变量映射。
- 状态：已完成（2026-11-12；RR-T21 评审通过（静态 token 范围）：七色+扩展色/字号/间距/圆角/阴影/焦点环与 token 表逐值一致，共享样式裸值 0、18 组对比度达标；浏览器亮暗主题逐页走查属 T-22+。证据 [T-21](../verification/tasks/T-21/)、[RR-T21](../verification/reviews/RR-T21-ui-tokens.md)）

## T-22 实现共享组件契约与九状态
- 改动：实现StatusTag、BoundaryState、MetricCard、TaskProgress、DeviceSelect、ReportSummary共享组件。
- 依赖：T-20、T-21，且用户确认新组件props契约和六段规格。
- DoD：
  - [ ] props/state/events/slots严格对照确认表，无契约外事件或any。
  - [ ] 九状态、四边界态、键盘、亮暗主题可实际触发。
- 验证：运行共享组件Vitest和Playwright状态矩阵，console 0 error/0 warning。
- 回退：单独还原共享组件，保留token与API client。
- 状态：未开始

## T-23 改造任务列表与创建页
- 改动：任务列表/创建接入新契约、参数校验、兼容性和四边界态。
- 依赖：T-09、T-10、T-22。
- DoD：
  - [ ] 合法创建/重放/错误字段路径正确，非法设备不能提交。
  - [ ] Android9/10/10.1及各兼容性维度、空非法版本展示正确。
- 验证：运行任务页Vitest/Playwright，覆盖参数、调度、empty/error/超长和移动端。
- 回退：单独还原任务列表/创建页。
- 状态：未开始

## T-24 修复任务监控 WS 生命周期
- 改动：监控页使用统一进度模型并在卸载/结束/认证失败时完整清理连接与timer。
- 依赖：T-08、T-22。
- DoD：
  - [ ] running不计完成，skip/timeout/null正确展示。
  - [ ] 连续进出5次无残留timer、重复日志或多余连接。
- 验证：运行监控页组件测试和Playwright资源计数，覆盖断线/认证失败/结束。
- 回退：单独还原监控页及WS客户端生命周期。
- 状态：未开始

## T-25 统一仪表盘与报告对比展示
- 改动：仪表盘和报告页使用统一五类统计、item_id对比和真实零值格式化。
- 依赖：T-08、T-22。
- DoD：
  - [ ] null不显示0%/100%，各任务状态分列，导出行为一致。
  - [ ] 重名不同ID不互换，0显示0，无对应项标不可对比。
- 验证：运行报告/仪表盘Vitest和Playwright，STAT/DASH/ZERO场景通过。
- 回退：单独还原两个页面，不影响后端统计。
- 状态：未开始

## T-26 实现管理员用户页面
- 改动：用户管理页接入建号、角色/状态、禁用及四边界态。
- 依赖：T-16、T-22。
- DoD：
  - [ ] 管理员可建号/禁用，普通用户无入口且服务端仍拒绝。
  - [ ] 表单错误、最后管理员冲突、disabled和readonly不触发错误写。
- 验证：运行用户页Playwright及API联调，核对落库和错误响应。
- 回退：单独还原用户页面。
- 状态：未开始

## T-27 补齐模块页边界与状态
- 改动：模块页按组件规格实现四边界态、九状态和键盘操作。
- 依赖：T-22。
- DoD：
  - [ ] loading/empty/error/超长均可触发，长模块名不横向滚动。
  - [ ] 表单禁用/loading不重复写，错误码展示准确。
- 验证：运行模块页Playwright状态矩阵和键盘走查。
- 回退：单独还原模块页。
- 状态：未开始

## T-28 补齐 AI 测试页闭环
- 改动：AI页复用授权任务创建、明确降级/错误并补四边界态。
- 依赖：T-04、T-22。
- DoD：
  - [ ] 无LLM和非法规划不伪造成功，设备拒绝不产生任务。
  - [ ] 长输入、空结果、错误和重复提交状态正确。
- 验证：运行AI页mock契约测试和真实API联调，核对任务落库。
- 回退：单独还原AI页面。
- 状态：未开始

## T-29 补齐记忆体页边界与零值
- 改动：记忆体页按规格统一分页、空态、错误和真实数值显示。
- 依赖：T-22。
- DoD：
  - [ ] 长文本、空数据、请求失败不破坏布局，0不显示为缺失。
  - [ ] Tab/筛选/分页状态与API一致。
- 验证：运行记忆体页Playwright与键盘走查。
- 回退：单独还原记忆体页。
- 状态：未开始

## T-30 补齐知识库与规则预览页面
- 改动：知识库页接入合法规则预览/转换错误及四边界态。
- 依赖：T-15、T-22。
- DoD：
  - [ ] 非法规则不写资产且字段错误可见，合法预览与落库一致。
  - [ ] 长文档/空搜索/解析失败/长预览均可操作且无横向滚动。
- 验证：运行知识库页Playwright和转换联调，覆盖键盘与异常路径。
- 回退：单独还原知识库页面。
- 状态：未开始

## T-31 补齐个人信息页状态与安全
- 改动：个人信息页实现资料/密码操作的加载、错误、只读和防重复提交。
- 依赖：T-22。
- DoD：
  - [ ] 错误密码/禁用用户/网络失败提示准确，密码不回显。
  - [ ] readonly/disabled不写，长用户名不破坏布局。
- 验证：运行个人信息页Playwright与API异常矩阵。
- 回退：单独还原个人信息页。
- 状态：未开始

## T-32 补齐登录与404页面
- 改动：登录和404页实现双主题、表单边界、键盘及导航反馈。
- 依赖：T-16、T-22。
- DoD：
  - [ ] 首管理员/普通登录/disabled/错误凭据状态准确，密码不泄露。
  - [ ] 404可键盘返回，空/错误/超长路径不横向滚动。
- 验证：运行登录/404 Playwright和可访问性走查。
- 回退：单独还原登录/404页面。
- 状态：未开始

## T-33 完成主布局响应式与可访问性
- 改动：主布局实现三档导航、焦点、主题切换和reduced-motion。
- 依赖：T-22。
- DoD：
  - [ ] 三档断点无横向滚动，移动菜单焦点圈定/返回正确。
  - [ ] Tab顺序、焦点环、aria、200%缩放和键盘导航符合规格。
- 验证：亮暗主题6宽度截图、Tab/Escape/reduced-motion实际走查。
- 回退：单独还原主布局。
- 状态：未开始

## T-34 完成设备页发现与授权交互
- 改动：设备页实现手动发现、授权改派、兼容性和四边界态。
- 依赖：T-03、T-22。
- DoD：
  - [ ] 首屏不自动扫描，普通用户无改派能力，发现失败不显示为空成功。
  - [ ] loading/empty/error/超长画像及各兼容性组合正确。
- 验证：运行设备页Playwright，核对发现调用次数、改派落库和键盘操作。
- 回退：单独还原设备页面。
- 状态：未开始

## T-35 清零前端工程警告
- 改动：治理lint、Vite CJS、Sass legacy API和大chunk警告及剩余console问题。
- 依赖：T-20～T-34全部完成。
- DoD：
  - [ ] lint 0 error/0 warning，build退出码0且无既定类别警告。
  - [ ] 未通过关规则、删文件、隐藏console或删除测试达标。
- 验证：实际运行npm test/lint/build和完整Playwright，保存完整输出。
- 回退：按配置/代码变更集单独还原，不回退页面功能任务。
- 状态：未开始

## T-36 完成 UPFM 事实来源与画像测试
- 改动：统一manifest/seed/导入入口并补板型识别、画像来源和异常恢复测试。
- 依赖：T-06、T-17、T-19。
- DoD：
  - [ ] T1-01～27与38源用例无缺失重复，runner/二进制/判定配置一致。
  - [ ] 空属性/失败/冲突/未知板型/缺字段/SKIP有测试，期望来源明确。
- 验证：运行UPFM静态与单元回归，输出静态矩阵；实机另按R3记录或标无法核验。
- 回退：单独还原UPFM manifest/profile/runner变更，不删历史证据。
- 状态：未开始

## T-37 更新文档与受保护资产清单
- 改动：同步活跃文档、历史标识、实际测试数、部署命令和逐项清理/保留清单。
- 依赖：T-01～T-36相关实现完成。
- DoD：
  - [ ] 文档与当前实现一致，追踪矩阵更新真实状态和证据链接。
  - [ ] 库/备份/上传/报告/日志/archive逐项分类并复核哈希，无整批误删。
- 验证：运行文档链接/结构检查、命令抽跑及受保护哈希对照。
- 回退：单独还原文档和清单，不回退业务代码。
- 状态：未开始

## T-38 独立全量回归与最终验收
- 改动：验收方按验证规则重跑并出具R1～R31验收报告，不产生业务实现改动。
- 依赖：T-01～T-37全部有证据。
- DoD：
  - [ ] 后端/前端/浏览器/迁移/Docker/UPFM证据独立复核，P0异常和写重放抽查完成。
  - [ ] R1～R31逐条通过/不通过/无法核验，结论与证据一致。
- 验证：执行 `verification-rules-v1.0.md` 全套规则；任一项不通过或无法核验则总体不通过。
- 回退：不适用；验收失败退回对应实现任务，整改后重验。
- 状态：未开始

## 执行顺序汇总

1. 可立即并行：T-01、T-02、T-06、T-17、T-19、T-20、T-21。
2. 授权/执行/账号主线：T-03→T-04→T-05；T-06→T-07→T-08；T-16。
3. 参数/调度主线：T-09→T-10；T-11与T-13→T-12→T-14；T-15可并行。
4. 前端：T-22经新组件文档确认后启动，随后T-23～T-34，最后T-35。
5. 收尾：T-36→T-37→T-38。发现依赖冲突立即暂停并更新任务板，不得跳门禁。
