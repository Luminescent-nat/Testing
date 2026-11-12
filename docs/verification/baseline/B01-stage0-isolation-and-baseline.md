# 阶段 0 测试隔离与可恢复基线（B01）

- 日期：2026-11-09
- 起始提交：`627e5f28a16772816d474694f5a96c0a79b4a611`
- 范围：仅测试基础设施、E2E 环境保护、相关使用文档与验证证据；未修改业务执行、权限、调度或前端页面逻辑。
- 结论：G0 基线可复现与数据保护门禁通过；不代表 R1～R31、实机、Docker、迁移或发布验收通过。

## 实施内容

1. 后端每个测试用例的 `STORAGE_PATH/TOOLS_PATH/REPORTS_PATH/LOGS_PATH` 自动指向独立临时目录。
2. 工具 fixture 和上传接口测试不再直接写 `backend/storage/tools`。
3. 测试数据库关闭前取消并等待任务执行器及报告后台任务，避免跨用程访问已关闭事件循环。
4. WebSocket 测试上下文显式注入 Mock ADB，避免 `TestClient` lifespan 心跳创建真实 ADB 子进程；对该资源警告启用 error 回归门槛。
5. `ensure_e2e_admin.py` 要求 `E2E_TEST_MODE=1`、`DATABASE_URL=E2E_DATABASE_URL`，并拒绝平台默认数据库。
6. Playwright global setup 缺少 `E2E_DATABASE_URL` 时拒绝执行，并使用参数数组调用 Python，避免 shell 拼接。
7. 新增存储隔离与 E2E 环境保护的正常/异常路径用例。

## 实际运行证据

| 核验项 | 实际结果 | 原始证据 |
|---|---|---|
| 首次全量后端回归 | 187 passed、1 failed；新增环境保护测试在 Git Bash 下因子进程输出编码失败 | `B01-stage0-regression-20261109.log` |
| 修正编码后第二次全量回归 | 188 passed、1 条子进程 transport 清理警告 | `B01-stage0-regression-rerun-20261109.log` |
| WS 最小复现与修复 | 单独运行稳定复现；注入 Mock ADB 后 3 passed、0 warning | 工具运行记录；最终全量日志 |
| 最终全量后端回归（补齐正向建号前） | **188 passed、0 failed、0 warning**，107.27s | `B01-stage0-regression-final-20261109.log` |
| 隔离证明全量回归 | **188 passed、0 failed、0 warning**，94.75s | `B01-stage0-isolation-proof-20261109.log` |
| 最终全量后端回归（含隔离库正向建号） | **189 passed、0 failed、0 warning**，95.99s | `B01-stage0-final-189-20261109.log` |
| 受保护文件哈希对照 | 138 个数据库、日志、报告和 archive 文件，多次回归前后变化数 **0** | `B01-protected-hashes-before.json`、`B01-protected-hashes-after.json`、`B01-protected-hashes-final.json` |
| 备份副本恢复 | 备份与恢复副本 SHA-256 一致；备份、恢复副本和当前库 `integrity_check=ok`；表行数一致 | `B01-backup-restore-20261109.json` |
| 前端 Vitest | 2 files / 6 tests passed；有 Vite CJS API 弃用警告 | `B01-frontend-vitest-20261109.log` |
| 前端 lint | 退出码 0；**0 errors、1037 warnings**，存量格式问题未在本阶段批量改写 | `B01-frontend-lint-20261109.log` |
| 前端 build | 退出码 0；有 Vite CJS、Dart Sass legacy API 和大 chunk 警告 | `B01-frontend-build-20261109.log` |
| Playwright 缺少隔离配置 | 按预期在 global setup 以非零退出拒绝，未进入账号初始化 | `B01-e2e-missing-isolation-guard-20261109.log` |

## 调试记录

- 新增 E2E 保护测试首次失败由 Windows 子进程默认编码引起；测试显式固定 `PYTHONIOENCODING=UTF-8` 与解码格式后，PowerShell/Git Bash 均通过。
- 全量回归中的 `BaseSubprocessTransport` 警告可在 WS 文件中独立复现。根因路径为 `TestClient` lifespan 心跳未注入 Mock ADB；修复 fixture 后定向与两次全量回归均无该警告。
- 失败日志均保留，没有删除失败用例或仅修改断言掩盖问题。

## 本阶段未覆盖

- 未运行完整 Playwright 正向流程；需要启动使用同一隔离数据库与 storage 的前后端服务。
- 当前 `adb devices -l` 无设备，未进行实机识别或 UPFM 用例。
- 未执行 Docker 构建、存量库 Alembic 升级/回滚、页面视觉走查。
- 前端 1037 条 lint 警告、构建弃用/大包警告仍是后续整改债务，不能称为前端零警告交付。
- 设备授权、失败关闭、原生 SKIP、daily、统计等 P0 业务缺陷仍未修改。

## 门禁结论

G0 所需的完整测试日志、实际结果、测试隔离、受保护数据哈希及备份副本恢复证据已具备，**G0 通过**。下一阶段只能进入契约、ADR、UI 规格和追踪矩阵；这些产物未经用户确认与架构评审，不得开始对应业务代码整改。

## 2026-11-09 后续复核补充

阶段 1 文档交付前再次运行全量回归，出现 `189 passed, 1 warning`；警告仍为 Windows `BaseSubprocessTransport` 清理异常，原始结果保留于 `../stage1-backend-regression-20261109.log`。这说明此前 WS 定向修复虽未失败，但公共 mock 对 lifespan 的覆盖不完整，不能用此前零警告结果推定后续永远无复发。

新增隔离断言在修复前实际失败，证明 `app.main` 导入时保存的 `ADBService` 未指向当前 mock，见 `../stage1-lifespan-isolation-red-20261109.log`。随后仅在公共测试 fixture 中同步 patch 该引用：

- WS 连续 3 轮均为 3 passed，见 `../stage1-lifespan-isolation-green-20261109.log`。
- 最终将 `PytestUnraisableExceptionWarning` 提升为错误运行全量，189 passed、105.02 秒、无警告汇总，见 `../stage1-backend-regression-final-20261109.log`。

本补充只关闭测试生命周期隔离缺口，不改变业务代码，也不改变本报告对 R1～R31 未验收的结论。
