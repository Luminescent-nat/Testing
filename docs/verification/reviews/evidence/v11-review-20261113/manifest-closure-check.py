# -*- coding: utf-8 -*-
"""契约 v1.1 实施独立复核：manifest fail-open 销项验证（HEAD 721db2b）。

判定口径与审计期相反：A1~A5 已实施的场景下，每个构造都必须抛 ToolManifestError
或记 declaration_gaps，全部按预期失败/报错 = 销项成立（EXIT=0）。
若任一构造仍静默通过 = 该洞未闭合（EXIT=1）。
"""
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent
for _ in range(10):
    cand = _BACKEND / "test-platform" / "backend"
    if (cand / "app" / "services" / "tool_manifest.py").is_file():
        _BACKEND = cand
        break
    _BACKEND = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
from app.services.tool_manifest import (  # noqa: E402
    ToolManifestError,
    assert_required_tools,
    validate_tools,
)

FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAILED"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _mk(root: Path, module: str, manifest_body: str, host_src: str = ""):
    mdir = root / module
    (mdir / "host").mkdir(parents=True, exist_ok=True)
    if host_src:
        (mdir / "host" / "run.py").write_text(host_src, encoding="utf-8")
    (mdir / "manifest.yaml").write_text(manifest_body, encoding="utf-8")


def expect_error(name, fn):
    try:
        fn()
    except ToolManifestError as exc:
        check(name, True, f"抛错: {str(exc)[:80]}")
        return
    check(name, False, "未抛错（fail-open 仍存在）")


# V1（原 F1）：host 缺 sha256 → 必须抛错
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    _mk(root, "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n    - path: demo/host/run.py\n",
        host_src="print('tampered')\n")
    expect_error("V1 host 缺 sha256 硬失败（原 F1）",
                 lambda: validate_tools(root))

# V2（原 F2）：tools: {} + 目录含 host → declaration_gaps 且启动失败
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    _mk(root, "demo", "module:\n  name: demo\nitems: []\ntools: {}\n",
        host_src="print('hi')\n")
    r = validate_tools(root)
    check("V2 空 tools:{} + host 目录 → declaration_gaps（原 F2）",
          bool(r["declaration_gaps"]), f"gaps={len(r['declaration_gaps'])}")
    expect_error("V2b 空 tools:{} 启动失败",
                 lambda: assert_required_tools(root))

# V3（原 F3）：{host_tool_dir} 未声明引用 → 加载硬失败，无降级条目
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    root.mkdir(parents=True)
    (root / "run.py").write_text("print(1)", encoding="utf-8")
    mdir = root / "demo" / "host"
    mdir.mkdir(parents=True)
    (root / "demo" / "manifest.yaml").write_text(
        "module:\n  name: demo\n"
        "items:\n  - name: t1\n    exec_type: host_exec\n"
        "    exec_command: python {host_tool_dir}/run.py\n"
        "tools:\n  host: []\n  shared: []\n  device: []\n", encoding="utf-8")
    expect_error("V3 未声明 {host_tool_dir} 引用硬失败（原 F3）",
                 lambda: validate_tools(root))

# V4（原 F4）：非法路径 ../ → 抛错且含原始值
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    _mk(root, "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n"
        "    - path: ../../etc/passwd\n"
        "      sha256: \"ab\"\n")
    try:
        validate_tools(root)
        check("V4 非法路径抛错（原 F4）", False, "未抛错")
    except ToolManifestError as exc:
        check("V4 非法路径抛错（原 F4）",
              "../../etc/passwd" in str(exc), f"含原始值: {'../../etc/passwd' in str(exc)}")

# V5（A5）：空 tools 根 → assert_required_tools 抛错
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    root.mkdir(parents=True)
    expect_error("V5 空工具根拒绝启动（A5）",
                 lambda: assert_required_tools(root))

# V6：真实仓库回归 —— 现行合法配置必须全部通过（零迁移成本验证）
REAL = _BACKEND.parent / "test-tools"
r = validate_tools(REAL)
check("V6 真实仓库 manifest 校验通过（零迁移）",
      r["ok"] is True,
      f"missing={len(r['missing_required'])} hash={len(r['hash_mismatch'])} "
      f"closure={len(r['closure_violations'])} gaps={len(r['declaration_gaps'])}")

print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED -> {FAILURES}")
    sys.exit(1)
print("RESULT: ALL CLOSED（A1~A5 销项成立）")
