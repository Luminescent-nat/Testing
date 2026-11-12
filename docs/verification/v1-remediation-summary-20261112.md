# V1 readiness 修订轮次汇总（2026-11-12）

- 依据：[RR-V1-READINESS-20261112](../reviews/RR-V1-READINESS-20261112.md)（独立审计）与用户测试记录
- 范围：V1-01～V1-05、V1-06、V1-08、V1-09、V1-10 的 P0/P1 缺陷修订；配置导入仅按用户口径更新需求草案（[config-import-requirements-v0.1-draft](../requirements/config-import-requirements-v0.1-draft.md)），未开发
- 修订方式：Agent Team 5 路并行（task-9 授权、task-10 判定/stop/执行器、task-11/12 幂等与迁移、task-13 工具清单、task-14/21 前端、task-16/20 统计、task-18 知识、task-17 删除/409、task-19 发现改派、task-22 followup 收口），独立评审方逐项复核（RR-V1-PLAN → RR-V1-FIX-* → RR-V1-FINAL）

## 1. 最终回归（本轮判定基线）

| 项 | 命令 | 结果 | 日志 |
|---|---|---|---|
| 后端严格全量（Lead 第3轮） | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning` | **448 passed / 0 failed / exit 0（241.00s，无 ignore）** | [V1-FINAL-STRICT-3-20261112.log](tasks/V1-FINAL-STRICT-3-20261112.log) |
| 后端严格全量（Lead 第2轮） | 同上 | 447 passed / 1 failed（`test_cancel_running_task_keeps_cancelled` 计时抖动，单独重跑通过） | [V1-FINAL-STRICT-2-20261112.log](tasks/V1-FINAL-STRICT-2-20261112.log) |
| 后端严格全量（Lead 第1轮，修复前） | 同上 | 5 failed = 审计 followup 5 项缺口（随后 task-22 修复） | [V1-FINAL-STRICT-20261112.log](tasks/V1-FINAL-STRICT-20261112.log) |
| 迁移/约束演练 | `python scripts/verify_migrations.py` | **74/74 checks PASS**（HEAD=004_task_deleted_at） | tasks/T-14/verify-migrations-004-drill.log |
| 前端 | `npm test` / `npm run lint` / `npm run build` | **56 用例通过**；0 error / 994 warning（较 1037 −43）；build exit 0 | [V1-FINAL-FRONTEND-20261112.log](tasks/V1-FINAL-FRONTEND-20261112.log) |
| 6 项审计定向反例 | `test_v1_readiness_audit`（永久回归，分布在 test_v1_authorization/judgement_stop/idempotency/tool_manifest 等） | **全部 fail→pass** | 见各 RR-V1-FIX-* 独立重跑记录 |

## 2. 逐缺陷闭环情况（对照审计表）

| 审计编号 | 缺陷 | 修复与证据 | 独立评审 |
|---|---|---|---|
| V1-01 | 普通用户越权使用他人设备 | [authorization.py](../../test-platform/backend/app/services/authorization.py) 统一策略接入手动/AI/重跑/设备/报告/WS；POST /device-discoveries、PATCH 版本条件改派；审计反例 R1 403 且零写入 | [RR-V1-FIX-T03T04T05](../reviews/RR-V1-FIX-T03T04T05.md)、[RR-V1-FIX-T19V1-01](../reviews/RR-V1-FIX-T19V1-01.md) 通过（真机 discovery 端到端无法核验） |
| V1-02 | 非法规则误判通过（fail-open） | `or {}` 前按原始类型校验（[]/标量/null→error）；approx_ratio 零目标/NaN/Inf→error；写前 400（T-15）；R3/R4 fail→pass | [RR-V1-FIX-T06T07](../reviews/RR-V1-FIX-T06T07.md)、[RR-V1-FIX-T15](../reviews/RR-V1-FIX-T15.md) 通过 |
| V1-03 | stop 收尾不完整 | `_skip_remaining_items`：剩余项补 `stopped_by_item_id` skip，5 项 → pass,fail,skip,skip,skip / completed / 100% / 50.0%；R5 fail→pass | 同上 通过 |
| V1-04 | 幂等键未生效 + 201 | IdempotencyRecord UNIQUE + 服务；创建/重跑/legacy 均 201；同键同体重放同 ID、不同体 409、并发 10 至多一次；R2 fail→pass；offline/maintenance 409（D2） | [RR-V1-FIX-T10](../reviews/RR-V1-FIX-T10.md) 有条件通过（缺失键=不强幂等 待用户确认；TTL 未做） |
| V1-05 | 初始化与迁移冲突 + R20 | 生产 init_db 仅走 alembic（fresh-init 冲突消除）；初始迁移 downgrade base 非空库保护；002/003/004 additive 可逆回滚数据保留（10/98 行全程）；DDL 指纹 + WAL 一致性备份 74/74 | [RR-V1-FIX-T02](../reviews/RR-V1-FIX-T02.md) 通过（R20 revision 级）；**上线阻塞：真实库结构漂移需用户选 A/B 对账** |
| V1-06 | 统计/进度/result 口径冲突 | 单一 [statistics.py](../../test-platform/backend/app/services/statistics.py)；running/pending 不计完成；skip 不进分母、零分母 null；Dashboard today 10 键分列；前端 reports/dashboard 改后端口径（自算通过率 0 残留） | [RR-V1-FIX-T08](../reviews/RR-V1-FIX-T08.md)、[RR-V1-FIX-T08B](../reviews/RR-V1-FIX-T08B.md) 通过（浏览器实测属 T-22+/T-35） |
| V1-07 | disabled WS / 执行器异常 / 敏感信息 | WS disabled→1008；子进程启动失败→error（INTERNAL_ERROR_RC=-2）；平台异常只存安全摘要、canary 不泄露 | 随 T03T05/T06T07 通过 |
| V1-08 | 必需二进制漏检 + Docker 假 verified | manifest 显式 `tools:` 声明（runner+共享依赖+二进制 sha256），删除声明文件→启动失败、无声明模块 fatal；check_image_tools 仅真实 build 才 verified（本机 UNVERIFIABLE） | [RR-V1-FIX-T17](../reviews/RR-V1-FIX-T17.md) 通过（R27 运行时无法核验） |
| V1-09 | 知识规则/删除边界 | 写前 400（对象根/空条件/未知操作符/非法正则/零目标）；DELETE 409/软删除幂等/越权 403；item_ids 400 矩阵 | [RR-V1-FIX-T15](../reviews/RR-V1-FIX-T15.md)、[RR-V1-FIX-T14](../reviews/RR-V1-FIX-T14.md) 通过（遗留：目标项 400 vs 404、规则 DB 唯一约束、test_item legacy list 透传） |
| V1-10 | 前端仅认 200、缺 pc_identifier | 49 处 `===200`→`isSuccessResponse`（残留 0）；登录/注册注入 pc_identifier；201 兼容 | [RR-V1-FIX-T20](../reviews/RR-V1-FIX-T20.md) 通过 |

## 3. 仍不通过/无法核验（本轮后仍构成上线阻塞）

| 编号 | 事项 | 状态 |
|---|---|---|
| V1-05 | 真实 backend/test_platform.db 结构漂移（生产 init_db fail-closed） | 需用户选对账方案 A/B；真实库严禁 downgrade base |
| V1-08/R27 | 主机无 docker，干净构建/容器启动/多架构容器无法核验；ddr 无 manifest（arm64 是否属 V1 待确认） | 无法核验 |
| V1-11 | mock-api 缺失（仓库确定性脚本替代，待用户确认 U1）；lint 994 warnings、build 历史告警；浏览器 console/页面九状态/亮暗走查未做（T-22～T-34 门禁、T-35 未开始） | 未通过 |
| V1-12 | A133P 画像与实机偏差（触摸 10 点、mc_props、board=exdroid）；仅 Android10/32 位形态 | 待用户确认画像口径 |
| V1-13 | 文档回归 errors=26（12 失效链接、6 emoji 文件、8 校验器过时断言）未修 | 未通过 |
| 范围 | 未实施任务：T-09 参数矩阵、T-11 daily 模型、T-12 调度恢复、T-13 设备锁探活推进、T-16 账号闭环、T-21 组件/页面（需用户确认门禁）、T-22～T-35、T-36 画像实测、T-37/T-38 | 未开始 |

## 4. 待用户确认项（新增/延续）

| 编号 | 事项 | 建议 |
|---|---|---|
| U1 | T-20 mock 由仓库确定性脚本生成（非 mock-api） | 接受为临时口径并同步修订规则，或补 mock-api 工具 |
| U-D1 | POST /tasks 缺失 Idempotency-Key 现为“不强幂等”（契约标必填） | 确认改强制 400 或接受兼容期 |
| U-V1-05 | 真实库漂移对账：A 规范化副本重建基线 / B 显式 reconciling revision | 上线前二选一并演练 |
| U-V1-08 | arm64/DDR 是否纳入 V1 工具门禁 | 明确 ABI 矩阵后再建 DDR manifest |
| U-V1-12 | 画像期望与实机冲突口径（固件期望 vs 回归基线） | 双列记录、冲突不判 FAIL 作交付证据 |
| 配置导入 | D1～D9 与 R32～R59/A32～A59 | 用户逐项确认后方可设计/编码（本轮未开发） |

## 5. 结论

- 动态复现的 6 项 P0 缺陷（越权、幂等、fail-open×2、stop 收尾、工具漏检）已全部修复并通过永久回归 + 独立评审；初始化/迁移冲突已消除，R20 在 revision 级成立。
- 后端严格全量 **448 passed / 0 failed**（无 ignore），前端 56 用例 / lint 0 error / build exit 0。
- **总体结论仍为：不具备完整 V1.0 生产上线条件，仅可作为受控开发基线**——阻塞项为真实库对账（V1-05）、Docker 无法核验（V1-08/R27）、mock/lint/浏览器门禁（V1-11）、画像口径（V1-12）、文档回归（V1-13）以及未实施任务清单（T-09/T-11～T-16/T-21～T-38）。
- 独立评审记录：[reviews/RR-V1-FINAL-20261112.md](../reviews/RR-V1-FINAL-20261112.md)（由 reviewer 出具）。
