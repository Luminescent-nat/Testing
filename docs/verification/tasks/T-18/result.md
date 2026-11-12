# T-18 拒绝弱默认密钥 — 结果记录

- 任务编号：T-18（共享任务板 task-7，owner=infra-tools）
- 执行人：infra-tools（Agent Team）
- 日期：2026-11-12（Asia/Shanghai，UTC+08:00）
- 设计依据：`docs/design/scheduler-and-data.md` 第 6 节「干净部署契约」

## 1. 变更文件

| 文件 | 变更 |
|---|---|
| `test-platform/backend/app/config.py` | 新增 `SECRET_KEY_MIN_LENGTH=32`、`SECRET_KEY_PLACEHOLDERS`（secret / change-me / your-secret-key / please-change-me-in-production 等 Compose 示例占位及其变体）、`secret_key_problem()`（返回原因，**绝不包含密钥值**）、`assert_secret_key_strength()`（不合规抛 `WeakSecretKeyError`） |
| `test-platform/backend/app/main.py` | lifespan 原 emptiness 检查替换为 `validate_startup_config()`：先 `assert_secret_key_strength(settings.SECRET_KEY)`，再 T-17 工具清单校验；失败 `logger.error("启动配置校验失败：%s", exc)` 后 raise —— 日志只指出配置项，不打印密钥值 |
| `test-platform/docker-compose.yml` | `- SECRET_KEY=${SECRET_KEY:-please-change-me-in-production}` → `- SECRET_KEY=${SECRET_KEY:?SECRET_KEY 未设置：...}`，未设置直接报错，删除弱默认占位 |
| `test-platform/backend/.env.example` | 同步强度规则说明（≥32 字符、非占位、非单字符重复），生成命令保留 |
| `test-platform/DEPLOYMENT.md` | Docker 首次部署、裸机要点第 4 条、内网检查清单同步（compose `:?` 强制显式、强度规则、错误不回显密钥） |
| `test-platform/backend/tests/unit/test_secret_strength.py` | 新增 21 用例（先红后绿）：弱/占位/变体/单字符重复/长度不足拒绝、错误信息不回显密钥值、合法与 32 字符边界、compose 强制显式静态契约、.env.example 文档同步、`main.validate_startup_config` 接线（弱密钥拒绝/合法密钥通过） |

## 2. 环境

- Windows 10；Python 3.12.10（venv）；uvicorn 0.27.0
- 启动矩阵完全隔离：每用例独立临时 cwd + 独立 SQLite/存储/日志（环境变量覆盖 `DATABASE_URL`/`STORAGE_PATH`/`LOGS_PATH`/`STATIC_PATH`），`TEST_TOOLS_PATH` 指向真实仓库 test-tools（只读），不触碰 `backend/test_platform.db` 与任何真实数据

## 3. 命令、起止时间与退出码

