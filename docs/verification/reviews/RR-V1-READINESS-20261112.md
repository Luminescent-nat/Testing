# RR-V1-READINESS：V1.0 整体上线与配置导入独立审计

- 评审日期：2026-11-12
- 评审对象：平台 V1.0 整体上线可行性、批次 G 陈述、各模块配置导入目标
- 审计 HEAD：`fa70d3b2a45e3d9947d1c5b229aadea760f4e18b`
- 审计方式：独立全量回归、隔离定向复现、关键代码与契约静态复核
- 总体结论：**不通过，不得作为完整 V1.0 生产版本上线**
- 配置导入需求：[R32～R59 草案](../../requirements/config-import-requirements-v0.1-draft.md)，未获用户确认，不得直接实施

## 1. 结论摘要

当前版本可以保留为受控开发基线，但不具备生产发布条件。原因不是单纯“任务数量不足”，而是已经实际复现了越权创建任务、幂等失效、非法规则误判通过、stop 收尾不完整、迁移路径冲突和必需工具漏检。

开发方原任务板记录为 5 项完成、3 项未闭环、30 项未开始。本轮定向复现证明 T-06 仍存在 fail-open，应撤回“无条件完成”。因此按本轮结果建议调整为：

| 状态 | 数量 | 任务 |
|---|---:|---|
| 限定范围内可保留完成 | 4 | T-01、T-18、T-19、T-21；不得外推为对应全部 R 项完成 |
| 未闭环或应重开 | 4 | T-02、T-06、T-17、T-20 |
| 未开始 | 30 | 其余任务 |

本报告没有直接修改任务板；正式状态变更须由开发方修订并重新评审。上述数量不是工作量百分比，也不是上线完成度。

“各模块自由导入配置”当前没有统一实现。现有 manifest 扫描、CRUD、工具上传、知识转换和 UPFM 专用脚本缺少统一包格式、版本、事务、冲突、审计、回滚和导出回环，不能宣称已经满足。

## 2. 独立运行证据

| 项目 | 实际结果 | 判定 |
|---|---|---|
| 后端全量 | 310 项收集，`310 passed in 130.18s`，退出码 0 | 既有套件通过，但存在覆盖盲区 |
| 新增定向契约复现 | 6 项，`6 failed in 2.55s`，退出码 1 | 六类缺陷均实际复现 |
| 幂等专项 | 同键两次请求返回任务 ID 1 和 2，退出码 1 | 重复创建确认 |
| 新装后迁移 | `create_all` 成功，随后 `alembic upgrade head` 报 `table users already exists`，退出码 1 | 初始化/迁移冲突确认 |
| 前端测试 | 3 个文件、33 个用例通过 | 仅既有测试范围通过 |
| 前端 lint | 0 error、1037 warning，退出码 0 | 不满足最终 0 warning 门禁 |
| 前端构建 | 退出码 0；有 Vite CJS、Sass legacy API、大于 500 kB chunk 警告 | 可构建不等于发布门禁通过 |
| token 静态检查 | 差异 0、裸值 0、18 组静态对比度通过 | 只证明静态 token，不证明页面可访问性完成 |
| ADB | 一台 A133P 在线，Android 10/SDK29/armeabi-v7a | 未做任何设备写操作；覆盖矩阵仍不足 |
| Docker | `docker: command not found`，退出码 127 | R27 无法核验 |
| 文档回归 | errors=26：12 个失效链接、6 个 emoji 文件、8 个旧校验器误报 | 前 18 项需修，后 8 项需更新校验器 |

原始证据：

- [后端全量](evidence/v1-readiness-20261112/backend-full.log)
- [六项定向复现](evidence/v1-readiness-20261112/targeted-defect-repro.log)
- [定向复现源码](evidence/v1-readiness-20261112/targeted-defect-repro.py)
- [幂等专项](evidence/v1-readiness-20261112/idempotency-repro.log)
- [新装后迁移](evidence/v1-readiness-20261112/fresh-init-then-upgrade.log)
- [前端测试](evidence/v1-readiness-20261112/npm-test.log)、[lint](evidence/v1-readiness-20261112/npm-lint.log)、[build](evidence/v1-readiness-20261112/npm-build.log)、[token](evidence/v1-readiness-20261112/check-tokens.log)
- [ADB 在线状态](evidence/v1-readiness-20261112/adb-devices.log)、[Docker 环境](evidence/v1-readiness-20261112/docker-version.log)
- [文档回归](evidence/v1-readiness-20261112/documentation-regression.log)、[新增文档后复跑](evidence/v1-readiness-20261112/documentation-regression-after-audit.log)

