# 统一声明式配置导入需求与验收标准草案

- 文档状态：评审草案，未获用户确认，不作为实施依据
- 日期：2026-11-12
- 产出角色：requirement-reviewer
- 关联基线：`requirements-v2.3.md` R1～R31
- 建议新增编号：R32～R59 / A32～A59
- 实施门禁：D1～D9 和 A32～A59 未经用户逐项确认，不得进入正式接口设计或编码

## 1. 需求审核结论

现有 R1～R31 和接口契约没有统一配置包、dry-run、diff、apply、rollback、export 等能力。服务器本地 manifest 扫描、模块 CRUD、知识文档转换和 UPFM 专用脚本均不能替代本需求。

本草案不修改 R1～R31。下文所有边界、数值选项和接口方向均为提案，不代表用户已经批准。尤其是“自由导入”不得解释为任意上传并执行代码、脚本、二进制、SQL 或 shell。

## 2. 待用户决策项

| 编号 | 待决策内容 | 建议选项 |
|---|---|---|
| D1 | 可导入模块类型 | 建议覆盖测试模块、测试项、失败模式、基线、知识规则和 expected board profile；用户需确认精确清单 |
| D2 | config-only 边界 | 建议 V1 只迁移声明式配置，不包含也不激活执行能力 |
| D3 | 是否支持 ZIP | 建议首版仅单个 UTF-8 JSON，不支持 ZIP |
| D4 | 平台与 schema 兼容范围 | 建议仅接受明确列出的平台/schema 版本，未知版本拒绝 |
| D5 | 回滚窗口 | 需确认 before-image 保留期及到期处置；建议先采用显式保留期，不默认永久 |
| D6 | 执行能力发布审批 | 建议 V1 完全不含发布；若后续支持，使用独立权限和独立确认 |
| D7 | 数值上限 | 可选 1 MiB/16 层/1000 项，或 10 MiB/32 层/5000 项；必须由用户选定后才能验收 |
| D8 | prune 范围 | 建议 V1 不支持 prune，包中未出现的资源一律保留 |
| D9 | 冲突解决 | 建议默认同 key 不同内容整包拒绝；若允许显式覆盖，必须 diff、base_revision 和审计齐全 |

## 2.1 用户 2026-11-12 补充口径（记录用，仍待逐项最终确认，未开发）

用户在 V1 readiness 评审后补充了首版默认边界，现登记如下（与 D2/D3/D6/D8/D9 建议一致；D1 模块清单、D4 schema/平台版本、D5 回滚窗口、D7 数值上限仍待用户逐项确认）：

1. 仅接受 UTF-8 JSON 声明式配置，不支持 ZIP。
2. 禁止代码、脚本、二进制、SQL、shell 和任意附件。
3. runner 只能引用已注册的 id/version/sha256。
4. 不支持默认 prune，冲突默认整包拒绝。
5. 流程必须具备：上传、dry-run、diff、管理员确认、单事务 apply、审计、回滚、导出回环。
6. 使用稳定业务 key、resource revision、base_revision、包哈希和 Idempotency-Key。
7. 运行中和历史任务快照不得被导入或回滚改写。
8. V1 不包含执行能力发布，不自动执行测试或触碰设备。

> 状态：以上仅为用户口径记录，D1～D9 与 R32～R59/A32～A59 尚未获用户逐项确认，**不得进入接口设计或编码**。

## 3. 建议安全边界

1. 首版只接受 UTF-8 JSON 声明式数据，禁止代码、脚本、可执行文件、APK、设备二进制、SQL、shell 和任意附件。
2. runner 只能引用服务器已注册且启用的 `runner_id + version + sha256`，导入不得下载、安装或启动 runner。
3. 密钥、密码、token、用户、owner、数据库凭据、历史报告和 observed 实机画像不得进入通用导入包或导出包。
4. expected board profile 可以导入，但必须与 observed 画像分储分用；导入不得覆盖实机事实。
5. 主流程为上传、validate dry-run、diff、active admin 确认、单事务 apply、审计、包级 rollback、export round-trip。
6. 默认冲突拒绝，不静默覆盖，不默认 prune。稳定业务 key、resource revision、base_revision、全包 SHA-256 和 Idempotency-Key 均为必备约束。
7. 运行中和历史任务使用不可变快照；配置 apply/rollback 不得改变既有任务、记录、统计和报告。
8. 配置导入不得隐式发布或激活执行能力，也不得自动执行测试或触碰设备。

