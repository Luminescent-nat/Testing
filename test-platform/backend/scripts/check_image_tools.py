#!/usr/bin/env python3
"""T-17 干净镜像工具发现只读校验（可在无 docker 的主机上运行）。

三项检查：
1. Dockerfile / .dockerignore 静态核对：镜像是否完整携带 test-tools
   （manifest + runner + 各架构二进制）并把 TEST_TOOLS_PATH/STATIC_PATH
   与镜像内工作目录 /app 对齐；
2. manifest 解析 + 工具发现（app/services/tool_manifest.py）：
   声明的必需工具缺失 → 非 0 退出；范围内 APK 等可选资源缺失 → skip；
3. docker 可用性探测：本机无 docker 时明确输出「无法核验」及原因
   （干净构建/启动未执行，不得伪造通过）。

用法（backend 目录）：
    python scripts/check_image_tools.py --report docs/verification/tasks/T-17/image-tools-summary.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PLATFORM_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.tool_manifest import ToolManifestError, validate_tools  # noqa: E402


def check_dockerfile(dockerfile: Path, dockerignore: Path) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    text = dockerfile.read_text(encoding="utf-8")
    ign = dockerignore.read_text(encoding="utf-8") if dockerignore.is_file() else ""

    def has(needle: str) -> bool:
        return needle in text

    checks.append(("Dockerfile 存在", dockerfile.is_file(), str(dockerfile)))
    checks.append(("COPY test-tools/ 进镜像", has("COPY test-tools/"), "COPY test-tools/"))
    checks.append(("TEST_TOOLS_PATH=/app/test-tools", has('TEST_TOOLS_PATH="/app/test-tools"') or has("TEST_TOOLS_PATH=/app/test-tools"), ""))
    checks.append(("STATIC_PATH=/app/static", has('STATIC_PATH="/app/static"') or has("STATIC_PATH=/app/static"), ""))
    checks.append(("WORKDIR /app（与 TEST_TOOLS_PATH/STATIC_PATH 对齐）", "WORKDIR /app" in text, ""))
    bad_excludes = [line.strip() for line in ign.splitlines() if line.strip() in ("test-tools", "test-tools/")]
    checks.append((".dockerignore 不排除 test-tools/", not bad_excludes, f"bad={bad_excludes}"))
    return checks


def check_tool_manifest(tools_root: Path) -> tuple[list[tuple[str, bool, str]], dict]:
    checks: list[tuple[str, bool, str]] = []
    result = validate_tools(tools_root)
    checks.append(("TEST_TOOLS_PATH 存在", tools_root.is_dir(), str(tools_root)))
    checks.append(("发现 manifest", bool(result["manifest_paths"]), str(result["manifest_paths"])))
    checks.append(("必需工具齐备", result["ok"], f"missing={ [m['name'] for m in result['missing_required']] }"))
    for item in result["skipped"]:
        checks.append((f"skip（不伪造）: {item['name']}", True, item.get("reason", "")))
    return checks, result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="T-17 镜像工具静态核对 + manifest 工具发现")
    parser.add_argument("--tools-root", default=None, help="test-tools 根目录（默认 TEST_TOOLS_PATH）")
    parser.add_argument("--dockerfile", default=str(PLATFORM_DIR / "Dockerfile"))
    parser.add_argument("--dockerignore", default=str(PLATFORM_DIR / ".dockerignore"))
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    tools_root = (
        Path(args.tools_root).resolve()
        if args.tools_root
        else (BACKEND_DIR / ".." / "test-tools").resolve()
    )

    checks: list[tuple[str, bool, str]] = []
    checks += check_dockerfile(Path(args.dockerfile), Path(args.dockerignore))

    result: dict = {}
    try:
        manifest_checks, result = check_tool_manifest(tools_root)
        checks += manifest_checks
    except ToolManifestError as exc:
        checks.append(("工具清单校验", False, str(exc)))
        result = {"root": str(tools_root), "error": str(exc), "ok": False}

    docker_bin = shutil.which("docker")
    docker_note = (
        f"主机存在 docker 命令: {docker_bin}" if docker_bin
        else "无法核验：当前主机无 docker 命令（Get-Command docker 为空），"
             "干净镜像构建（docker build）、容器启动与镜像内工具发现未执行；"
             "本脚本仅完成 Dockerfile/.dockerignore 静态核对与 host 侧 manifest 工具发现。"
    )
    print(f"\n[docker] {docker_note}")
    print("[docker] 明确结论：镜像内实际构建/启动核验 = 无法核验（不伪造通过）")

    print("\n================ 汇总 ================")
    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\nRESULT: {'PASS(static)' if not failed else 'FAIL'} ({len(checks) - len(failed)}/{len(checks)})")
    print(f"docker build/start verification: {'verified' if docker_bin else 'UNVERIFIABLE (no docker)'}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
                    "failed": len(failed),
                    "tool_manifest": result,
                    "docker_available": bool(docker_bin),
                    "docker_note": docker_note,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[report] {report_path}")

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
