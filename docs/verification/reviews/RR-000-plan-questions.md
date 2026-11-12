# RR-000：计划/契约/设计文档疑问项清单与评审结论

- 评审编号：RR-000
- 评审对象/任务编号：批次 G 前置依据文档（阶段一，随开发并行完成）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：
  - `docs/plan/implementation-plan-v1.0.md`（v1.0，2026-11-12）
  - `docs/plan/task-board-v1.0.md`（v1.0，2026-11-12）
  - `docs/contracts/README.md`（契约 v1.0，确认日期 2026-11-12）及 `task-execution-v1.0.md` 等分契约
  - `docs/design/execution-state-machine.md`（v1.0，2026-11-12 用户已确认）
  - `docs/design/scheduler-and-data.md`（v1.0，2026-11-12 用户已确认）
  - `docs/design/ui-tokens.md`（v1.0，确认日期 2026-11-12）
  - `docs/verification/verification-rules-v1.0.md`（v1.0，2026-11-12）
  - `docs/verification/stage1-handoff.md`（2026-11-12，H01/H02 放行、H03 不放行）
- 环境与 commit/变更集：主机 Windows 10（10.0.26200），工作目录 `D:\MCTEST`，git HEAD `d0b415d`（阶段0/1定稿）。评审为纯文档/代码只读核查 + 真机只读审计，未产生业务变更。
- 证据路径：
  - `docs/verification/reviews/evidence/adb-a133p-20261112/`（真机只读原始输出 17 份）
  - 本文件引用的代码位置均为 `git show d0b415d` 当前工作区实况（附文件:行）

## 0. 评审范围说明

按 Lead 派发的批次 G（T-01/T-02/T-06/T-17/T-18/T-19/T-20/T-21），对实现前已可判定的疑问项逐项建档。本记录只做"实现前疑问确认"，不替代各任务完成后的 RR-Txx 评审。

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| Q1 | 契约成功外层与现有实现的差异 | 读契约 README §2 + `backend/app/schemas.py:624-627`、`backend/app/main.py:154-164` | 见问题 P1 | 差异存在且必须在 T-01 落地 |
| Q2 | 422→400 的兼容影响 | 读契约 README §2 错误码表 + 全局无 `RequestValidationError` handler（`main.py` 仅 1 个 Exception handler） | 见问题 P2 | 影响前端 client 与既有测试，需双轨过渡 |
| Q3 | 目标路由 vs legacy 双轨 | grep legacy 路径：`devices.py:67`、`tasks.py:198/236`、`auth.py:91`、`reports.py:1301/1318` | 见问题 P3 | 契约 README §4 允许短期双轨，必须委托同一服务并标弃用 |
| Q4 | mock-api 工具缺失 | `Get-Command mock-api` 退出码 1；frontend 无 tools/mock-api 目录；`docs/verification/verification-rules-v1.0.md:118` 要求 mock 只能来自 mock-api 生成物 | 见问题 P4 | T-20 DoD 文字与工具现实冲突，需用户裁决 |
| Q5 | Docker 不可用导致 T-17 无法核验 | 主机无 docker 命令（未执行成功）；契约/scheduler-and-data §6 自认"当前未执行干净构建，R27 未验证" | 见问题 P5 | T-17 代码可评审，运行时验证只能标"无法核验" |
| Q6 | 前端源码中文字符乱码（UTF-8 mojibake） | 对 `frontend/src` 36 个 *.vue/js/ts 逐一严格 UTF-8 解码 + mojibake 特征正则扫描；再对 HEAD 版 theme.scss/index.scss 做字节级 hexdump + 双解码对照 | 见问题 P6（已结案） | 字节级证明：文件均为合法 UTF-8 正确中文；观察到的乱码是控制台按 GBK/936 渲染 UTF-8 的显示 artifact，非文件缺陷（已结案，详见 §4.1） |
| Q7 | T-19 str 命令改参数数组的调用方兼容 | grep `test-tools` 全部 `.shell(`/`.run(` 调用点（66 处命中，约 30 处业务调用） | 见问题 P7 | 兼容面大，T-19 必须给出兼容策略 |
| Q8 | ADB 设备仅 armeabi-v7a/Android 10 的覆盖局限 | 真机 getprop 实测（`evidence/adb-a133p-20261112/03/04.log`）；ddr 二进制仅有 armeabi-v7a | 见问题 P8 | 记录为长期限制，不阻塞批次 G |
| Q9 | 成功外层 `data` 必填对象 vs 现实现 `data: Optional[Any]=None` | `schemas.py:624-627` | 见问题 P1 细项 | 并入 P1 |
| Q10 | 基线证据日志为 UTF-16 编码 | 读 `docs/verification/baseline/baseline-session-start-20261112.log`（BOM FF FE） | 见问题 P9 | 低风险，仅证据可读性 |

