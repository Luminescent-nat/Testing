#!/usr/bin/env python3
"""执行一轮 EMMC 自动化测试并输出报告。"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin123"
MODULE_NAME = "EMMC"


def login():
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": USERNAME, "password": PASSWORD})
    r.raise_for_status()
    data = r.json()["data"]
    print(f"[登录] {USERNAME} -> role={data['user']['role']}")
    return data["access_token"]


def get_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def refresh_devices(token):
    r = requests.post(f"{BASE_URL}/devices/refresh", headers=get_headers(token))
    r.raise_for_status()
    data = r.json()["data"]
    print(f"[设备刷新] 发现 {data['found_devices']} 台设备")
    return data["items"]


def get_emmc_module(token):
    r = requests.get(f"{BASE_URL}/modules", headers=get_headers(token))
    r.raise_for_status()
    for m in r.json()["data"]["items"]:
        if m["name"] == MODULE_NAME:
            r2 = requests.get(f"{BASE_URL}/modules/{m['id']}", headers=get_headers(token))
            r2.raise_for_status()
            return r2.json()["data"]
    raise RuntimeError("未找到 EMMC 模块")


def create_task(token, device_serial, item_ids):
    payload = {
        "device_serial": device_serial,
        "name": f"EMMC自动化测试_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "item_ids": item_ids,
        "custom_parameters": {}
    }
    r = requests.post(f"{BASE_URL}/tasks", headers=get_headers(token), json=payload)
    r.raise_for_status()
    task = r.json()["data"]
    print(f"[创建任务] id={task['id']} name={task['name']} device={task.get('device_serial')}")
    return task["id"]


def wait_task(token, task_id, timeout=600, interval=3):
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{BASE_URL}/tasks/{task_id}", headers=get_headers(token))
        r.raise_for_status()
        task = r.json()["data"]
        status = task["status"]
        progress = task.get("progress_percent", 0)
        print(f"[任务 {task_id}] status={status} progress={progress}%")
        if status in ("completed", "failed", "cancelled"):
            return task
        time.sleep(interval)
    raise RuntimeError("等待任务完成超时")


def get_records(token, task_id):
    r = requests.get(f"{BASE_URL}/tasks/{task_id}/records", headers=get_headers(token))
    r.raise_for_status()
    return r.json()["data"]["items"]


def get_report(token, task_id):
    r = requests.get(f"{BASE_URL}/reports/{task_id}", headers=get_headers(token))
    if r.status_code == 200:
        return r.json()["data"]
    return None


def main():
    token = login()
    devices = refresh_devices(token)
    online = [d for d in devices if d["status"] == "online"]
    if not online:
        print("[错误] 没有在线设备可测试")
        sys.exit(1)
    device = online[0]
    print(f"[选用设备] serial={device['serial_number']} model={device.get('model')} android={device.get('android_version')}")

    module = get_emmc_module(token)
    item_ids = [item["id"] for item in module["items"] if item.get("enabled", True)]
    print(f"[EMMC 测试项] 共 {len(item_ids)} 项: {item_ids}")

    task_id = create_task(token, device["serial_number"], item_ids)
    task = wait_task(token, task_id)

    records = get_records(token, task_id)
    print(f"\n[测试记录] 共 {len(records)} 条")

    status_count = {"pass": 0, "fail": 0, "skip": 0, "error": 0, "running": 0, "pending": 0}
    for rec in records:
        status = rec["status"]
        status_count[status] = status_count.get(status, 0) + 1
        print(f"  - {rec['item_name']}: {status.upper()} | 耗时={rec.get('execution_time')}s")
        if rec.get("fail_reason"):
            print(f"      失败原因: {rec['fail_reason']}")
        if rec.get("extracted_data"):
            print(f"      提取数据: {json.dumps(rec['extracted_data'], ensure_ascii=False)[:200]}")

    print(f"\n[汇总] pass={status_count.get('pass',0)} fail={status_count.get('fail',0)} "
          f"skip={status_count.get('skip',0)} error={status_count.get('error',0)}")

    report = get_report(token, task_id)
    if report:
        print(f"\n[报告] report_id={report.get('report_id')} pass_rate={report['summary']['pass_rate']}")
    else:
        print("\n[报告] 报告接口暂时不可用")

    # 保存原始记录到文件
    out_path = Path(f"emmc_test_result_task_{task_id}.json")
    out_path.write_text(json.dumps({"task": task, "records": records, "report": report}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[结果已保存] {out_path.absolute()}")


if __name__ == "__main__":
    main()
