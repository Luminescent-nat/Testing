#!/usr/bin/env python3
"""V1-08 定向复现（修正夹具版）：manifest 显式声明设备二进制后，删除文件仍为必需且启动失败。

说明：审计原始夹具（targeted-defect-repro.py:151-164）的 manifest **没有 tools 声明**，
按 V1-08 新契约它本身不是合法场景（未声明文件不应成为必需项，且此类 manifest 会被判
declaration_gaps 致命）。本文件保留同一定向语义，仅把必需设备二进制**显式声明**进
manifest，证明「删除已声明文件→条目仍在→启动校验失败」。原夹具运行结果见
../v1-08-audit-repro-rerun-20261112.log（现于第 161 行失败：未声明文件不应被 glob 生成必需项）。
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"D:\MCTEST\test-platform\backend")))
from app.services.tool_manifest import (  # noqa: E402
    ToolManifestError,
    assert_required_tools,
    discover_requirements,
)


def main() -> int:
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="v108_repro_"))
    module = root / "demo"
    binary = module / "binaries" / "arm64-v8a" / "tool"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"audit")
    sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    (module / "manifest.yaml").write_text(
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  device:\n"
        "    - path: demo/binaries/arm64-v8a/tool\n"
        "      abi: arm64-v8a\n"
        "      version: '1.0'\n"
        f"      sha256: \"{sha}\"\n",
        encoding="utf-8",
    )

    before, _ = discover_requirements(root)
    print(f"[before] demo/binaries/arm64-v8a/tool in requirements = {'demo/binaries/arm64-v8a/tool' in before}")
    binary.unlink()
    after, _ = discover_requirements(root)
    print(f"[after ] demo/binaries/arm64-v8a/tool in requirements = {'demo/binaries/arm64-v8a/tool' in after}")
    try:
        assert_required_tools(root)
        startup_blocked = False
        detail = "未抛出异常（错误）"
    except ToolManifestError as exc:
        startup_blocked = "demo/binaries/arm64-v8a/tool" in str(exc)
        detail = str(exc).splitlines()[0]

    ok = ("demo/binaries/arm64-v8a/tool" in before
          and "demo/binaries/arm64-v8a/tool" in after
          and startup_blocked)
    print(f"[startup] blocked={startup_blocked} ({detail})")
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
