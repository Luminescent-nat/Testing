#!/bin/bash
# Windows测试启动脚本

echo "========== 测试平台Windows启动脚本 =========="
echo ""

# 1. 清理缓存
echo "[1/4] 清理Python缓存..."
cd test-platform/backend
find . -name "*.pyc" -delete 2>/dev/null
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
rm -rf app/__pycache__ app/*/__pycache__ 2>/dev/null
echo "✓ 缓存清理完成"

# 2. 初始化数据库（不删除已有数据，init_db.py 只做建表/迁移）
echo "[2/4] 初始化数据库..."
python init_db.py
echo "✓ 数据库初始化完成"

# 3. 测试密码功能
echo "[3/4] 测试密码功能..."
python -c "
import sys
sys.path.insert(0, '.')
from app.services.auth import get_password_hash, verify_password
h = get_password_hash('test123')
assert verify_password('test123', h), 'Password verification failed'
print('✓ 密码功能测试通过')
"

# 4. 启动服务
echo "[4/4] 启动服务..."
echo ""
echo "服务正在启动，请稍候..."
echo ""

python start.py &

sleep 5

echo ""
echo "========== 服务启动完成 =========="
echo ""
echo "✓ API文档: http://localhost:8000/docs"
echo "✓ 健康检查: http://localhost:8000/health"
echo ""
echo "📱 ADB设备:"
adb devices -l
echo ""
echo "🧪 快速测试:"
echo "  curl -X POST http://localhost:8000/api/v1/auth/register \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"username\": \"admin\", \"password\": \"admin123\", \"email\": \"admin@test.com\"}'"
echo ""

# 测试注册
echo "正在测试用户注册..."
RESULT=$(curl -s -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123", "email": "admin@test.com"}')
  
if echo "$RESULT" | grep -q '"code":200'; then
  echo "✅ 用户注册成功！"
  echo ""
  echo "🎉 系统测试完成，可以正常使用！"
else
  echo "❌ 注册失败: $RESULT"
  echo ""
  echo "建议：重新运行此脚本或重启电脑清除缓存"
fi
