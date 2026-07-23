#!/bin/bash

echo "========== 测试平台功能测试 =========="
echo ""

BASE_URL="http://localhost:8000/api/v1"

echo "1. 测试用户注册..."
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "password123", "email": "test@test.com"}')
echo "注册响应: $REGISTER_RESPONSE"
echo ""

echo "2. 测试用户登录..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "password123"}')
echo "登录响应: $LOGIN_RESPONSE"
echo ""

# 提取token
TOKEN=$(echo $LOGIN_RESPONSE | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
echo "获取Token: ${TOKEN:0:50}..."
echo ""

echo "3. 测试设备刷新（发现ADB设备）..."
DEVICES_RESPONSE=$(curl -s -X POST "$BASE_URL/devices/refresh" \
  -H "Authorization: Bearer $TOKEN")
echo "设备响应: $DEVICES_RESPONSE"
echo ""

echo "4. 测试获取设备列表..."
DEVICES_LIST=$(curl -s -X GET "$BASE_URL/devices" \
  -H "Authorization: Bearer $TOKEN")
echo "设备列表: $DEVICES_LIST"
echo ""

echo "5. 测试获取测试模块..."
MODULES_RESPONSE=$(curl -s -X GET "$BASE_URL/modules" \
  -H "Authorization: Bearer $TOKEN")
echo "模块响应: $MODULES_RESPONSE"
echo ""

echo "========== 测试完成 =========="
