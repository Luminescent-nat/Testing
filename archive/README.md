# Archive 归档说明

归档日期：2026-07-20。本项目无版本控制，历史文件统一移动到本目录而非删除。
移动前已对 `test-platform/backend/app/`、`test-platform/backend/*.py`、`test-platform/*.sh`、前端 `src/` 及各 README/文档做引用 grep 检查，下列文件均未被活代码引用。

## legacy-scripts/ —— 早期历史脚本

| 文件 | 原路径 | 归档原因 |
|---|---|---|
| `emmc_tools.py` | `D:/MCTEST/emmc_tools.py` | 821 行早期单体脚本，流程已拆解进 `test-platform/test-tools/emmc/`。DEVELOPMENT_WORKFLOW.md §3.3 明确要求删除。代码中仅有注释级"对齐 emmc_tools.py 流程"的历史参考提及 |
| `generate_mindmap.py` | `D:/MCTEST/generate_mindmap.py` | xmind 生成脚本，同用途脚本共 4 个，均为一次性产物 |
| `generate_flow_mindmap.py` | `D:/MCTEST/generate_flow_mindmap.py` | 同上 |
| `generate_flow_mindmap_v2.py` | `D:/MCTEST/generate_flow_mindmap_v2.py` | 同上 |
| `generate_flow_mindmap_xmind8.py` | `D:/MCTEST/generate_flow_mindmap_xmind8.py` | 同上 |

## debug-artifacts/ —— 一次性调试产物

| 文件 | 原路径 | 归档原因 |
|---|---|---|
| `emmc_baseline_verify_task_6.json` | `test-platform/` | 早期手动调试的任务结果快照 |
| `emmc_baseline_verify2_task_7.json` | `test-platform/` | 同上 |
| `emmc_stability_verify_task_4.json` | `test-platform/` | 同上 |
| `emmc_stability_verify_task_5.json` | `test-platform/` | 同上 |
| `emmc_test_result_task_2.json` | `test-platform/` | 同上（`run_emmc_round.py` 的输出产物） |
| `verify_stability_task_id.txt` | `test-platform/` | 调试时记录 task id 的临时文件 |
| `test_api.sh` | `test-platform/` | 早期手动 curl 调试脚本，非正式流程入口 |
| `test_complete.sh` | `test-platform/` | 同上 |
| `run_all_tests.py` | `test-platform/` | 早期手动调试脚本；正式测试入口为 `backend/` 下 pytest（pytest.ini testpaths=tests），启动脚本与文档均未将其作为正式入口 |
| `run_emmc_round.py` | `test-platform/` | 早期手动跑 EMMC 轮次的调试脚本 |
| `test_full_workflow.py` | `test-platform/` | 早期手动调试脚本；与 `backend/tests/e2e/test_full_workflow.py`（正式 e2e 用例，未动）仅同名，无引用关系 |
| `patch_reports.py` | `test-platform/backend/` | 用正则改源码的临时补丁脚本，补丁已生效 |
| `patch_word.py` | `test-platform/backend/` | 同上 |
| `test_system.py` | `test-platform/backend/` | 非 pytest 的早期冒烟脚本，pytest.ini 的 testpaths=tests 已排除它 |
| `sync_emmc_items.py` | `test-platform/backend/` | 无引用，职责与 `app/seed_data.py` 的 EMMC 种子数据完全重叠（seed_data 为现行版本） |

## runtime-junk/ —— 运行时垃圾 / 误生产物

| 文件 | 原路径 | 归档原因 |
|---|---|---|
| `test_platform.db` | `D:/MCTEST/test_platform.db` | 0 字节空库，在错误目录启动后端产生；正式库为 `test-platform/backend/test_platform.db` |
| `backend_server.log` | `test-platform/backend/server.log` | 旧后端运行日志（归档时重命名以区分根目录同名日志） |
| `storage/` | `D:/MCTEST/storage/` | 在错误目录启动后端产生的空目录（仅含空 `tools/`）；后端有自己独立的 `test-platform/backend/storage/`（logs/reports/tools） |
| `root__pycache__/` | `D:/MCTEST/__pycache__/` | 根目录 Python 字节码缓存（重命名以标明来源） |
| `test_platform.db.bak` | `test-platform/backend/test_platform.db.bak` | 旧手工数据库备份（Jul 13） |

注：根目录 `server.log`（121 字节）在移动过程中被同名文件覆盖丢失；内容仅为一次性运行日志，无保留价值。

## 未归档

- `.venv_xmind/`：mindmap 脚本专用虚拟环境，体积大。未移动，**建议用户确认后自行删除**（对应脚本已归档至 legacy-scripts/）。
- `test-platform/backend/migrate_*.py`：手写迁移脚本，后被 alembic（`backend/alembic/`）取代并删除。
