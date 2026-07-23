#!/bin/bash

echo "========== 测试平台功能测试报告 =========="
echo "测试时间: $(date)"
echo ""

BASE_URL="http://localhost:8000/api/v1"
TOKEN=""

# 1. 测试健康检查
echo "[1/8] 测试健康检查..."
HEALTH=$(curl -s "$BASE_URL/../health")
echo "✅ 健康检查: $HEALTH"
echo ""

# 2. 测试用户注册
echo "[2/8] 测试用户注册..."
REGISTER=$(curl -s -X POST "$BASE_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username": "testadmin", "password": "admin123", "email": "admin@test.com"}')
if echo "$REGISTER" | grep -q '"code":200'; then
  echo "✅ 注册成功"
else
  echo "❌ 注册失败: $REGISTER"
fi
echo ""

# 3. 测试用户登录
echo "[3/8] 测试用户登录..."
LOGIN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "testadmin", "password": "admin123"}')
if echo "$LOGIN" | grep -q '"code":200'; then
  TOKEN=$(echo $LOGIN | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
  echo "✅ 登录成功"
  echo "   Token: ${TOKEN:0:50}..."
else
  echo "❌ 登录失败: $LOGIN"
fi
echo ""

# 4. 测试获取用户信息
echo "[4/8] 测试获取用户信息..."
if [ -n "$TOKEN" ]; then
  ME=$(curl -s "$BASE_URL/auth/me" -H "Authorization: Bearer $TOKEN")
  if echo "$ME" | grep -q '"code":200'; then
    echo "✅ 获取用户信息成功"
  else
    echo "❌ 获取用户信息失败: $ME"
  fi
else
  echo "⚠️  跳过（无Token）"
fi
echo ""

# 5. 测试设备刷新（需要ADB设备）
echo "[5/8] 测试设备刷新（发现ADB设备）..."
if [ -n "$TOKEN" ]; then
  DEVICES=$(curl -s -X POST "$BASE_URL/devices/refresh" \
    -H "Authorization: Bearer $TOKEN")
  if echo "$DEVICES" | grep -q '"code":200'; then
    echo "✅ 设备刷新成功"
    echo "   发现设备: $(echo $DEVICES | grep -o '"found_devices":[0-9]*' | cut -d':' -f2) 台"
  else
    echo "❌ 设备刷新失败: $DEVICES"
  fi
else
  echo "⚠️  跳过（无Token）"
fi
echo ""

# 6. 测试获取设备列表
echo "[6/8] 测试获取设备列表..."
if [ -n "$TOKEN" ]; then
  LIST=$(curl -s "$BASE_URL/devices" -H "Authorization: Bearer $TOKEN")
  if echo "$LIST" | grep -q '"code":200'; then
    echo "✅ 获取设备列表成功"
  else
    echo "❌ 获取设备列表失败: $LIST"
  fi
else
  echo "⚠️  跳过（无Token）"
fi
echo ""

# 7. 测试获取测试模块
echo "[7/8] 测试获取测试模块..."
if [ -n "$TOKEN" ]; then
  MODULES=$(curl -s "$BASE_URL/modules" -H "Authorization: Bearer $TOKEN")
  if echo "$MODULES" | grep -q '"code":200'; then
    echo "✅ 获取测试模块成功"
  else
    echo "❌ 获取测试模块失败: $MODULES"
  fi
else
  echo "⚠️  跳过（无Token）"
fi
echo ""

# 8. 测试获取任务列表
echo "[8/8] 测试获取任务列表..."
if [ -n "$TOKEN" ]; then
  TASKS=$(curl -s "$BASE_URL/tasks" -H "Authorization: Bearer $TOKEN")
  if echo "$TASKS" | grep -q '"code":200'; then
    echo "✅ 获取任务列表成功"
  else
    echo "❌ 获取任务列表失败: $TASKS"
  fi
else
  echo "⚠️  跳过（无Token）"
fi
echo ""

echo "========== 测试完成 =========="
echo ""
echo "📱 ADB设备状态:"
adb devices -l
echo ""
echo "🌐 API文档地址: http://localhost:8000/docs"