新增审计报告和需求草案参与复跑后，检查范围增至 77 个 Markdown、46 个 JSON 示例和 243 个链接目标，errors 仍为 26，未引入新增文档错误；既有 26 项仍未关闭。

定向复现只使用临时 SQLite、临时目录和 Mock ADB。临时测试文件已移出业务测试目录并保存为证据，未修改业务实现，未接触真实数据库或设备。

## 3. 上线阻塞项与修订要求

### V1-01 普通用户可越权使用他人设备创建任务

- 严重度：P0；证据：动态复现 + 静态复核。
- 实现：`test-platform/backend/app/api/tasks.py:32-35` 只按 serial 查设备，`:75-95` 直接创建并启动；没有 owner/PC 校验。
- 动态结果：普通用户对 admin 所有且异 PC 的设备创建任务，实际返回 HTTP/body 200，契约应为 403 且零任务写入。
- AI 路径 `app/api/ai_tasks.py:60-92` 同样直接写任务；重跑也需要重新校验当前设备授权。
- 修订：完成 T-03/T-04，手动、AI、重跑共用同一服务端授权策略；增加他人、null owner、PC 不一致、设备改派后重跑和零写入测试。不得只隐藏前端按钮。

### V1-02 T-06 仍有两条 fail-open 路径

- 严重度：P0；证据：动态复现。
- `conditional_rules=[]` 被 `execution_engine.py:233-236` 和 `judgement_engine.py:635-644` 的 `or {}` 归一化为空对象，随后 `pass_pattern` 命中，实际得到 pass，契约应为 error。
- `approx_ratio` 在 `judgement_engine.py:465-468` 把零目标偏差强制设为 0，`actual=100,target=0,tolerance=0%` 实际得到 pass；契约明确禁止零目标。
- 修订：先校验原始 JSON 类型，再做默认值处理，禁止用 truthiness 擦除非法 falsy 类型；模块、知识转换和未来导入写入时统一拒绝零目标、NaN/Inf、非法数值比较，运行时仍须 error 兜底。补数组/标量/null、零目标、非数值、双模式和 API 落库测试。T-06 应重开。

### V1-03 stop-on-failure 伪造完整收尾

- 严重度：P0；证据：动态复现。
- `task_executor.py:205-214` 遇 stop 只 break，随后无条件 completed/100%，没有补剩余 skip。
- 动态结果：5 项中第 2 项 fail+stop，实际记录只有 `pass,fail`，缺少后三项 `skip`。
- 修订：完成 T-07；剩余项创建带原因和 stopped_by_item_id 的 skip，不执行、不重试、不伪造输出；核对 C=N、progress=100、pass_rate=50.0。补 fail/error/timeout 三种触发及取消、平台异常、running 残留测试。

### V1-04 创建/重跑幂等未实现且成功码不符契约

- 严重度：P0；证据：动态复现。
- `tasks.py:24-30` 没有 Idempotency-Key 参数和摘要存储；`:107-111` 返回 200 而非 201。
- 动态结果：相同键和相同 body 连续请求，实际生成任务 ID 1 和 2。
- 修订：完成 T-11；持久化用户、操作、幂等键、请求规范化哈希、响应和任务 ID，数据库唯一约束兜底；同键同体重放返回首次结果，同键不同体 409，并发 10 次只执行一次。创建/重跑统一 201，设备不可用等冲突按契约 409。不得只在前端生成请求头而后端忽略。

### V1-05 新装、存量、回滚三条数据路径均未闭环

- 严重度：P0；证据：动态复现 + 既有 R20 不通过记录 + 静态复核。
- `database.py:74-83` 正常启动仍 create_all，且不写 alembic_version。本轮在隔离空库复现：初始化成功后 `alembic upgrade head` 因 users 已存在失败。
- `verify_migrations.py:318-331` 只比较表名就 stamp head，未逐列、索引、FK、CHECK 对比；`:310-316` 只复制主 db 文件，未形成含 WAL 的一致性备份。
- 已确认 `downgrade base` 使存量副本任务/记录从 10/98 变成 0/0，R20 不通过。
- 修订：
  1. 生产新装只走 Alembic upgrade，不再由应用 create_all 建一套未登记结构。
  2. 已应用迁移历史不重写；后续 additive revision 必须支持 head 到前一兼容 revision 的真实可逆回滚。
  3. 对非空库的 downgrade base 加代码防护，不靠文档警告；禁止 no-op downgrade 伪造数据保留。
  4. stamp 前做完整 DDL 指纹对比，增加“同表名不同 DDL”反例。
  5. 使用 SQLite 一致性备份机制，覆盖 WAL 中已提交数据，核对行数、结构、约束、完整性和哈希。
  6. 全量灾难恢复使用版本化备份 SOP，但不能替代包级或 revision 级回滚证据。
  7. 真实库严禁执行 `alembic downgrade base`。