## 2. 问题与风险等级

| # | 问题 | 依据（文件:行/证据） | 影响 | 等级 | 责任任务 |
|---|---|---|---|---|---|
| P1 | 成功/错误外层与现实现不一致。契约要求成功 `{code:int(=HTTP),message,data:object}`（无内容时 `data={}`，`data` 必填）；错误 `{code:string机器码,message,details:object}`。现实现：`ResponseModel.data` 可为 null（schemas.py:627）；全局 500 返回 `{code:500,message,detail}`（字段名是 `detail` 非 `details`，code 是 int 非字符串 INTERNAL_ERROR，main.py:157-164）；未处理 FastAPI 默认 422 `{"detail":[...]}` | contracts/README.md:35-58；schemas.py:624-632；main.py:154-164 | 所有契约错误码断言、前端错误解析（frontend/src/api/client.js 已按新外层实现 normalizeErrorPayload）都依赖统一外层；若 T-01 只改后端不改齐全部端点，新旧外层混存 | 高 | T-01 |
| P2 | 422→400：FastAPI 默认把请求体验证失败返回 422 + `{"detail":[...]}`；契约要求 400 + `VALIDATION_ERROR`。现无 `RequestValidationError`/`HTTPException` 契约化 handler。兼容影响：①既有 189 基线中可能有断言 422/detail 的用例需同步改写（属预期语义变更，不算放宽）；②前端 axios 错误处理与用户提示从 422 映射为 400；③OpenAPI 文档中验证错误示例随之变化 | main.py（无对应 handler）；contracts/README.md:52（VALIDATION_ERROR=400） | 中：若遗漏 handler，所有非法输入用例直接回归失败或被旧 422 掩盖 | 中 | T-01 |
| P3 | 目标路由 vs legacy 双轨：目标 `/tasks/{id}/cancellations`、`/tasks/{id}/reruns`（task-execution-v1.0.md §6/§7）；legacy `/tasks/{id}/cancel`（tasks.py:198）、`/tasks/{id}/rerun-failed`（tasks.py:236）、`/devices/refresh`（devices.py:67）、`/auth/register`（auth.py:91）、`/reports/*/export`（reports.py:1301/1318）。契约 README §4 允许 legacy 短期保留但必须：委托同一服务、标弃用、覆盖相同授权语义；不得形成第二套权限/统计 | contracts/README.md:68-74；task-board T-01 DoD | 双轨若各自实现（尤其 register 首管理员语义与 AI 创建入口）将复现"第二套权限"缺陷 | 中 | T-01 |
| P4 | mock-api 生成工具缺失：主机 `mock-api` 命令不存在，frontend 内无 mock-api 目录/配置。验证规则 v1.0 §7 要求"mock 只能来自 mock-api 按确认契约生成的文件"；task-board T-20 DoD 写"用 mock-api 生成开发 mock"。工具缺失时开发只能手写 mock，字面上违反 DoD 措辞 | verification-rules-v1.0.md:118；task-board T-20；主机实测（Get-Command 退出码 1） | T-20 若手写 mock 并标"mock-api 生成"即属证据夸大；若如实标注则 DoD 无法满足 | 中 | T-20（已裁决 U1：接受仓库确定性脚本+显式标注为临时替代，标偏差） |
| P5 | Docker 不可用：主机无 docker 命令（本会话未检测到可执行 docker；契约与设计文档亦自认 R27 未验证）。T-17 的 DoD"干净构建/启动并导出工具清单"无法在本机执行 | scheduler-and-data.md:83（自认未执行）；task-board T-17 验证 | T-17 只能交付代码+静态核对，运行时验证标"无法核验"，不得写通过 | 中 | T-17 |
| P6 | 「前端源码中文字符乱码」经字节级复核为**显示层 artifact，非文件缺陷**：`git show HEAD:test-platform/frontend/src/styles/theme.scss` 首行原始字节 `e4b8bb e9a298 e58f98 e9878f e5ae9a e4b989`＝UTF-8 编码的「主题变量定义」；`index.scss` 首行 `e9809a e794a8 e6a0b7 e5bc8f`＝「通用样式」。二者按 UTF-8 严格解码均为正确中文；按 GBK 误读才会得到 Lead 所述「涓婚鍙橀噺瀹氫箟/閫氱敤鏍峰紡」。工作区（T-21 后）首行 `e8aebee8aea1 20 746f6b656e`＝「设计 token」，同样正确、无 U+FFFD。同一现象在 `.gitattributes`、check-tokens 输出等处复现，均系终端未按 UTF-8（cp936/GBK）解码所致 | 本记录 §5 字节证据 `evidence/encoding-check-theme-index-20261112.log`；`_tmp_encoding_check.py` 输出；theme.scss/index.scss 工作区读取 | 文件内容自始正确，无需 T-21「修复乱码」；不存在文件级 GBK-as-UTF8 损坏。建议后续统一终端/日志为 UTF-8 以避免误判 | 低（已结案） | 记录性（U5 结案） |
| P7 | T-19 调用方兼容：`common/adb_runner.py:59-61` 现为 `shell(cmd:str)` → `run(f'shell "{cmd}"', shell=True)`。全库约 30 处业务调用传 str，且大量使用 f-string/字符串拼接传参：`mc_props_check.py:61`、`apk_install_check.py:40`、`toggle_check.py:54-101`、`sleep_check.py:78-109`、`rotation_check.py:57`、`storage_rw_check.py:62-170`、`emmc_fio_runner.py:163`（`" ".join(cmd_parts)`）、`emmc_tester.py:73-279` 等。若 T-19 将 `shell()` 改为参数数组 API 而不留 str 兼容层，全部调用方一次性破坏；若改为内部 shlex 拆分，f-string 中的引号/元字符语义改变（如 `f'settings put {ns} {key} {value}'` 含空格值时） | common/adb_runner.py:39-61；grep 命中清单（本记录附） | 高：改签名为破坏性变更；保持 str+内部拆分则对含引号命令（如 `shell "echo \"ok\""`，adb_runner.py:94 自身也用）行为可能变化 | 高 | T-19（已裁决 U6：保留 shell(str) 兼容签名+内部参数数组，禁止破坏性换签名） |
| P8 | 真机覆盖局限：当前唯一实机 A133P 为 Android 10/SDK 29/`armeabi-v7a`（abilist 仅 `armeabi-v7a,armeabi`，zygote32，`evidence/.../04-getprop-abi.log`）。ddr 工具二进制仅有 armeabi-v7a（`test-tools/ddr/binaries/`，无 arm64-v8a）；emmc 双架构齐备。rk3568（arm64，profiles 第 30-69 行）在 64 位用户态下能否运行 32 位二进制取决于内核 CONFIG_COMPAT，未经实机验证。Android 9/10.1 等契约要求的兼容维度无实机 | evidence/adb-a133p-20261112/04；test-tools/ddr/binaries 目录清单 | ddr 工具链换板风险；实机项只能覆盖 Android10/32 位一种形态，其余标"无法核验" | 中 | T-19/T-36（记录性） |
| P9 | 基线证据日志 `baseline-session-start-20261112.log` 为 UTF-16 LE（BOM FF FE），用普通文本读取工具按 UTF-8 读会判为二进制/乱码 | 本机字节头实测（255,254,...） | 低：仅影响证据可读性与后续工具链兼容；内容核对无误（189 passed，102.66s） | 低 | 记录性（T-37 可顺带统一编码） |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | T-17 干净 Docker 构建/启动 | 主机无 docker | 运行时工具发现校验无法核验 |
| L2 | T-18 启动矩阵中的"实际启动服务"部分 | 需真实启动服务进程；评审方仅重跑单测，启动矩阵由开发提供证据、评审抽查 | 以证据核对为准 |
| L3 | A133P 蓝牙开关崩溃复现 | 开关 bluetooth 属写设备操作，本轮审计禁止 | 沿用画像历史记录（board_profiles.py:100-104），标"未复验" |
| L4 | Android 9/10.1、arm64 板型（rk3568）实机行为 | 无对应设备 | 相关契约兼容维度标"无法核验" |