| # | 命令（WORKDIR） | 起 | 止 | 退出码 | 结果 |
|---|---|---|---|---|---|
| 1 | `python -m pytest tests/unit/test_secret_strength.py -q`（backend，实现前红测） | 12:06:11 | 12:06:12 | 2 | 收集错误：`cannot import name 'SECRET_KEY_MIN_LENGTH' from 'app.config'` |
| 2 | `python -m pytest tests/unit/test_secret_strength.py -q`（backend，实现后绿测） | 12:16+ | 12:16+ | 0 | 21 passed |
| 3 | `python docs/verification/tasks/T-18/startup_matrix.py`（MCTEST，真实启动矩阵） | 12:16:13 | 12:16:22 | 0 | **PASS**：8 类弱/占位/短密钥 uvicorn 全部 exit=3 拒绝启动；合法密钥 /health=200 `{"status":"healthy"}`；fresh 空库 + 合法密钥 /health=200 |
| 4 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`（backend，全量回归） | 12:16:33 | 12:18:46 | 0 | **310 passed**（0 failed） |

## 4. 原始日志与产物

- `docs/verification/tasks/T-18/pytest-T18-red-20261112.log` / `pytest-T18-green-20261112.log`
- `docs/verification/tasks/T-18/startup-matrix-20261112.log` — 每用例原始 uvicorn stdout/stderr、退出码、/health 探测、`mentions_config_item`/`leaks_value` 检查
- `docs/verification/tasks/T-18/startup-matrix.json` — 机器可读汇总
- `docs/verification/tasks/T-18/startup_matrix.py` — 可复现脚本
- `docs/verification/tasks/T-18/regression-full-20261112.log`

启动矩阵关键原始结论：
```
[empty]                     exit=3 rejected=True mentions_config=True leaks_value=False
[short]                     exit=3 rejected=True mentions_config=True leaks_value=False
[placeholder-secret]        exit=3 rejected=True mentions_config=True leaks_value=False
[placeholder-change-me]     exit=3 rejected=True mentions_config=True leaks_value=False
[placeholder-your-secret-key] exit=3 rejected=True mentions_config=True leaks_value=False
[placeholder-compose-example] exit=3 rejected=True mentions_config=True leaks_value=False
[placeholder-long-variant]  exit=3 rejected=True mentions_config=True leaks_value=False
[single-char-repeat]        exit=3 rejected=True mentions_config=True leaks_value=False
[legal]  /health status=200 body='{"status":"healthy"}' healthy=True   （已初始化临时库）
[fresh-empty-db] /health status=200 body='{"status":"healthy"}' healthy=True （干净空库，seed_data 修复后）
weak_all_rejected=True no_secret_value_leak=True legal_healthy=True fresh_empty_db_healthy=True
RESULT: PASS
```
弱密钥日志样例（不回显密钥值）：
`[ERROR] app.main: 启动配置校验失败：SECRET_KEY 强度不足：长度必须至少 32 字符。请生成随机密钥并写入 backend/.env...`
`[ERROR] uvicorn.error: Application startup failed. Exiting.`（uvicorn 退出码 3）

## 5. DoD 逐条

| DoD | 状态 | 证据 |
|---|---|---|
| config.py 提供 SECRET_KEY 强度校验（≥32；拒空/占位/单字符重复） | ✅ | `app/config.py`；21 项单测 |
| 拒绝 Compose 示例占位值及其变体 | ✅ | 精确匹配 + 前缀匹配（`please-change-...-longer...` 被拒） |
| 错误日志只指出配置项不打印密钥值 | ✅ | `secret_key_problem` 返回文案不含值；矩阵 `leaks_value=False` 全绿；单测 `test_error_message_never_echoes_the_key_value` |
| main.py lifespan 调用（复用 lifespan 校验点） | ✅ | `validate_startup_config()`；单测接线断言 |
| docker-compose.yml 默认值改强制显式 `${SECRET_KEY:?...}` | ✅ | compose 文件 + 静态契约单测（禁止 `${SECRET_KEY:-` 与占位默认） |
| .env.example / DEPLOYMENT.md 示例同步 | ✅ | 两文件更新 + 单测文档断言 |
| 真实启动矩阵：弱/占位/短密钥失败、合法密钥成功（uvicorn 临时端口 + /health，保存日志与退出码） | ✅ | 矩阵 PASS（第 4 节），退出码与原始日志齐备 |
| tests/unit/test_secret_strength.py 新增 | ✅ | 21 用例，先红后绿 |

## 6. 未验证项与说明

1. Docker 容器内启动（compose `:?` 生效路径）未验证——主机无 docker（与 T-17 同一限制）；host 侧已用 env var + uvicorn 等效验证 `${SECRET_KEY:?}` 的应用侧行为（强度校验），compose 变量展开属 docker 运行时行为，未核验。
2. 「合法密钥」矩阵用例与 conftest 一致使用 32+ 字符非占位测试常量（48 字符）；真实生产密钥不参与测试。
3. 密钥强度不做熵评估（除单字符重复外），符合任务定义范围；更长/低熵密钥不额外拒绝。
4. 弱密钥矩阵中 `empty` 用例以 `SECRET_KEY=""` 覆盖模拟「未配置」（主机 `backend/.env` 存在真实密钥，矩阵 cwd 为隔离临时目录不受影响）。

## 7. 联动发现

fresh 空库 + 合法密钥首次启动曾因 T-02 `PRAGMA foreign_keys=ON` 暴露 `seed_data.py` 虚构 `created_by=1` 的 FK 崩溃；经 lead 授权修复（`created_by=None`）后，本矩阵 `fresh-empty-db` 用例 /health=200 通过。该发现与修复详情记录于 `docs/verification/tasks/T-02/result-addendum-RR-T02.md`。

## 8. 回退说明

1. `app/config.py`：删除 `SECRET_KEY_MIN_LENGTH`/`SECRET_KEY_PLACEHOLDERS`/`secret_key_problem`/`assert_secret_key_strength`/`WeakSecretKeyError`。
2. `app/main.py`：`validate_startup_config()` 恢复为原 emptiness 检查（注意 T-17 工具清单校验若保留需另行接入点）。
3. `docker-compose.yml` / `.env.example` / `DEPLOYMENT.md`：恢复占位默认与旧文案（不建议：会重新引入弱默认密钥风险）。
4. 删除 `tests/unit/test_secret_strength.py` 与 `docs/verification/tasks/T-18/`。
5. 本次未 git commit；回退需手工反向编辑或经 Lead 确认后 `git restore`。
