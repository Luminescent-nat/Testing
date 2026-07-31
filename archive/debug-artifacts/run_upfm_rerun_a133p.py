# -*- coding: utf-8 -*-
"""UPFM 全量复跑（板型画像改造后）：创建任务(27项) → 轮询 → 输出逐项状态。

输出含 RESULT: SKIP 的记录在报告中归类为 skip（平台断言判定无 skip 状态，
SKIP 输出落库为 error，此处按输出内容重分类）。
"""
import json
import time
from collections import Counter

import requests

BASE = "http://localhost:8000/api/v1"
USER = {"username": "e2e-admin", "password": "e2e-admin-pass"}
SERIAL = "9c000c8a230487920dd"
OUT = r"D:\MCTEST\archive\debug-artifacts\upfm_rerun_a133p_boards.json"


def main():
    tok = requests.post(f"{BASE}/auth/login", json=USER, timeout=15).json()["data"]["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    items = requests.get(f"{BASE}/modules/7", headers=H, timeout=15).json()["data"]["items"]
    item_ids = [i["id"] for i in items]
    print("items:", len(item_ids))

    payload = {"device_serial": SERIAL, "name": "UPFM全量复测-板型画像",
               "item_ids": item_ids, "custom_parameters": {}}
    r = requests.post(f"{BASE}/tasks", headers=H, json=payload, timeout=30)
    print("create:", r.status_code, r.text[:300])
    task_id = r.json()["data"]["id"]

    t0 = time.time()
    while time.time() - t0 < 1800:
        t = requests.get(f"{BASE}/tasks/{task_id}", headers=H, timeout=15).json()["data"]
        if t["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(10)
    print("final status:", t["status"], "elapsed:", round(time.time() - t0))

    recs = requests.get(f"{BASE}/tasks/{task_id}/records", headers=H, timeout=15).json()["data"].get("items", [])
    summary = []
    for rec in sorted(recs, key=lambda x: x.get("id", 0)):
        status = rec["status"]
        output = rec.get("output") or ""
        if status == "error" and "RESULT: SKIP" in output:
            status = "skip(runner)"
        summary.append({
            "item": rec.get("item_name") or rec.get("item_id"),
            "status": status,
            "fail_reason": (rec.get("fail_reason") or "")[:150],
            "output_tail": output[-300:],
        })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"task_id": task_id, "device": SERIAL, "status": t["status"],
                   "records": summary}, f, ensure_ascii=False, indent=2)
    print("status dist:", dict(Counter(s["status"] for s in summary)))
    for s in summary:
        print(f"  [{s['status']:12}] {s['item']}  {s['fail_reason'][:80]}")
    print("task_id:", task_id)


if __name__ == "__main__":
    main()