### V1-06 统计、进度和任务 result 仍使用冲突口径

- 严重度：P0；证据：静态复核，需在 T-08 做端到端动态矩阵。
- `schemas.py:340-354` 不看任务 status，仅按已有记录推 result，running/cancelled/平台 failed 可能出现业务 passed/failed。
- `websocket.py:104-127` 把 running 加入 completed_items，并把 pending 放入完成结果，消息缺 counts/pass_rate/result。
- `reports.py:212-217` 使用 passed/total，skip 被纳入分母，全 skip 返回字符串 `0%`；`:1200-1258` 趋势和模块统计也不统一。
- `dashboard.py:34-55` 把所有 completed 当 passed，并把平台 failed/cancelled 纳入失败和通过率分母。
- 修订：完成 T-07/T-08，以同一聚合函数服务任务详情、列表、WS、Dashboard、报告和导出；覆盖全 skip、skip+pass、零记录、running、pending、cancelled、平台 failed 真值表。零有效分母必须为 number null，不得为 0 或字符串。

### V1-07 disabled 用户 WS、执行器异常和敏感信息仍有绕行路径

- 严重度：P0；证据：静态复核。
- `websocket.py:185-202` 校验用户存在和归属，但不检查 `user.status`，disabled 用户的未过期 token 仍可订阅。
- `device.py:300-302` 把包括子进程启动失败在内的异常转为 rc=-1；`execution_engine.py:360-370` 除超时外走普通非零判定，主机 adb 不存在可能被判 fail 而非执行器 error。
- `task_executor.py:119-121`、`:478-480` 将原始异常持久化，`schemas.py:360-364` 可在 200 详情中返回，绕过全局 500 脱敏。
- 修订：T-05 增加 active 校验和 disabled 1008；区分设备测试失败与执行器无法启动；平台异常只保存安全摘要，详细堆栈仅进入受控服务端日志。补真实 ADBService 路径、异常落库后详情读取和敏感 canary 测试。

### V1-08 工具清单会漏掉被删除的必需二进制，Docker 检查还可能产生假证据

- 严重度：P0；证据：动态复现 + 静态复核。
- `tool_manifest.py:113-129` 通过 glob 现存二进制来生成“必需清单”。定向复现中，文件存在时清单有条目，删除后清单变 `{}`，启动校验无法发现缺件。
- 清单未覆盖 runner 的共享 Python 依赖闭包，公共模块丢失可能到执行时才暴露。
- `check_image_tools.py:88-103` 只检测 docker 命令是否存在；存在时会打印 `docker build/start verification: verified`，但未实际 build/start。
- 当前主机无 Docker，R27 仍未核验。
- 修订：manifest 显式声明每个必需 runner、共享依赖、设备二进制、ABI、version 和 SHA-256；删除任一文件必须启动失败。Docker 检查只有真实 build/start/容器内发现成功才能写 verified，否则 UNVERIFIABLE。补做 no-cache build、compose 启动、/health、工具发现、弱密钥拒绝和新旧数据卷迁移。明确 arm64 是否属于 V1；若属于，DDR 工具和实测必须补齐。

### V1-09 知识转换与删除/创建边界仍可制造非法数据

- 严重度：P1，部分可导致 P0 误判；证据：静态复核。
- `knowledge_converter.py:66-72` 仍声明 conditional_rules 为 array，`:166-169` 会把对象包成 list，写入后运行时只能 error。
- `schemas.py:308-315` 未限制空 item_ids、正整数、去重；执行器可把零记录任务 completed/100%。
- `tasks.py:385-403` 仍硬删除且不限制运行态，带记录或 running 任务可能出现 500、证据丢失或后台竞争。
- 修订：T-15 建立唯一规则 Schema，预览、写入、转换、导入共用；非法输入 400 且零资产写入。T-11/T-12 补创建边界、软删除和证据保留矩阵，不得通过删除旧测试或放宽断言掩盖问题。

### V1-10 前端客户端可解析 201，但页面仍只认 200，登录/注册缺契约字段

- 严重度：P1；证据：静态复核。
- `client.js:424-428` 接受全部 2xx，但 `views/tasks/create.vue:307`、`views/login/index.vue:203,212`、`store/user.js:29` 等大量调用方仍写 `res.code === 200`。后端切换到契约 201 后，请求成功却可能不进入成功流程。
- 登录/注册在 `views/login/index.vue:199-211` 只发送 username/password；`user-administration-v1.0.md` 要求 body 中 pc_identifier，且登录成功为 201。
- 修订：视图统一使用 2xx 成功判定或客户端标准化结果，不允许各页面散落 200；登录/注册补 pc_identifier，并做目标后端真实联调。增加 200/201、0/false/空串、错误外层和重复提交测试。

