#!/bin/bash

# 测试平台启动脚本

echo "=== 测试平台启动脚本 ==="

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python版本: $python_version"

# 安装依赖
echo "正在安装依赖..."
pip install -r requirements.txt

# 初始化数据库
echo "正在初始化数据库..."
python init_db.py

# 启动服务
echo "正在启动FastAPI服务..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
