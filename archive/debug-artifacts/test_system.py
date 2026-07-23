#!/usr/bin/env python3
"""
Windows测试平台启动器
"""

import sys
sys.path.insert(0, '.')

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import init_db, AsyncSessionLocal
from app.services.auth import get_password_hash
from app.models import User

async def setup_test_data():
    """初始化测试数据"""
    print("Initializing database...")
    await init_db()
    
    async with AsyncSessionLocal() as db:
        # 创建测试用户
        user = User(
            username='admin',
            password_hash=get_password_hash('admin123'),
            role='admin',
            status='active'
        )
        db.add(user)
        await db.commit()
        print("Test user created: admin/admin123")

# 先初始化数据库
asyncio.run(setup_test_data())

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_login():
    """测试用户登录"""
    print("\n[1/5] Testing user login...")
    response = client.post(
        '/api/v1/auth/login',
        json={'username': 'admin', 'password': 'admin123'}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print("[PASS] Login successful")
        return data['data']['access_token']
    else:
        print(f"[FAIL] Login failed: {response.json()}")
        return None

def test_get_user_info(token):
    """测试获取用户信息"""
    print("\n[2/5] Testing get user info...")
    response = client.get(
        '/api/v1/auth/me',
        headers={'Authorization': f'Bearer {token}'}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("[PASS] Get user info successful")
        return True
    else:
        print(f"[FAIL] Get user info failed: {response.json()}")
        return False

def test_refresh_devices(token):
    """测试刷新设备"""
    print("\n[3/5] Testing refresh ADB devices...")
    response = client.post(
        '/api/v1/devices/refresh',
        headers={'Authorization': f'Bearer {token}'}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"[PASS] Found {data['data'].get('found_devices', 0)} devices")
        return True
    else:
        print(f"[FAIL] Refresh failed: {response.json()}")
        return False

def test_list_devices(token):
    """测试获取设备列表"""
    print("\n[4/5] Testing list devices...")
    response = client.get(
        '/api/v1/devices',
        headers={'Authorization': f'Bearer {token}'}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        devices = data['data'].get('items', [])
        print(f"[PASS] Found {len(devices)} devices")
        for device in devices:
            print(f"  - {device.get('model', 'Unknown')} ({device.get('serial_number', 'N/A')})")
        return True
    else:
        print(f"[FAIL] List devices failed: {response.json()}")
        return False

def test_get_modules(token):
    """测试获取测试模块"""
    print("\n[5/5] Testing get test modules...")
    response = client.get(
        '/api/v1/modules',
        headers={'Authorization': f'Bearer {token}'}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("[PASS] Get test modules successful")
        return True
    else:
        print(f"[FAIL] Get test modules failed: {response.json()}")
        return False

def main():
    print("=" * 60)
    print("Test Platform System Test")
    print("=" * 60)
    
    results = []
    
    # 1. Login
    token = test_login()
    results.append(("User Login", token is not None))
    
    if token:
        # 2. Get user info
        results.append(("Get User Info", test_get_user_info(token)))
        
        # 3. Refresh devices
        results.append(("Refresh ADB Devices", test_refresh_devices(token)))
        
        # 4. List devices
        results.append(("List Devices", test_list_devices(token)))
        
        # 5. Get modules
        results.append(("Get Test Modules", test_get_modules(token)))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n*** All tests passed! System is working! ***")
    else:
        print(f"\n*** {total - passed} tests failed ***")
    
    print("=" * 60)
    
    # ADB devices info
    print("\nConnected ADB Devices:")
    import subprocess
    result = subprocess.run(['adb', 'devices', '-l'], capture_output=True, text=True)
    print(result.stdout)

if __name__ == "__main__":
    main()