### V1-11 T-20 mock 来源和最终前端门禁未闭环

- 严重度：P1；证据：独立回归与文档复核。
- 当前 mock 来自仓库确定性脚本，不是 mock-api。Lead 无权替代用户放宽全局规则。
- lint 有 1037 个 warning，构建有弃用和大 chunk 警告；token 静态通过不能替代页面九状态、四边界态、断点、键盘、浏览器 console 和截图验收。
- 修订：优先由 mock-api 按确认契约重新生成；若用户明确批准临时替代机制，必须同步修订规则并保留来源标注、契约差异检查、生产禁用和真实联调切换。最终交付不得残留未标注 mock。T-22～T-34 仍需用户确认组件/页面文档后实施。

### V1-12 A133P 画像冲突不能一律 SKIP

- 严重度：P1；证据：实机只读记录与代码/画像静态复核。
- 当前 A133P 实测 techwin 10 点，画像期望 32 点，多项 mc_props 不一致；DDR 仅有 32 位工具。
- 修订：画像选择至少包含板型、固件、面板/触摸控制器和 ABI；serial 只绑定证据，不作画像身份。明确适用于该固件/面板且实测不符合期望时应 fail；画像缺失、不适用或配置无效应 error，并将覆盖状态记为无法核验/阻塞；只有 R3 明确排除项才按范围 skip。执行终态与验收覆盖状态必须分开。

### V1-13 文档和变更集可追溯性仍需修正

- 严重度：P1/P2。
- 集成汇总有 12 个失效链接，6 个任务结果文件含 emoji，校验器仍有 8 个“任务必须未开始”的过时断言。
- 集成汇总仍写“尚未 git commit”，与当前历史不符；追踪矩阵部分环境状态也未随当前设备在线事实更新。
- T-01/T-17/T-18、T-20/T-21 存在混合提交，独立回退需要 hunk 映射。
- 修订：修复实际链接和 emoji；更新校验器以接受合法任务状态并检查证据完整性，而不是回退任务状态；更新历史描述。既有提交不建议擅自重写，可补组合回退演练和 hunk 映射，后续坚持单任务独立变更集。

## 4. 配置导入现状与目标架构

### 4.1 当前能力不能视为统一导入

- `tool_registry.py:137-201` 是服务器本地 manifest 扫描，每个 manifest 单独 commit；缺字段可跳过该条并继续提交，可能留下部分模块/测试项。
- 模块和测试项 CRUD 是逐对象写入，没有稳定业务 key、base_revision、整包 diff 和回滚。
- 工具上传、知识转换、UPFM 专用脚本各有独立语义，没有统一事务、审计和导出回环。
- `execution_engine.py:549-580` 的 host_exec 使用 `create_subprocess_shell`。管理员当前可写 exec_command，不代表可以把任意命令作为“配置”开放导入。

### 4.2 建议的 V1 安全边界

1. 首版仅 UTF-8 JSON 声明式配置，不支持 ZIP，不允许代码、脚本、二进制、SQL、shell 或任意附件。
2. runner 只能选择已注册 allowlist 的精确 id/version/sha256，导入不得新增命令、下载、安装或启动 runner。
3. 密钥、用户、owner、数据库凭据、历史报告和 observed 实机画像不进入通用包。
4. 上传、validate dry-run、diff、active admin 确认、单事务 apply、审计、包级 rollback、export round-trip 缺一不可。
5. 默认冲突拒绝，不静默覆盖、不默认 prune；使用稳定业务 key、resource revision、base_revision、全包 SHA-256 和 Idempotency-Key。
6. 所有适配器同一事务，任一故障全包零写入；运行/历史任务继续使用不可变快照。
7. 配置导入不自动执行测试、不触碰设备、不隐式发布执行能力。

建议包外形仅为草案，不是已确认契约：

```json
{
  "schema_version": "1.0",
  "package_id": "vendor.upfm",
  "package_version": "1.0.0",
  "module_type": "test_module",
  "module_key": "upfm",
  "revision": 7,
  "payload": {
    "display_name": "UPFM",
    "items": []
  },
  "dependencies": []
}
```

建议接口方向，六要素尚未定义、未获双方确认，不得直接开发：

