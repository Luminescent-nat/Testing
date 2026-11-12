# 整改基线记录（B00）

- 日期：2026-11-09
- Git commit：627e5f28a16772816d474694f5a96c0a79b4a611（master；编制时存在未跟踪 `docs/`，并非完全无未跟踪文件）
- 计划文件：C:\Users\MCTECH\.claude\plans\adb-enumerated-wilkes.md（2026-11-09 用户批准）

## 环境

| 项 | 值 |
|---|---|
| Python | 3.12.10 |
| FastAPI | 0.109.0 |
| SQLAlchemy | 2.0.25 |
| Pydantic | 2.5.3 |
| Node | v24.15.0 |
| npm | 11.6.4 |
| ADB | 1.0.41 (35.0.2) |
| 平台服务 | 未运行（审计时无后端/前端进程） |

## 实测基线（2026-11-09，均为真实运行）

| 项 | 命令 | 结果 |
|---|---|---|
| 后端收集 | `python -m pytest tests --collect-only -q` | 185 collected |
| 后端全量 | `python -m pytest tests -q` | **185 passed, 24 warnings, 97.31s**（测试用临时库；汇总后出现 aiosqlite 事件循环关闭线程异常，不能视为无异常；后续清理复核见 B01） |
| 前端单元 | `npm test`（Vitest） | **2 files / 6 tests passed** |
| 数据库备份 | `python scripts/backup_db.py` | `backups/test_platform_20261109_091839.db` |

## 数据盘点（只读）

- 正式库：`backend/test_platform.db`（1,060,864 字节，2026-10-08）；预置备份 `test_platform.db.bak2`（2026-07-31）；另有历史 smoke 库 2 个。
- 存储：`backend/storage/logs/task_{1,2,8,9,10}`（task_8/9/10 为 7 月历史实机日志；task_1/2 为今日 pytest 运行写入的执行日志产物）、`storage/reports/`（task_1/6/8/9/10 + samples）、`storage/tools/`。
- 处置：全部列为"禁止直接删除"，迁移演练只在备份副本上进行。

## 门禁

- G0 基线可复现：本记录编制时仅取得基础测试与备份证据，缺恢复演练、完整哈希和存储隔离证明，不能单独判 G0 通过；后续闭环结果见 `B01-stage0-isolation-and-baseline.md`。
- G1 需求确认：通过（R1～R31 经 requirement-reviewer 审核，用户 2026-11-09 批准计划构成确认）。