## 4. 需求与 GWT 验收标准草案

| 编号 | 需求 | 可测试验收标准 |
|---|---|---|
| R32 | 仅允许用户确认的模块类型和声明式配置 | A32：给定清单内与清单外资源，当 validate 时，清单内逐类返回结果，清单外返回 400 和字段路径，目标配置零写入。依赖 D1/D2。 |
| R33 | 仅接受受支持版本的 UTF-8 JSON | A33：合法包可进入 dry-run；非 UTF-8、 malformed JSON、非 object 根、未知平台/schema 版本均返回契约 4xx 和字段路径，零目标写入。 |
| R34 | 禁止主动内容 | A34：代码/脚本字段、base64 附件、SQL、shell、runner command 在上传至 apply 任一阶段均被写入前拒绝；无子进程、下载、安装或配置区外文件写入。 |
| R35 | 秘密、用户归属、历史报告和 observed 画像禁止导入导出 | A35：含 secret/password/token/owner/observed 等字段的包返回 400 且零写入；导出不含这些字段及预置秘密 canary。 |
| R36 | runner 精确匹配 allowlist | A36：完全匹配且启用才通过；缺字段、未知 id、错误 version/hash、disabled runner 均拒绝，不自动下载、安装或启动。 |
| R37 | expected 与 observed 画像分离 | A37：apply/export 后仅 expected 改变，observed 数据及哈希不变，导出不含 observed。 |
| R38 | 严格主流程且 dry-run 零业务写入 | A38：上传、validate、diff 绑定同一包哈希；除暂存和审计外 before-image 不变；跳步直接 apply 被拒绝。 |
| R39 | diff 使用稳定 key 并绑定当前状态 | A39：逐项展示 create/update/unchanged/conflict、当前/目标 revision 和安全摘要；包字节或目标 revision 改变后旧 diff 不得 apply；未声明删除不得列为 prune。 |
| R40 | active admin 确认相同包和 diff | A40：缺确认、非管理员、包改一字节、替换包、过期 diff 均拒绝并零写入；仅相同哈希和 diff 可 apply。 |
| R41 | 默认冲突拒绝且不删除既有资源 | A41：同 key 不同内容整包 409；相同内容 unchanged 且不增 revision；包内未出现的既有资源保留。 |
| R42 | 稳定业务 key 和 resource revision | A42：重名不同 key、跨环境不同内部 ID 不产生重复；引用按 key 重映射；真实更新增 revision，unchanged 重放不增。 |
| R43 | base_revision 全包乐观锁 | A43：dry-run 后任一资源被更新，旧 base_revision apply 返回 409 并整包回滚；全部匹配时只提交 diff 声明的变更。 |
| R44 | apply 强制幂等键 | A44：同键同 body 重放返回首次结果且无第二次写、revision 或 apply 记录；同键不同 body 返回 409；缺失/非法键返回 400。 |
| R45 | 并发导入无重复、脏写和半包 | A45：同键并发 10 次恰好一次 apply；不同键相同 base_revision 并发 10 次至多一个成功，其余 409；无重复、部分包或未处理 500。 |
| R46 | 所有适配器同一业务事务 | A46：逐适配器在写前、写中、适配器交界和提交前注入故障，失败后全部配置及 revision 与 before-image 一致，无孤立附件/任务/报告，并保留安全失败审计。 |
| R47 | 完整且不可由包篡改的审计 | A47：成功、拒绝、失败、rollback、export 均记录操作者、UTC 时间、动作、包哈希、结果、revision 和安全摘要；原 apply 与 rollback 均保留，审计无秘密。 |
| R48 | 窗口内包级 rollback | A48：当前 revision 仍为该 apply 结果时，单事务恢复完整 before-image、生成新 revision 并保留审计；超窗或有后续编辑返回 409 且零部分恢复。 |
| R49 | export/fresh import/export 业务等价 | A49：全范围配置在干净支持版本环境回环后，按稳定 key 比较规范化配置、引用和 expected 数据等价；仅元数据可不同，且无 R35 排除项。 |
| R50 | 不改写运行/历史任务快照和报告 | A50：配置更新、冲突导入和 rollback 后，既有任务的选中项、参数、runner、画像快照、统计、结果和报告哈希不变；仅新任务使用新配置。 |
| R51 | 全入口 active admin 授权 | A51：普通用户、disabled admin、无效/过期 token 分别返回 403/403/401，且无目标配置、apply、rollback 或导出文件变化。 |
| R52 | 不隐式发布执行能力 | A52：config-only apply 不改变发布/启用状态；未授权发布返回 403。若 D6 不支持发布，相关字段按禁止字段拒绝。 |
| R53 | 严格 JSON Schema | A53：每字段的错类型、缺必填、未知字段、非法 null、重复 JSON 成员均在写前返回 400 `VALIDATION_ERROR` 和精确 JSON 路径，不忽略未知字段，不泄露堆栈。 |
| R54 | 空包、重复 key 和上限边界 | A54：合法且等于上限的包可通过；空包、重复 key、上限+1 均确定性拒绝并零写入。具体数值依 D7。 |
| R55 | 复用严格判定、参数和依赖语义 | A55：非法正则/operator、approx_ratio 零目标、缺 source/target、非法参数、shell 控制符、缺依赖和循环依赖均写前拒绝；合法 0/false/空串/URL 保留，空规则不得变 pass。 |
| R56 | 纯 JSON 不引入解包路径风险 | A56：选择纯 JSON 时，`../`、绝对路径、反斜杠、NUL 等 key/路径样字段按 schema 拒绝且不写预期存储外文件；ZIP 穿越标“不适用：无 ZIP/解包器”，不得写通过。 |
| R57 | 错误、diff、审计和日志脱敏 | A57：秘密 canary、堆栈、SQL、服务器绝对路径、密钥和命令行细节不得出现在 API/WS、diff、审计或日志中。 |
| R58 | UI 完整展示真实流程和边界态 | A58：loading/empty/error/超长 diff/冲突/确认中/apply 失败均有真实状态；disabled/readonly/loading 不发写请求；确认前展示哈希与差异，失败不得显示成功。 |
| R59 | 生产无未标注 mock，证据真实可追 | A59：生产构建无未标注 mock；测试 mock 只能由 mock-api 按已确认契约生成并标注。回归使用隔离数据库/storage，保存命令、退出码和完整日志，受保护数据与证据哈希不变。 |

