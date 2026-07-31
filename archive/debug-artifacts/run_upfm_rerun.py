# -*- coding: utf-8 -*-
"""UPFM 全量任务执行验证：刷新设备 → 创建任务(27项) → 轮询 → 输出结果。"""
import json
import sys
import time

import requests

BASE = "http://localhost:8000/api/v1"
USER = {"username": "e2e-admin", "password": "e2e-admin-pass"}
OUT = r"D:\MCTEST\archive\debug-artifacts\upfm_rerun_records.json"

def main():
    tok = requests.post(f"{BASE}/auth/login", json=USER, timeout=15).json()["data"]["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    # 1. 刷新设备（新版代码支持自动登记）
    r = requests.post(f"{BASE}/devices/refresh", headers=H, timeout=120)
    print("refresh:", r.status_code, r.text[:200])
    devices = requests.get(f"{BASE}/devices", headers=H, timeout=15).json()["data"]
    dev_list = devices if isinstance(devices, list) else devices.get("items", devices.get("devices", []))
    online = [d for d in dev_list if d.get("status") == "online"]
    print("devices:", [(d["id"], d["serial_number"], d["status"]) for d in dev_list])
    if not online:
        print("NO ONLINE DEVICE"); sys.exit(2)
    dev = online[0]

    # 2. UPFM 测试项
    items = requests.get(f"{BASE}/modules/7", headers=H, timeout=15).json()["data"]["items"]
    item_ids = [i["id"] for i in items]
    print("items:", len(item_ids))

    # 3. 创建任务
    payload = {"device_serial": dev["serial_number"], "name": "UPFM全量复测-代码更新后", "item_ids": item_ids, "custom_parameters": {}}
    r = requests.post(f"{BASE}/tasks", headers=H, json=payload, timeout=30)
    print("create:", r.status_code, r.text[:300])
    task_id = r.json()["data"]["id"]

    # 4. 轮询
    t0 = time.time()
    while time.time() - t0 < 1500:
        t = requests.get(f"{BASE}/tasks/{task_id}", headers=H, timeout=15).json()["data"]
        if t["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(10)
    print("final status:", t["status"], "result:", t.get("result"), "elapsed:", round(time.time() - t0))

    # 5. 记录
    recs = requests.get(f"{BASE}/tasks/{task_id}", headers=H, timeout=15).json()["data"].get("records", [])
    summary = []
    for rec in sorted(recs, key=lambda x: x.get("id", 0)):
        summary.append({
            "item": rec.get("item_name") or rec.get("item_id"),
            "status": rec["status"],
            "fail_reason": (rec.get("fail_reason") or "")[:120],
            "output_tail": (rec.get("output") or "")[-200:],
        })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"task_id": task_id, "device": dev["serial_number"], "status": t["status"], "records": summary}, f, ensure_ascii=False, indent=2)
    from collections import Counter
    print("status dist:", dict(Counter(s["status"] for s in summary)))
    for s in summary:
        print(f"  [{s['status']:7}] {s['item']}  {s['fail_reason'][:80]}")
    print("task_id:", task_id)

if __name__ == "__main__":
    main()
