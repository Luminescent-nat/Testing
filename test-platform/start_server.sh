#!/bin/bash
# 测试平台 Linux 裸机一键启动脚本（Docker 部署请用 docker compose up -d --build）
set -e

# 从脚本所在目录解析路径，不依赖调用时的工作目录
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"
[ -f "$VENV/Scripts/python.exe" ] && VENV_PY="$VENV/Scripts/python.exe"  # 兼容 Windows venv 布局

echo "========== 测试平台启动 =========="

# 1. 虚拟环境
if [ ! -f "$VENV_PY" ]; then
  echo "[1/4] 创建虚拟环境 .venv ..."
  python3 -m venv "$VENV"
else
  echo "[1/4] 虚拟环境已存在，跳过。"
fi

# 2. 依赖
echo "[2/4] 安装/校验后端依赖..."
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r "$BACKEND/requirements.txt"

# 3. 首次运行生成 .env（随机 SECRET_KEY，未配置时应用拒绝启动）
if [ ! -f "$BACKEND/.env" ]; then
  echo "[3/4] 生成 backend/.env（随机 SECRET_KEY）..."
  "$VENV_PY" -c "import secrets,pathlib; pathlib.Path(r'$BACKEND/.env').write_text('SECRET_KEY=' + secrets.token_urlsafe(48) + '\n', encoding='utf-8')"
else
  echo "[3/4] backend/.env 已存在，跳过。"
fi

# 4. 启动（建表/种子数据/中断状态恢复在应用 lifespan 中自动完成；
#    存量库结构升级请先执行: cd backend && alembic upgrade head）
echo "[4/4] 启动服务..."
echo ""
echo "  平台地址:  http://localhost:8000      （前端页面，同源提供）"
echo "  API 文档:  http://localhost:8000/docs"
echo "  首次使用请在登录页注册账号（首个注册用户自动成为管理员）。"
echo ""
cd "$BACKEND"
exec "$VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