## 4. 待用户确认项（含 Lead 裁决处置）

| # | 事项 | 建议决定 | Lead 裁决（2026-11-12） | 状态 |
|---|---|---|---|---|
| U1 | T-20 mock 生成方式（P4） | 接受"手写/脚本 mock + 明确标注来源"作临时口径 | **接受「仓库内确定性生成脚本 + 显式标注来源」作为本轮替代；必须标为偏差，T-20 结论为"有条件通过/待用户最终确认"，不得写成 mock-api 生成物** | 已裁决（T-20 结论据此） |
| U2 | 422→400 前端同步（P2） | 后端 400+契约外层、前端双格式兼容 | **采用后端 400+契约外层、前端 client 兼容双格式**（client.js normalizeErrorPayload 已支持） | 已裁决 |
| U3 | legacy 路径保留与弃用（P3） | 本轮保留并标 deprecated | **本轮保留 legacy 并加弃用标注；移除时点待用户定** | 已裁决 |
| U4 | 画像 vs 实机冲突口径（P-A1/P-A3） | 画像标注适用固件版本；冲突判 SKIP/待确认 | **画像期望=固件特定期望、实机实测=回归基线，双列记录；touch 10 vs 32、mc_props 四项、board=exdroid、serial 另一台实体等冲突一律标 SKIP/待用户确认，不得判 FAIL 作为交付证据** | 已裁决（已同步 RR-ADB-001） |
| U5 | "前端乱码"来源（P6） | 提供具体文件；无则撤销 | **以 theme.scss/index.scss 为具体路径结案；字节级复核确认为控制台 GBK 误读 UTF-8 的显示 artifact，文件本身正确（详见 P6 与 §5）** | 已结案 |
| U6 | T-19 str 兼容策略（P7） | 保留 shell(str)+内部参数数组+新增数组 API | **保持 `shell(str)` 兼容签名 + 内部参数数组，不允许破坏性换签名** | 已裁决（已下发 infra-tools，评审据此核对调用方） |