## 5. 负向路径覆盖索引

- 主流程：A33、A38～A40。
- 类型、必填、未知字段和版本：A33、A53。
- 重复 key、空包、超大、过深：A54。
- runner、正则、参数和循环依赖：A36、A55。
- 路径穿越：A56；纯 JSON 时 ZIP 项只能记“不适用+理由”。
- 普通用户、disabled、无效 token 和越权：A51。
- 重放、同键不同 body、10 并发和 revision 冲突：A43～A45。
- 每个适配器故障零部分写入：A46。
- 运行/历史快照：A50。
- 敏感字段和日志脱敏：A35、A57。
- fresh round-trip：A49。
- rollback before-image 和审计：A47、A48。
- 生产 mock：A59。

## 6. 阶段门禁

1. G1 需求门禁：D1～D9、R32～R59/A32～A59 经用户确认，补齐确认人和日期。当前不通过。
2. G2 方案与契约门禁：明确模块清单、JSON Schema、稳定 key/revision、状态流转、六要素接口、错误码和回滚语义，前后端双方确认；既有契约变更须版本号 +0.1 并追加变更记录。
3. G3 实施门禁：每个 A 编号均有实现及正常、边界、异常测试；适配器和故障注入点齐全；前端只按契约协作，mock 仅来自 mock-api。
4. G4 测试回归门禁：实际运行全量 pytest、前端 test/lint/build/隔离浏览器测试；重放、10 并发、逐适配器故障、rollback、fresh round-trip、敏感 canary 均有原始结果。
5. G5 验收门禁：A32～A59 逐条给出通过/不通过/无法核验及证据；任一不通过或无法核验则总体不通过，最终由用户验收。
