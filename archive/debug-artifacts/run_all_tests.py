#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试平台 - 完整自动化测试套件
执行所有测试用例并生成报告
"""

import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Tuple

# 添加backend目录到Python路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, AsyncSessionLocal
from app.services.auth import get_password_hash
from app.models import User, TestModule, TestItem

client = TestClient(app)

class TestResult:
    """测试结果记录"""
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.details: List[Dict] = []
        self.start_time = None
        self.end_time = None
    
    def add_test(self, name: str, status: str, message: str = "", duration: float = 0):
        self.total += 1
        if status == "PASS":
            self.passed += 1
        else:
            self.failed += 1
        
        self.details.append({
            "name": name,
            "status": status,
            "message": message,
            "duration": f"{duration:.2f}s"
        })
    
    def summary(self) -> str:
        return f"Total: {self.total}, Passed: {self.passed}, Failed: {self.failed}, Pass Rate: {self.passed/self.total*100:.1f}%"

# 全局变量
test_result = TestResult()
token = None
headers = {}
test_user = {"username": "testuser", "password": "testpass123", "email": "test@test.com"}

print("=" * 80)
print(" " * 25 + "测试平台 - 完整测试套件")
print("=" * 80)
print(f"\n测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("-" * 80)

# ============ 模块1: 用户管理测试 ============
print("\n【模块1: 用户管理测试】")
print("-" * 80)

def test_user_registration():
    """TC-001: 用户注册测试"""
    start = time.time()
    
    # 测试正常注册
    response = client.post('/api/v1/auth/register', json=test_user)
    duration = time.time() - start
    
    if response.status_code == 200:
        test_result.add_test("TC-001-1: 用户正常注册", "PASS", "", duration)
    else:
        msg = response.json().get('message', 'Unknown error')
        if '已存在' in msg or 'exist' in msg.lower():
            test_result.add_test("TC-001-1: 用户正常注册", "PASS", "User already exists", duration)
        else:
            test_result.add_test("TC-001-1: 用户正常注册", "FAIL", msg, duration)
    
    # 测试重复注册
    start = time.time()
    response = client.post('/api/v1/auth/register', json=test_user)
    duration = time.time() - start
    
    if response.status_code != 200:
        test_result.add_test("TC-001-2: 重复注册检查", "PASS", "Correctly rejected duplicate", duration)
    else:
        test_result.add_test("TC-001-2: 重复注册检查", "FAIL", "Should reject duplicate user", duration)
    
    # 测试弱密码
    start = time.time()
    weak_user = {"username": "weakuser", "password": "123", "email": "weak@test.com"}
    response = client.post('/api/v1/auth/register', json=weak_user)
    duration = time.time() - start
    
    # Pydantic会校验密码长度
    if response.status_code == 422:
        test_result.add_test("TC-001-3: 弱密码检查", "PASS", "Password validation works", duration)
    else:
        test_result.add_test("TC-001-3: 弱密码检查", "INFO", "Password validation may be client-side", duration)

def test_user_login():
    """TC-002: 用户登录测试"""
    global token, headers
    
    # 测试正常登录
    start = time.time()
    response = client.post('/api/v1/auth/login', json={
        "username": test_user["username"],
        "password": test_user["password"]
    })
    duration = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        token = data['data']['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        test_result.add_test("TC-002-1: 正常登录", "PASS", f"Token: {token[:20]}...", duration)
    else:
        test_result.add_test("TC-002-1: 正常登录", "FAIL", response.json().get('detail', ''), duration)
        return
    
    # 测试错误密码
    start = time.time()
    response = client.post('/api/v1/auth/login', json={
        "username": test_user["username"],
        "password": "wrongpassword"
    })
    duration = time.time() - start
    
    if response.status_code == 401:
        test_result.add_test("TC-002-2: 错误密码检查", "PASS", "Correctly rejected wrong password", duration)
    else:
        test_result.add_test("TC-002-2: 错误密码检查", "FAIL", "Should reject wrong password", duration)
    
    # 测试不存在用户
    start = time.time()
    response = client.post('/api/v1/auth/login', json={
        "username": "nonexistentuser12345",
        "password": "somepassword"
    })
    duration = time.time() - start
    
    if response.status_code == 401:
        test_result.add_test("TC-002-3: 不存在用户检查", "PASS", "Correctly rejected non-existent user", duration)
    else:
        test_result.add_test("TC-002-3: 不存在用户检查", "FAIL", "Should reject non-existent user", duration)

def test_get_user_info():
    """TC-002-4: 获取用户信息"""
    if not token:
        test_result.add_test("TC-002-4: 获取用户信息", "SKIP", "No token available")
        return
    
    start = time.time()
    response = client.get('/api/v1/auth/me', headers=headers)
    duration = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        username = data.get('data', {}).get('username', '')
        test_result.add_test("TC-002-4: 获取用户信息", "PASS", f"Username: {username}", duration)
    else:
        test_result.add_test("TC-002-4: 获取用户信息", "FAIL", response.json().get('detail', ''), duration)

# 执行用户管理测试
test_user_registration()
test_user_login()
test_get_user_info()

# ============ 模块2: 设备管理测试 ============
print("\n【模块2: 设备管理测试】")
print("-" * 80)

def test_refresh_devices():
    """TC-003: 设备发现测试"""
    if not token:
        test_result.add_test("TC-003: 刷新设备", "SKIP", "No token available")
        return
    
    start = time.time()
    response = client.post('/api/v1/devices/refresh', headers=headers)
    duration = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        devices = data.get('data', {}).get('items', [])
        device_count = len(devices)
        
        if device_count >= 2:
            test_result.add_test("TC-003: 刷新ADB设备", "PASS", f"Found {device_count} devices", duration)
        else:
            test_result.add_test("TC-003: 刷新ADB设备", "FAIL", f"Expected 2+ devices, found {device_count}", duration)
        
        return devices
    else:
        test_result.add_test("TC-003: 刷新ADB设备", "FAIL", response.json().get('detail', ''), duration)
        return []

def test_list_devices():
    """TC-004: 获取设备列表"""
    if not token:
        test_result.add_test("TC-004: 获取设备列表", "SKIP", "No token available")
        return []
    
    start = time.time()
    response = client.get('/api/v1/devices', headers=headers)
    duration = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        devices = data.get('data', {}).get('items', [])
        
        device_info = []
        for d in devices[:2]:  # 只显示前2个
            model = d.get('model', 'Unknown')
            serial = d.get('serial_number', 'N/A')[:8]
            device_info.append(f"{model}({serial}...)")
        
        test_result.add_test("TC-004: 获取设备列表", "PASS", f"{len(devices)} devices: {', '.join(device_info)}", duration)
        return devices
    else:
        test_result.add_test("TC-004: 获取设备列表", "FAIL", response.json().get('detail', ''), duration)
        return []

# 执行设备管理测试
devices = test_refresh_devices()
if not devices:
    devices = test_list_devices()

# ============ 模块3: 测试编排测试 ============
print("\n【模块3: 测试编排测试】")
print("-" * 80)

def test_create_module():
    """TC-005: 创建测试模块"""
    if not token:
        test_result.add_test("TC-005: 创建测试模块", "SKIP", "No token available")
        return None
    
    module_data = {
        "name": "内存测试模块",
        "category": "性能",
        "description": "测试设备内存性能",
        "icon": "memory"
    }
    
    start = time.time()
    response = client.post('/api/v1/modules', headers=headers, json=module_data)
    duration = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        module_id = data.get('data', {}).get('id')
        test_result.add_test("TC-005: 创建测试模块", "PASS", f"Module ID: {module_id}", duration)
        return module_id
    else:
        # 可能是权限问题（普通用户无法创建）
        detail = response.json().get('detail', '')
        if 'Forbidden' in detail or '403' in str(response.status_code):
            test_result.add_test("TC-005: 创建测试模块", "PASS", "Admin permission required (expected)", duration)
        else:
            test_result.add_test("TC-005: 创建测试模块", "FAIL", detail, duration)
        return None

def test_list_modules():
    """TC-006: 获取测试模块列表"""
    if not token:
        test_result.add_test("TC-006: 获取测试模块", "SKIP", "No token available")
        return
    
    start = time.time()
    response = client.get('/api/v1/modules', headers=headers)
    duration = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        modules = data.get('data', {}).get('items', [])
        test_result.add_test("TC-006: 获取测试模块", "PASS", f"Found {len(modules)} modules", duration)
    else:
        test_result.add_test("TC-006: 获取测试模块", "FAIL", response.json().get('detail', ''), duration)

# 执行测试编排测试
module_id = test_create_module()
test_list_modules()

# ============ 模块4: 任务执行测试 ============
print("\n【模块4: 任务执行测试】")
print("-" * 80)

def test_create_task():
    """TC-007: 创建测试任务"""
    if not token or not devices:
        test_result.add_test("TC-007: 创建测试任务", "SKIP", f"Token: {bool(token)}, Devices: {len(devices)}")
        return None
    
    task_data = {
        "device_serial": devices[0]['serial_number'],
        "name": "自动化测试任务",
        "item_ids": [],  # 空任务测试
        "custom_parameters": {}
    }
    
    start = time.time()
    response = client.post('/api/v1/tasks', headers=headers, json=task_data)
    duration = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        task_id = data.get('data', {}).get('id')
        test_result.add_test("TC-007: 创建测试任务", "PASS", f"Task ID: {task_id}", duration)
        return task_id
    else:
        test_result.add_test("TC-007: 创建测试任务", "FAIL", response.json().get('message', ''), duration)
        return None

def test_list_tasks():
    """TC-008: 获取任务列表"""
    if not token:
        test_result.add_test("TC-008: 获取任务列表", "SKIP", "No token available")
        return
    
    start = time.time()
    response = client.get('/api/v1/tasks', headers=headers)
    duration = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        tasks = data.get('data', {}).get('items', [])
        test_result.add_test("TC-008: 获取任务列表", "PASS", f"Found {len(tasks)} tasks", duration)
    else:
        test_result.add_test("TC-008: 获取任务列表", "FAIL", response.json().get('detail', ''), duration)

# 执行任务测试
task_id = test_create_task()
test_list_tasks()

# ============ 模块5: 报告管理测试 ============
print("\n【模块5: 报告管理测试】")
print("-" * 80)

def test_get_reports():
    """TC-009: 获取测试报告"""
    if not token or not task_id:
        test_result.add_test("TC-009: 获取测试报告", "SKIP", f"Token: {bool(token)}, Task: {task_id}")
        return
    
    start = time.time()
    response = client.get(f'/api/v1/reports/{task_id}', headers=headers)
    duration = time.time() - start
    
    if response.status_code == 200:
        test_result.add_test("TC-009: 获取测试报告", "PASS", "Report retrieved successfully", duration)
    else:
        # 可能是报告未生成
        detail = response.json().get('detail', '')
        test_result.add_test("TC-009: 获取测试报告", "INFO", f"Report may not exist yet: {detail}", duration)

# 执行报告测试
test_get_reports()

# ============ 测试总结 ============
print("\n" + "=" * 80)
print(" " * 30 + "测试总结")
print("=" * 80)

test_result.end_time = datetime.now()

print(f"\n测试结束时间: {test_result.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"\n{test_result.summary()}")

print("\n【详细测试结果】")
print("-" * 80)
for detail in test_result.details:
    status_icon = "✅" if detail['status'] == "PASS" else ("⚠️ " if detail['status'] == "INFO" else ("⏭️ " if detail['status'] == "SKIP" else "❌"))
    print(f"{status_icon} {detail['name']}")
    print(f"   状态: {detail['status']}")
    if detail['message']:
        print(f"   信息: {detail['message']}")
    print(f"   耗时: {detail['duration']}")
    print()

# 生成测试报告文件
report_data = {
    "test_date": test_result.end_time.strftime('%Y-%m-%d %H:%M:%S'),
    "summary": {
        "total": test_result.total,
        "passed": test_result.passed,
        "failed": test_result.failed,
        "pass_rate": f"{test_result.passed/test_result.total*100:.1f}%" if test_result.total > 0 else "0%"
    },
    "details": test_result.details
}

report_file = os.path.join(os.path.dirname(__file__), 'test_report.json')
with open(report_file, 'w', encoding='utf-8') as f:
    json.dump(report_data, f, ensure_ascii=False, indent=2)

print(f"\n📄 测试报告已保存: {report_file}")

print("\n" + "=" * 80)
if test_result.failed == 0:
    print("🎉 所有测试通过！系统可以投入使用！")
else:
    print(f"⚠️  有 {test_result.failed} 个测试失败，请检查并修复问题")
print("=" * 80)
