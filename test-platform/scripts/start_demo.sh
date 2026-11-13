#!/bin/bash
# ============================================================
#  测试平台 — 演示环境启动脚本（Linux/macOS，兼容 Git Bash）
#
#  演示专用：使用独立 demo.db + storage/demo/，**绝不触碰历史库**
#  backend/test_platform.db（其结构漂移在严格 init_db 下会 SchemaMismatchError
#  拒绝启动，属预期；严禁对任何真实库执行 alembic downgrade base）。
#
#  用法：
#    bash scripts/start_demo.sh
#    bash scripts/start_demo.sh --port 8001
#    bash scripts/start_demo.sh --secret-key "<32+字符随机密钥>"
#    bash scripts/start_demo.sh --migrate-only      # 仅建演示库后退出
#
#  环境变量（本脚本显式设置，覆盖 backend/.env 中的 DATABASE_URL 等）：
#    DATABASE_URL   = sqlite+aiosqlite:///./demo.db
#    STORAGE_PATH   = storage/demo
#    TOOLS_PATH     = storage/demo/tools
#    REPORTS_PATH   = storage/demo/reports
#    LOGS_PATH      = storage/demo/logs
#    TEST_TOOLS_PATH= ../test-tools
#  SECRET_KEY 解析顺序：--secret-key > $DEMO_SECRET_KEY > $SECRET_KEY
#    > backend/.env 中的 SECRET_KEY > 本次运行临时生成（仅当次有效）
# ============================================================
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV_PY="$ROOT/.venv/bin/python"
[ -f "$ROOT/.venv/Scripts/python.exe" ] && VENV_PY="$ROOT/.venv/Scripts/python.exe"

SECRET_KEY_ARG=""
PORT=8000
SKIP_MIGRATE=0
MIGRATE_ONLY=0
DEMO_DB="./demo.db"
STORAGE_ROOT="storage/demo"

while [ $# -gt 0 ]; do
  case "$1" in
    --secret-key) SECRET_KEY_ARG="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --skip-migrate) SKIP_MIGRATE=1; shift ;;
    --migrate-only) MIGRATE_ONLY=1; shift ;;
    --demo-db) DEMO_DB="$2"; shift 2 ;;
    --storage-root) STORAGE_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

if [ ! -f "$VENV_PY" ]; then
  echo "[错误] 未找到虚拟环境 $VENV_PY，请先运行 start_server.sh 或手动创建 .venv 并安装 backend/requirements.txt" >&2
  exit 1
fi

echo "========== 测试平台 · 演示环境 =========="
echo "历史库 backend/test_platform.db 保留不动（只读）；演示使用独立 $DEMO_DB + $STORAGE_ROOT/"
echo "注意：历史库存在结构漂移，严格 init_db 会 SchemaMismatchError 拒绝启动，属预期；严禁 alembic downgrade base。"

# ---------- 1. 演示环境变量（隔离） ----------
export DATABASE_URL="sqlite+aiosqlite:///$DEMO_DB"
export STORAGE_PATH="$STORAGE_ROOT"
export TOOLS_PATH="$STORAGE_ROOT/tools"
export REPORTS_PATH="$STORAGE_ROOT/reports"
export LOGS_PATH="$STORAGE_ROOT/logs"
export TEST_TOOLS_PATH="../test-tools"

# ---------- 2. SECRET_KEY ----------
env_file_key() {
  [ -f "$BACKEND/.env" ] || return 0
  sed -n 's/^[[:space:]]*SECRET_KEY[[:space:]]*=[[:space:]]*//p' "$BACKEND/.env" | head -1 | tr -d '"'"'"''
}
if [ -n "$SECRET_KEY_ARG" ]; then
  export SECRET_KEY="$SECRET_KEY_ARG"
elif [ -n "${DEMO_SECRET_KEY:-}" ]; then
  export SECRET_KEY="$DEMO_SECRET_KEY"
elif [ -z "${SECRET_KEY:-}" ]; then
  FROM_FILE="$(env_file_key)"
  if [ -n "$FROM_FILE" ]; then
    export SECRET_KEY="$FROM_FILE"
    echo "[SECRET_KEY] 使用 backend/.env 中的密钥"
  else
    export SECRET_KEY="$("$VENV_PY" -c 'import secrets;print(secrets.token_urlsafe(48))')"
    echo "[SECRET_KEY] 未配置，已生成仅本次运行有效的临时随机密钥（如需持久化请写入 backend/.env）"
  fi
fi

# ---------- 3. 演示存储目录 ----------
mkdir -p "$STORAGE_ROOT/tools" "$STORAGE_ROOT/reports" "$STORAGE_ROOT/logs"

# ---------- 4. 首次/升级：alembic upgrade head（空库 001→004，幂等） ----------
if [ "$SKIP_MIGRATE" -eq 0 ]; then
  echo "[1/2] 初始化演示库（alembic upgrade head，空库 001→004，幂等）..."
  ( cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head && "$VENV_PY" -m alembic current )
else
  echo "[1/2] 跳过迁移（--skip-migrate）"
fi

# ---------- 5. 启动服务 ----------
echo "[2/2] 启动演示服务..."
echo "  演示库:      $BACKEND/$DEMO_DB"
echo "  存储目录:    $BACKEND/$STORAGE_ROOT/{tools,reports,logs}"
echo "  平台地址:    http://localhost:$PORT"
echo "  API 文档:    http://localhost:$PORT/docs"
echo "  首次使用请在登录页注册账号（首个注册用户自动成为管理员）。"
echo "  提示：演示请只用只读测试项（如 cat /proc/meminfo），不要写入/烧录/重启/压测；daily/once 演示禁用。"
if [ "$MIGRATE_ONLY" -eq 1 ]; then
  echo "[MigrateOnly] 已完成演示库初始化，未启动服务。"
  exit 0
fi

cd "$BACKEND"
exec "$VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
