# -*- coding: utf-8 -*-
"""契约 v1.1 §6.1 销项复现（F1~F4 修复后必须抛错/失败）：manifest-failopen-repro-v2。

对照：docs/verification/reviews/evidence/v1-refinal-review-20261112/manifest-failopen-repro.py
（原审计文件未动，其 4 项 fail-open 在 v1.1 实现后全部转为 CLOSED）。

F1 host/shared 声明缺 sha256 → ToolManifestError（A1）
F2 tools:{} 四段全空且目录含 host 文件 → declaration_gaps + 启动失败（A2）
F3 {host_tool_dir} 引用未声明 → 加载抛错，无 undeclared_reference 降级（A3）
F4 非法路径（../ 越界）→ 加载抛错且信息含原始值（A4）
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
    status = "CLOSED" if cond else "OPEN"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _mk(root: Path, module: str, manifest_body: str, host_src: str = ""):
    mdir = root / module
    (mdir / "host").mkdir(parents=True, exist_ok=True)
    if host_src:
        (mdir / "host" / "run.py").write_text(host_src, encoding="utf-8")
    (mdir / "manifest.yaml").write_text(manifest_body, encoding="utf-8")
    return mdir / "manifest.yaml"


def _expect_raise(fn, needle: str) -> tuple:
    try:
        result = fn()
        return (False, f"未抛出（返回 ok={getattr(result, 'ok', 'n/a')}）")
    except ToolManifestError as exc:
        message = str(exc)
        ok = needle in message
        return (ok, f"raised ok={ok}（needle={needle!r} in message={ok}）")


# F1 → CLOSED：host 声明缺 sha256 现在必须抛 ToolManifestError（A1）
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    manifest = _mk(root, "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n    - path: demo/host/run.py\n",
        host_src="print('tampered')\n")
    ok, detail = _expect_raise(lambda: validate_tools(root), "demo/host/run.py")
    check("F1 CLOSED host 缺 sha256 → ToolManifestError（指明条目）", ok, detail)
    ok2, detail2 = _expect_raise(lambda: assert_required_tools(root), str(manifest))
    check("F1 CLOSED 启动门禁抛错并指明 manifest 路径", ok2, detail2)

# F2 → CLOSED：tools:{} 空对象 + 目录含 host 文件 → declaration_gaps 非空且启动失败（A2）
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    _mk(root, "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools: {}\n",
        host_src="print('hi')\n")
    r = validate_tools(root)
    gaps = r["declaration_gaps"]
    check("F2 CLOSED 空 tools:{} → declaration_gaps 非空",
          len(gaps) == 1 and r["ok"] is False, f"gaps={len(gaps)}")
    ok2, detail2 = _expect_raise(lambda: assert_required_tools(root), "demo")
    check("F2 CLOSED 启动门禁抛错", ok2, detail2)

# F3 → CLOSED：{host_tool_dir} 引用未声明 → 加载抛错，undeclared_reference 降级已废除（A3）
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    (root / "common").mkdir(parents=True)
    (root / "common" / "adb_runner.py").write_text("X=1\n", encoding="utf-8")
    (root / "run.py").write_text(
        "import common.adb_runner\nprint(common.adb_runner.X)\n", encoding="utf-8")
    _mk(root, "demo",
        "module:\n  name: demo\n"
        "items:\n  - name: t1\n    exec_type: host_exec\n"
        "    exec_command: python {host_tool_dir}/run.py\n"
        "tools: {}\n")
    ok, detail = _expect_raise(lambda: validate_tools(root), "run.py")
    check("F3 CLOSED {host_tool_dir} 未声明引用 → 加载抛错", ok, detail)
    ok2, detail2 = _expect_raise(lambda: assert_required_tools(root), "{host_tool_dir}")
    check("F3 CLOSED 启动门禁抛错（含引用路径）", ok2, detail2)
    # 降级条目废除：若未抛错则 requirements 里不应有 undeclared_reference；
    # 抛错本身即证明不再产生降级条目（在 v1.1 下无任何无 sha256 的旁路条目）
    check("F3 CLOSED undeclared_reference 降级条目已废除", ok is True and ok2 is True,
          "加载即抛错，不存在可返回的降级条目")

# F4 → CLOSED：非法路径（../ 越界）→ 加载抛错且信息含原始值（A4）
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    _mk(root, "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n    - path: ../../etc/passwd\n")
    ok, detail = _expect_raise(lambda: validate_tools(root), "../../etc/passwd")
    check("F4 CLOSED 非法路径（../）→ 抛错且含原始声明值", ok, detail)
    ok2, detail2 = _expect_raise(lambda: assert_required_tools(root), "../../etc/passwd")
    check("F4 CLOSED 启动门禁抛错（含原始声明值）", ok2, detail2)

print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} OPEN -> {FAILURES}")
    sys.exit(1)
print("RESULT: ALL CLOSED (F1~F4 fail-open 已全部修复：契约 v1.1 §6.1 A1~A4)")
