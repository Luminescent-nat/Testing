# Archive 归档说明

本目录只保留具有历史追溯价值的实机结果与调试数据，不再保存已被替代的一次性脚本。

## 2026-11-13 废弃项清理

依据 2026-07-20 归档时的引用检查，并在清理前重新检查当前 `test-platform/` 与 `docs/` 无活动引用，已删除：

- `legacy-scripts/`：早期单体 `emmc_tools.py` 与 4 个一次性 mindmap 生成脚本；现行 EMMC 实现位于 `test-platform/test-tools/emmc/`。
- `debug-artifacts/` 中的一次性补丁、手动调试和旧跑测脚本：`patch_reports.py`、`patch_word.py`、`run_all_tests.py`、`run_emmc_round.py`、`run_upfm_rerun*.py`、`sync_emmc_items.py`、`test_api.sh`、`test_complete.sh`、`test_full_workflow.py`、`test_system.py` 与临时任务 ID 文件。

正式测试入口仍为 `test-platform/backend/` 下的 pytest 与 `test-platform/frontend/` 下的 Vitest/Playwright。删除内容保留在 Git 历史中，可追溯，不影响当前运行代码。

## 保留的历史结果证据

下列文件不是运行依赖，但属于历史实机或调试结果快照，不能作为普通缓存删除：

- `UPFM测试项.xlsx`。
- `debug-artifacts/emmc_*.json`。
- `debug-artifacts/upfm_rerun_a133p_boards.json`。
- `debug-artifacts/upfm_rerun_records.json`。

这些快照只证明其记录时的历史结果，不替代当前 HEAD 的验收证据。

## 本地运行时文件

数据库、数据库备份、运行日志、storage、缓存、虚拟环境与 `.env` 均由 `.gitignore` 排除，不上传 GitHub。任何历史库或备份仍需单独审批后才能删除，不与废弃脚本一起清理。