## 5. 独立重跑记录

本记录为文档/静态评审，未执行测试重跑。执行的核查命令：

- `Get-Command mock-api` → 退出码 1（命令不存在）。
- 前端源码编码扫描（PowerShell，严格 UTF8Encoding($false,$true) 解码 + mojibake 正则 `锟|æ|å|ç|è¾|U+FFFD`）：36 个 src 文件 0 命中、0 解码失败；dist/public/tests 0 非 UTF-8 文本文件。
- 字节级编码复核（`evidence/_tmp_encoding_check.py`，`python -c` 取 `git show HEAD:` 原始字节）：theme.scss 首行 hex `…e4b8bbe9a298e58f98e9878fe5ae9ae4b989…`（=主题变量定义），index.scss 首行 `e9809ae794a8e6a0b7e5bc8f`（=通用样式）；UTF-8 strict 解码正确、GBK 解码为乱码；工作区同法正确、无 U+FFFD。结论：文件自始为合法 UTF-8 正确中文，乱码为终端 GBK 误读。输出存 `evidence/encoding-check-theme-index-20261112.log`。
- `git status`/`git log`：工作区状态与 HEAD=d0b415d 已核对。

## 6. 最终结论

**有条件通过（作为实现前疑问清单放行）。** U1/U2/U3/U4/U6 已由 Lead 裁决并落实为评审依据；P6（U5）经字节级证据结案为显示层 artifact、非文件缺陷；P5 下 T-17 运行时验证只能标"无法核验"。其余为记录在案风险，不阻塞开发。

## 7. 签名

reviewer，2026-11-12；本记录基于原始证据独立作出，未代开发修改任何代码。
