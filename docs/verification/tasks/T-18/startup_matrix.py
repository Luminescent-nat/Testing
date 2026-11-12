#!/usr/bin/env python3
"""T-18 真实启动矩阵：弱/占位/短密钥拒绝启动，合法密钥 /health 成功。

每个用例在独立临时工作目录（cwd）+ 独立 SQLite/存储/日志中运行，
不触碰 backend/test_platform.db 或任何真实数据；通过环境变量覆盖
DATABASE_URL / STORAGE_PATH / LOGS_PATH 等，TEST_TOOLS_PATH 指向真实仓库
test-tools（只读工具发现）。弱密钥期望 uvicorn 启动失败（非 0 退出码），
合法密钥期望 /health 返回 200 {"status":"healthy"}。

注：合法密钥用例使用「已初始化临时库（建表 + 预置 1 个用户）」，
以隔离 SECRET_KEY 校验；另设一个 fresh 空库观察用例，用于如实记录
T-02 `PRAGMA foreign_keys=ON` 导致的 seed_data 干净库 FK 问题（不作为本任务门禁）。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND = REPO_ROOT / "test-platform" / "backend"
TEST_TOOLS = REPO_ROOT / "test-platform" / "test-tools"

LEGAL_KEY = "x9F2k7Qp4Lm8Nv3Bw6Yz1Rt5Hj0Cd4Es7Ag2Ui5Oq8PnT3Wv"

WEAK_CASES = [
    ("empty", ""),
    ("short", "short"),
    ("placeholder-secret", "secret"),
    ("placeholder-change-me", "change-me"),
    ("placeholder-your-secret-key", "your-secret-key"),
    ("placeholder-compose-example", "please-change-me-in-production"),
    ("placeholder-long-variant", "please-change-me-in-production-but-much-longer-than-32-chars"),
    ("single-char-repeat", "a" * 40),
]


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def build_env(workdir: Path, secret: str) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["SECRET_KEY"] = secret
    env["DATABASE_URL"] = "sqlite+aiosqlite:///" + (workdir / "matrix.db").as_posix()
    env["STORAGE_PATH"] = str(workdir / "storage")
    env["TOOLS_PATH"] = str(workdir / "storage" / "tools")
    env["REPORTS_PATH"] = str(workdir / "storage" / "reports")
    env["LOGS_PATH"] = str(workdir / "storage" / "logs")
    env["STATIC_PATH"] = str(workdir / "no-static")
    env["TEST_TOOLS_PATH"] = str(TEST_TOOLS)
    env["ADB_TIMEOUT"] = "5"
    return env


def init_temp_db_with_user(workdir: Path) -> None:
    """建表并预置 1 个用户（模拟已完成首次注册的正常部署），隔离 SECRET_KEY 校验。"""
    db_path = (workdir / "matrix.db").as_posix()
    code = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from sqlalchemy import create_engine, text\n"
        "from app.models import Base\n"
        "eng = create_engine('sqlite:///%s')\n"
        "Base.metadata.create_all(eng)\n"
        "with eng.begin() as c:\n"
        "    c.execute(text(\"INSERT INTO users (username, password_hash, role, status) "
        "VALUES ('matrix-admin','x','admin','active')\"))\n"
        "eng.dispose()\n"
        "print('DB_INIT_OK')\n" % (BACKEND, db_path)
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=str(workdir), env=build_env(workdir, LEGAL_KEY),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(f"[init] DB+user init exit={proc.returncode} out={proc.stdout.strip()!r} err={proc.stderr.strip()[:300]!r}")


def uvicorn_cmd(port: int) -> list[str]:
    return [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", str(port), "--log-level", "info",
    ]


def run_weak(name: str, secret: str, workdir: Path) -> dict:
    port = free_port()
    print(f"\n[{name}] $ python -m uvicorn app.main:app --port {port} (SECRET_KEY 长度={len(secret)})")
    started = time.time()
    proc = subprocess.run(
        uvicorn_cmd(port), cwd=str(workdir), env=build_env(workdir, secret),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
    )
    elapsed = time.time() - started
    combined = proc.stdout + proc.stderr
    print(f"[{name}] exit={proc.returncode} elapsed={elapsed:.1f}s")
    print(f"[{name}] stdout:\n{proc.stdout}")
    print(f"[{name}] stderr:\n{proc.stderr}")
    # 只对可区分的长值检查回显（短值如 "secret" 会与提示里的 secrets.token_urlsafe 相撞）
    leaks_value = len(secret) >= 12 and secret in combined
    result = {
        "case": name, "secret_length": len(secret), "port": port,
        "exitcode": proc.returncode, "elapsed_s": round(elapsed, 2),
        "startup_rejected": proc.returncode != 0,
        "mentions_config_item": "SECRET_KEY" in combined,
        "leaks_secret_value": leaks_value,
        "stdout": proc.stdout, "stderr": proc.stderr,
    }
    print(f"[{name}] rejected={result['startup_rejected']} mentions_config={result['mentions_config_item']} leaks_value={leaks_value}")
    return result


def run_startup_and_probe(label: str, workdir: Path, secret: str, expect_healthy: bool) -> dict:
    port = free_port()
    print(f"\n[{label}] $ python -m uvicorn app.main:app --port {port} (SECRET_KEY 长度={len(secret)})")
    proc = subprocess.Popen(
        uvicorn_cmd(port), cwd=str(workdir), env=build_env(workdir, secret),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    status, body = None, None
    if expect_healthy:
        deadline = time.time() + 45
        while time.time() < deadline and proc.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
                    status, body = resp.status, resp.read().decode("utf-8")
                    break
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                time.sleep(0.5)
    else:
        deadline = time.time() + 45
        while time.time() < deadline and proc.poll() is None:
            time.sleep(0.3)
    healthy = status == 200 and '"healthy"' in (body or "")
    print(f"[{label}] /health status={status} body={body!r} healthy={healthy}")
    if proc.poll() is None:
        proc.terminate()
    try:
        out, _ = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=10)
    code = proc.returncode
    print(f"[{label}] exit={code}")
    print(f"[{label}] stdout+stderr:\n{out}")
    return {
        "case": label, "secret_length": len(secret), "port": port,
        "health_status": status, "health_body": body, "healthy": healthy,
        "expect_healthy": expect_healthy, "exitcode": code, "stdout": out,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    workroot = Path(tempfile.mkdtemp(prefix="t18_startup_")).resolve()
    print(f"[env] isolated workroot={workroot}")
    print(f"[env] backend={BACKEND}")
    print(f"[env] test_tools={TEST_TOOLS}")
    print(f"[env] python={sys.executable}")

    results = []
    for idx, (name, secret) in enumerate(WEAK_CASES):
        workdir = workroot / f"weak_{idx}"
        workdir.mkdir(parents=True)
        results.append(run_weak(name, secret, workdir))

    legal_dir = workroot / "legal"
    legal_dir.mkdir(parents=True)
    init_temp_db_with_user(legal_dir)
    legal = run_startup_and_probe("legal", legal_dir, LEGAL_KEY, expect_healthy=True)

    # fresh 空库 + 合法密钥：seed_data 修复（created_by=None）后必须能成功启动
    fresh_dir = workroot / "fresh_empty_db"
    fresh_dir.mkdir(parents=True)
    fresh = run_startup_and_probe("fresh-empty-db", fresh_dir, LEGAL_KEY, expect_healthy=True)
    fresh_ok = fresh["healthy"]

    weak_ok = all(r["startup_rejected"] and r["mentions_config_item"] for r in results)
    no_leak = all(not r["leaks_secret_value"] for r in results)
    legal_ok = legal["healthy"]
    print("\n================ 汇总 ================")
    for r in results:
        print(f"  [{'PASS' if r['startup_rejected'] else 'FAIL'}] {r['case']}: exit={r['exitcode']} rejected={r['startup_rejected']}")
    print(f"  [{'PASS' if legal_ok else 'FAIL'}] legal(已初始化临时库): /health={legal['health_status']} body={legal['health_body']}")
    print(f"  [{'PASS' if fresh_ok else 'FAIL'}] fresh 空库(合法密钥): /health={fresh['health_status']} body={fresh['health_body']}")
    print(f"weak_all_rejected={weak_ok} no_secret_value_leak={no_leak} legal_healthy={legal_ok} fresh_empty_db_healthy={fresh_ok}")
    ok = weak_ok and no_leak and legal_ok and fresh_ok
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")

    report = {
        "workroot": str(workroot), "backend": str(BACKEND), "test_tools": str(TEST_TOOLS),
        "weak_all_rejected": weak_ok, "no_secret_value_leak": no_leak, "legal_healthy": legal_ok,
        "fresh_empty_db_healthy": fresh_ok,
        "result": "PASS" if ok else "FAIL",
        "fresh_empty_db": {
            "note": "T-02 PRAGMA foreign_keys=ON 曾因 seed_data.py user_id=1（无用户时）使干净库首次启动 FK 失败；"
                    "seed_data.py 改为 created_by=None 后本用例必须通过（干净空库首次启动成功）",
        },
        "cases": results, "legal": legal, "fresh": fresh,
    }
    (REPO_ROOT / "docs" / "verification" / "tasks" / "T-18" / "startup-matrix.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