- `POST /api/v1/config-imports`：上传并校验，默认 dry-run。
- `GET /api/v1/config-imports/{id}`：查看校验、diff 和状态。
- `POST /api/v1/config-imports/{id}/confirmations`：携带 Idempotency-Key 确认应用。
- `POST /api/v1/config-imports/{id}/rollbacks`：按 before-image 幂等回滚。
- `GET /api/v1/config-exports`：按模块导出稳定 key 和版本，不导出秘密或内部 ID 身份。

完整 R32～R59/A32～A59 和 D1～D9 见[配置导入需求草案](../../requirements/config-import-requirements-v0.1-draft.md)。需求门禁未通过前，不得进入正式接口实现。

## 5. 推荐实施顺序

### 阶段 R：立即冻结生产发布

- 当前版本只作为受控开发基线。
- 真实库禁止 downgrade base；不在生产环境试迁移。
- 不开放任意配置/命令上传，不把现有静态检查结果写成 Docker 运行时通过。
- 将本报告六项动态反例纳入开发回归，修复后必须保留并全量运行。

### 阶段 F0：先修可信度和授权主线

1. T-03/T-04/T-05：设备、手动/AI/重跑、报告和 WS 授权。
2. 重开 T-06，关闭两条 fail-open；T-07 完成 stop、任务终态和安全异常摘要。
3. T-08 统一所有统计读模型。
4. T-11/T-12 完成 schema、幂等、不可变快照、daily、设备锁和生命周期。
5. T-15/T-16 完成规则写入和账号生命周期。

这些任务未完成前，不建议叠加“自由写入配置”能力，否则会把现有非法规则和授权问题放大到批量导入。

### 阶段 F1：闭环迁移与部署

- 按 V1-05 统一新装、升级、回滚、备份恢复路径并实际演练。
- 按 V1-08 改为显式工具清单，在真实 Docker 环境完成 R27。
- 明确 Android 9/10/10.1、32/64 位支持矩阵，未覆盖项记无法核验，不记通过。

### 阶段 F2：确认配置导入需求后再设计实施

- 用户先确认 D1～D9 和 A32～A59。
- 契约、ADR、数据模型和前后端接口六要素经双方确认后再开工。
- 以 T-36 统一 manifest/seed/UPFM 专用脚本事实来源，避免再造第四套配置入口。
- 后端 dry-run/apply/audit/rollback 与前端向导可并行，但前端只能使用 mock-api 按确认契约生成的 mock。
- 每个适配器故障、10 并发、重放、回滚、round-trip 和敏感 canary 必须有真实运行证据。

### 阶段 F3：完成前端、实机和文档闭环

- 用户确认 T-22～T-34 组件/页面契约后实施，再执行 T-35 浏览器与可访问性验收。
- 修复 201/pc_identifier 联调问题、lint/build 警告和文档链接。
- 实机只读与写测试分开授权，导入本身不得触发设备动作。
- 最后由独立验收方执行 T-38 和新增配置导入验收。

## 6. V1.0 上线门禁

只有以下条件全部满足，才可重新申请上线验收：

1. 本报告 P0 项全部有修复、边界/异常测试和独立复测通过证据。
2. R1～R31 逐条通过；若配置导入纳入 V1.0，新增已确认 R32～R59 也逐条通过。
3. 新装、存量副本、WAL 数据、迁移失败、revision 回滚和备份恢复均通过，真实数据保留。
4. 干净 Docker build/start/健康检查/工具发现/弱密钥矩阵通过，无伪造 verified。
5. 创建和重跑幂等、10 并发、权限、stop、五类终态、统计和报告跨 API/WS 一致。
6. 配置导入若入版，严格 schema、dry-run、diff、单事务、冲突、审计、回滚、导出回环和快照隔离全部通过。
7. 前端 lint 0 error/0 warning、build 无既定警告、浏览器 console 0 error/0 warning，页面和可访问性证据齐全。
8. 实机支持矩阵明确；范围内无不通过或无法核验，画像冲突不通过 SKIP 隐藏。
9. 生产无未标注 mock，文档链接、任务状态、追踪矩阵和证据路径一致。
10. 独立验收报告逐条引用原始日志；任一不通过或无法核验，总体仍不通过。

## 7. 审计边界

- 本轮未修改业务代码，未提交 Git，未执行真实库迁移，未做设备写操作。
- 前端仅完成既有测试/构建和客户端兼容定向复核，未完成全页面浏览器验收。
- 静态发现必须由对应修复任务补动态回归；本报告没有把静态审查冒充动态通过。
- 配置导入只有需求草案和架构建议，没有实现，也没有任何导入通过记录。
- 本报告是独立上线评估，不替代用户对新需求、契约变更和最终验收的确认。
