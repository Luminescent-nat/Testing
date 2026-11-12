# RR-T18：拒绝弱默认密钥

- 评审编号：RR-T18
- 评审对象/任务编号：T-18（task-7，owner infra-tools）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/design/scheduler-and-data.md` v1.0 §6（SECRET_KEY 至少 32 字符、拒空/secret/change-me/your-secret-key/Compose 占位/单字符重复；错误日志不打印密钥值）、`docs/verification/verification-rules-v1.0.md` §6、`docs/plan/task-board-v1.0.md` T-18
- 环境与 commit/变更集：Windows 10，Python 3.12.10，uvicorn 0.27.0；git HEAD `d0b415d` + 工作区。变更：`app/config.py`（SECRET_KEY_MIN_LENGTH=32/占位集/secret_key_problem/assert_secret_key_strength/WeakSecretKeyError）、`app/main.py`（lifespan `validate_startup_config` 接线）、`docker-compose.yml`（`${SECRET_KEY:?...}` 强制显式）、`.env.example`、`DEPLOYMENT.md`、新增 `tests/unit/test_secret_strength.py`
- 证据路径：`docs/verification/tasks/T-18/`（result.md、startup-matrix-20261112.log、startup-matrix.json、startup_matrix.py、pytest-T18-red/green、regression-full）；评审方独立全量 `evidence/test-rerun-20261112/backend-final-full-regression-reviewer.log`

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 只改声明 scope | git diff/status | config.py/main.py(接线)/compose/.env.example/DEPLOYMENT.md/test_secret_strength.py；未改业务逻辑 | 通过 |
| 2 | 强度规则：≥32、拒空/占位/变体/单字符重复 | 读 config.py:8-53；test_secret_strength 21 用例 | SECRET_KEY_MIN_LENGTH=32；空/短拒；占位精确+前缀变体拒；单字符重复拒 | 通过 |
| 3 | 错误日志不打印密钥值 | 读 secret_key_problem（返回文案不含值）、assert 消息；startup-matrix leaks_value 全 false；单测 test_error_message_never_echoes_the_key_value | 错误仅指出配置项，不回显值；矩阵 8 类 leaks_value=False | 通过 |
| 4 | 真实启动矩阵：8 类弱/占位/短→exit=3 拒绝 | 读 startup-matrix.json/log | empty/short/placeholder-secret/change-me/your-secret-key/compose-example/long-variant/single-char-repeat 均 exit=3 rejected=True mentions_config=True | 通过 |
| 5 | 合法密钥 /health=200 | 矩阵 legal 用例 | status=200 `{"status":"healthy"}` | 通过 |
| 6 | fresh 空库 + 合法密钥 /health=200 | 矩阵 fresh-empty-db 用例（seed 修复后） | status=200 healthy | 通过 |
| 7 | compose 强制显式（无弱默认） | 读 docker-compose.yml diff | `SECRET_KEY=${SECRET_KEY:?...}`，删除 `:-please-change-me-in-production`；未设置即报错 | 通过 |
| 8 | .env.example / DEPLOYMENT.md 同步 | 读两份文件更新 + 单测文档断言 | 强度规则/生成命令/compose `:?` 同步 | 通过 |
| 9 | main.py lifespan 接线且不影响合法启动 | 读 validate_startup_config + try/except；独立全量 310 passed；矩阵 legal | 弱/缺拒绝启动、合法正常启动 | 通过 |
| 10 | 21 单测真实（先红后绿） | pytest-T18-red/green；独立全量含 test_secret_strength | red 收集错误；green 21 passed；独立全量通过 | 通过 |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-T18-1 | Docker 容器内启动（compose `${SECRET_KEY:?}` 变量展开路径）未验证 | result.md §6.1；主机无 docker | compose 运行时强制显式行为未在容器内核验；host 侧强度校验等效验证已过 | 低-中 | 运维/验收（需 docker） |
| P-T18-2 | 强度不做熵评估（除单字符重复）；更长低熵密钥不额外拒绝 | result.md §6.3；config.py | 符合任务定义范围；"aaaaaaaa…x"类低熵但非全同密钥不拒（可接受，记录在案） | 低 | 记录性 |
| P-T18-3 | 占位匹配为规范化精确+前缀；未覆盖全部可能占位词 | config.py:22-40 | 覆盖契约/Compose 常见占位；新增占位需扩充集合 | 低 | T-37/文档 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 容器内 compose `:?` 变量展开与容器启动 | 主机无 docker | 容器运行时未核验；host 侧等效（env→uvicorn）已核验 |
| L2 | 生产真实密钥/熵分布 | 测试用 32+/48 字符测试常量 | 真实密钥未参与；属合理 |

## 4. 待用户确认项

无新增（强度规则严格对齐 design§5/§6 与任务 DoD）。如需熵阈值（非单字符）可后续扩展。

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| 评审方独立严格全量 `pytest tests -q -W error::...`（含 test_secret_strength 21 用例） | **310 passed / 0 failed** | 0 | `evidence/test-rerun-20261112/backend-final-full-regression-reviewer.log` |
| Lead 最终全量日志 | 310 passed（135.09s） | 0 | `docs/verification/tasks/FULL-REGRESSION-final-20261112.log` |
| 开发启动矩阵（真实 uvicorn，8 弱拒绝 + legal/fresh healthy） | PASS | 0 | `docs/verification/tasks/T-18/startup-matrix-20261112.log` + `.json` |
| 开发绿测 test_secret_strength.py | 21 passed | 0 | `docs/verification/tasks/T-18/pytest-T18-green-20261112.log` |

## 6. 最终结论

**通过（host 侧真实启动矩阵 + 单测 + 独立全量）。** SECRET_KEY 强度校验（≥32、拒空/占位及变体/单字符重复）、错误日志不回显密钥值、compose `${SECRET_KEY:?}` 强制显式、.env.example/DEPLOYMENT 同步均落地并经真实 uvicorn 启动矩阵验证：8 类弱/占位/短密钥全部 exit=3 拒绝、合法密钥 /health=200、fresh 空库 /health=200。独立严格全量 310 passed。限制：Docker 容器内 compose `:?` 展开与容器启动因主机无 docker 未核验（L1/P-T18-1），host 侧等效已验证，不影响密钥拒绝结论；R27 容器运行时仍记"无法核验"。

## 7. 签名

reviewer，2026-11-12；本记录基于源码、启动矩阵原始日志、单测与独立全量日志作出，未替开发修改任何代码；未执行 docker（本机不可用）。
