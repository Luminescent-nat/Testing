#!/bin/bash

echo "========== 测试平台快速启动脚本 =========="
echo ""

# 清理缓存
echo "[1/3] 清理Python缓存..."
cd test-platform/backend
find . -name "*.pyc" -delete 2>/dev/null
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
echo "✅ 缓存清理完成"
echo ""

# 初始化数据库（不删除已有数据，init_db.py 只做建表/迁移）
echo "[2/3] 初始化数据库..."
python init_db.py
echo "✅ 数据库初始化完成"
echo ""

# 启动服务
echo "[3/3] 启动后端服务..."
python -c "
import uvicorn
uvicorn.run('app.main:app', host='0.0.0.0', port=8000, reload=False)
" &

sleep 5

echo ""
echo "✅ 服务启动完成！"
echo ""
echo "📍 访问地址:"
echo "   - API文档: http://localhost:8000/docs"
echo "   - 前端页面: http://localhost:3000"
echo ""
echo "📱 已连接ADB设备:"
adb devices -l
echo ""
echo "🧪 测试命令:"
echo "   curl -X POST http://localhost:8000/api/v1/auth/register \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"username\": \"admin\", \"password\": \"admin123\", \"email\": \"admin@test.com\"}'"
