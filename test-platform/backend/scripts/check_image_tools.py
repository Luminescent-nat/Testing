#!/usr/bin/env python3
"""T-17/V1-08 干净镜像工具核验（真实性优先，禁止假 verified）。

三层：
1. Dockerfile / .dockerignore 静态核对（镜像是否完整携带 test-tools 并与 /app 对齐）；
2. manifest 显式工具清单只读校验（存在性 + SHA-256 + 依赖闭包，app/services/tool_manifest.py）；
3. **真实 Docker 运行时核验**（仅当 docker 可用时）：`docker build --no-cache` →
   `docker compose up -d` → `/health` 200 → 容器内工具发现 → `docker compose down`。
   只有以上全部真实成功才输出 `verified`。仅发现 docker 命令、或未实际构建，一律
   `UNVERIFIABLE` 并退出非零，绝不打印 verified。

退出码：0 = 静态+清单通过且 docker 运行时 verified；1 = 静态/清单失败或 docker 运行时失败；
        2 = docker 不可用（无法核验）。

用法（backend 目录）：
    python scripts/check_image_tools.py --report docs/verification/tasks/T-17/image-tools-summary.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PLATFORM_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.tool_manifest import ToolManifestError, validate_tools  # noqa: E402

CONTAINER_DISCOVERY_CODE = (
    "from app.services.tool_manifest import validate_tools;"
    "r = validate_tools();"
    "print('TOOL_DISCOVERY count=%d missing=%d hash=%d closure=%d gaps=%d ok=%s' % ("
    "len(r['requirements']), len(r['missing_required']), len(r['hash_mismatch']),"
    "len(r['closure_violations']), len(r['declaration_gaps']), r['ok']));"
    "raise SystemExit(0 if r['ok'] else 3)"
)


def check_dockerfile(dockerfile: Path, dockerignore: Path) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    text = dockerfile.read_text(encoding="utf-8") if dockerfile.is_file() else ""
    ign = dockerignore.read_text(encoding="utf-8") if dockerignore.is_file() else ""
    checks.append(("Dockerfile 存在", dockerfile.is_file(), str(dockerfile)))
    checks.append(("COPY test-tools/ 进镜像", "COPY test-tools/" in text, "COPY test-tools/"))
    checks.append(("TEST_TOOLS_PATH=/app/test-tools",
                   'TEST_TOOLS_PATH="/app/test-tools"' in text or "TEST_TOOLS_PATH=/app/test-tools" in text, ""))
    checks.append(("STATIC_PATH=/app/static",
                   'STATIC_PATH="/app/static"' in text or "STATIC_PATH=/app/static" in text, ""))
    checks.append(("WORKDIR /app（与 TEST_TOOLS_PATH/STATIC_PATH 对齐）", "WORKDIR /app" in text, ""))
    bad_excludes = [line.strip() for line in ign.splitlines() if line.strip() in ("test-tools", "test-tools/")]
    checks.append((".dockerignore 不排除 test-tools/", not bad_excludes, f"bad={bad_excludes}"))
    return checks


def check_compose_image_alignment(compose_path: Path, tag: str) -> list[tuple[str, bool, str]]:
    """task-D：docker-compose.yml app 服务的 image 必须与 docker build --tag 一致。

    RR-V1-REFINAL §3.5 指出的「验证分裂」：compose 无 image: 时 compose up 用项目名
    自行命名镜像，与 docker build --tag 不是同一个镜像。
    """
    checks: list[tuple[str, bool, str]] = []
    text = compose_path.read_text(encoding="utf-8") if compose_path.is_file() else ""
    checks.append(("docker-compose.yml 存在", compose_path.is_file(), str(compose_path)))
    import re as _re
    image_lines = _re.findall(r"(?m)^\s*-\s*image:\s*(\S+)\s*$", text) + \
        _re.findall(r"(?m)^\s*image:\s*(\S+)\s*$", text)
    aligned = tag in image_lines
    checks.append((f"compose app image 与 --tag 一致（{tag}）", aligned,
                   f"image lines={sorted(set(image_lines))}"))
    return checks


def check_tool_manifest(tools_root: Path) -> tuple[list[tuple[str, bool, str]], dict]:
    checks: list[tuple[str, bool, str]] = []
    result = validate_tools(tools_root)
    checks.append(("TEST_TOOLS_PATH 存在", tools_root.is_dir(), str(tools_root)))
    checks.append(("发现 manifest", bool(result["manifest_paths"]), str(result["manifest_paths"])))
    checks.append(("显式声明无缺口", result["declaration_gaps"] == [],
                   str([i["name"] for i in result["declaration_gaps"]])))
    checks.append(("必需工具齐备", result["missing_required"] == [],
                   f"missing={[m['name'] for m in result['missing_required']]}"))
    checks.append(("SHA-256 全部匹配", result["hash_mismatch"] == [],
                   str([h["name"] for h in result["hash_mismatch"]])))
    checks.append(("共享依赖闭包完整", result["closure_violations"] == [],
                   str([c["name"] for c in result["closure_violations"]])))
    for item in result["skipped"]:
        checks.append((f"skip（不伪造）: {item['name']}", True, item.get("reason", "")))
    return checks, result


def _run(cmd: list[str], cwd: Path, timeout: int = 900) -> tuple[int, str, str]:
    print(f"[docker] $ {' '.join(cmd)}  (cwd={cwd})")
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError as exc:
        return 127, "", f"FileNotFoundError: {exc}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    if proc.stdout.strip():
        print(f"[docker] stdout:\n{proc.stdout}")
    if proc.stderr.strip():
        print(f"[docker] stderr:\n{proc.stderr}")
    print(f"[docker] exit={proc.returncode}")
    return proc.returncode, proc.stdout, proc.stderr


def verify_docker_runtime(tag: str, health_timeout: int) -> dict:
    """真实执行 docker build + compose up + /health + 容器内工具发现。仅全成功 verified。"""
    steps: list[dict] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        steps.append({"step": name, "ok": ok, "detail": detail})
        print(f"[docker] [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

    rc, _, err = _run(["docker", "build", "--no-cache", "-t", tag, "."], PLATFORM_DIR, timeout=1800)
    step("docker build --no-cache", rc == 0, f"rc={rc}")
    if rc != 0:
        return {"status": "FAILED", "verified": False, "steps": steps}

    rc, out, err = _run(["docker", "compose", "up", "-d"], PLATFORM_DIR, timeout=600)
    step("docker compose up -d", rc == 0, f"rc={rc}")
    try:
        if rc != 0:
            return {"status": "FAILED", "verified": False, "steps": steps}

        healthy = False
        deadline = time.time() + health_timeout
        last = ""
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as resp:
                    body = resp.read().decode("utf-8", "replace")
                    healthy = resp.status == 200 and '"healthy"' in body
                    last = f"{resp.status} {body}"
                    if healthy:
                        break
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
                last = repr(exc)
            time.sleep(2)
        step("host /health 200 healthy", healthy, last)

        rc, out, err = _run(
            ["docker", "compose", "exec", "-T", "app", "python", "-c", CONTAINER_DISCOVERY_CODE],
            PLATFORM_DIR, timeout=300,
        )
        discovery_ok = rc == 0 and "ok=True" in (out or "")
        step("容器内工具发现 validate_tools ok", discovery_ok, (out or err).strip()[:300])

        verified = healthy and discovery_ok and all(s["ok"] for s in steps)
        return {"status": "VERIFIED" if verified else "FAILED", "verified": verified, "steps": steps}
    finally:
        rc, _, _ = _run(["docker", "compose", "down"], PLATFORM_DIR, timeout=300)
        step("docker compose down（清理）", rc == 0, f"rc={rc}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="T-17/V1-08 干净镜像工具核验（真实性）")
    parser.add_argument("--tools-root", default=None)
    parser.add_argument("--dockerfile", default=str(PLATFORM_DIR / "Dockerfile"))
    parser.add_argument("--dockerignore", default=str(PLATFORM_DIR / ".dockerignore"))
    parser.add_argument("--tag", default="test-platform:v1-08-check")
    parser.add_argument("--health-timeout", type=int, default=120)
    parser.add_argument("--skip-docker", action="store_true", help="跳过运行时核验（仅静态+清单）")
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    tools_root = (
        Path(args.tools_root).resolve() if args.tools_root
        else (BACKEND_DIR.parent / "test-tools").resolve()
    )

    checks = check_dockerfile(Path(args.dockerfile), Path(args.dockerignore))
    checks += check_compose_image_alignment(
        PLATFORM_DIR / "docker-compose.yml", args.tag
    )
    manifest_result: dict = {}
    try:
        manifest_checks, manifest_result = check_tool_manifest(tools_root)
        checks += manifest_checks
    except ToolManifestError as exc:
        checks.append(("工具清单校验", False, str(exc)))
        manifest_result = {"ok": False, "error": str(exc)}

    static_failed = [c for c in checks if not c[1]]

    docker_bin = shutil.which("docker")
    runtime: dict
    exit_code: int
    if args.skip_docker or not docker_bin:
        reason = (
            "显式 --skip-docker"
            if args.skip_docker
            else "当前主机无 docker 命令（Get-Command docker 为空），docker build / compose up / /health / "
                 "容器内工具发现均未执行"
        )
        runtime = {"status": "UNVERIFIABLE", "verified": False, "reason": reason}
        exit_code = 2 if not static_failed else 1
        print(f"\n[docker] 状态=UNVERIFIABLE：{reason}")
        print("[docker] 明确结论：镜像层核验 = 无法核验（不伪造 verified）")
    else:
        runtime = verify_docker_runtime(args.tag, args.health_timeout)
        if runtime["verified"] and not static_failed:
            exit_code = 0
            print("\n[docker] 状态=VERIFIED（真实 build + compose up + /health + 容器内工具发现全部成功）")
        else:
            exit_code = 1
            print(f"\n[docker] 状态={runtime['status']}（未全部成功，禁止写 verified）")

    print("\n================ 汇总 ================")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    overall = (
        "VERIFIED" if exit_code == 0
        else "UNVERIFIABLE" if runtime["status"] == "UNVERIFIABLE"
        else "FAIL"
    )
    print(f"\nRESULT: {overall} (static {len(checks) - len(static_failed)}/{len(checks)}, runtime={runtime['status']})")
    print(f"docker runtime verification: {runtime['status']}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
                    "static_failed": len(static_failed),
                    "tool_manifest": manifest_result,
                    "docker_available": bool(docker_bin),
                    "runtime": runtime,
                    "overall": overall,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[report] {report_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
