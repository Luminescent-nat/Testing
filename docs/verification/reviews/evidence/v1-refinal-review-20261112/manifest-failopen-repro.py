# -*- coding: utf-8 -*-
"""重新复核：tool_manifest fail-open 动态复现 v2（HEAD a4a32f2）。

复现项（对应 RR-V1-READINESS 批次 G P0，HEAD a4a32f2 核验）：
F1 host 声明缺 sha256 → 哈希校验被跳过，文件存在即 ok（篡改可绕过）
F2 manifest 写 tools: {}（空对象）→ declaration_gaps 不触发（绕过 v2 R6b 语义）
F3 {host_tool_dir} 引用降级 undeclared_reference → 无 sha256 且不参与依赖闭包扫描
F4 非法路径（../ 越界）在 _add 中被静默丢弃，不产生任何告警
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
from app.services.tool_manifest import validate_tools  # noqa: E402

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


# F1: host 声明缺 sha256，文件存在 → 哈希校验被跳过（ok=True 即 fail-open 成立）
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    _mk(root, "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n    - path: demo/host/run.py\n",
        host_src="print('tampered')\n")
    r = validate_tools(root)
    check("F1 host 缺 sha256 时哈希校验被跳过（fail-open）",
          r["ok"] is True and not r["hash_mismatch"],
          f"ok={r['ok']} hash_mismatch={len(r['hash_mismatch'])}")

# F2: tools: {} 空对象 → declaration_gaps 不触发（gaps==0 即绕过成立，不要求整体 ok）
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    _mk(root, "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools: {}\n",
        host_src="print('hi')\n")
    r = validate_tools(root)
    check("F2 空 tools:{} 绕过 declaration_gaps（gaps=0）",
          not r["declaration_gaps"],
          f"gaps={len(r['declaration_gaps'])} ok={r['ok']}")

# F3: {host_tool_dir} 引用 → undeclared_reference：无 sha256 且不扫闭包。
#     把 run.py 放到 root/run.py 使引用存在 → 若仍 ok=True 且无闭包违规，则 fail-open 成立
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    (root / "common").mkdir(parents=True)
    (root / "common" / "adb_runner.py").write_text("X=1\n", encoding="utf-8")
    (root / "run.py").write_text(
        "import common.adb_runner\nprint(common.adb_runner.X)\n", encoding="utf-8")
    mdir = root / "demo" / "host"
    mdir.mkdir(parents=True)
    (root / "demo" / "manifest.yaml").write_text(
        "module:\n  name: demo\n"
        "items:\n  - name: t1\n    exec_type: host_exec\n"
        "    exec_command: python {host_tool_dir}/run.py\n"
        "tools: {}\n", encoding="utf-8")
    r = validate_tools(root)
    undeclared = [x for x in r["requirements"]
                  if x["kind"] == "undeclared_reference"]
    check("F3a {host_tool_dir} 引用降级为 undeclared_reference 且无 sha256",
          len(undeclared) == 1 and undeclared[0].get("sha256") is None,
          f"undeclared={[(u['name'], u.get('sha256')) for u in undeclared]}")
    check("F3b undeclared_reference 存在且其 common 导入不产生闭包违规（fail-open）",
          any(u["name"] == "run.py" for u in undeclared)
          and not r["closure_violations"],
          f"closure={len(r['closure_violations'])} ok={r['ok']}")

# F4: 非法路径静默丢弃
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "test-tools"
    _mk(root, "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n    - path: ../../etc/passwd\n")
    r = validate_tools(root)
    check("F4 非法路径（../）被静默丢弃且无告警",
          r["ok"] is True and not r["requirements"],
          f"ok={r['ok']} requirements={len(r['requirements'])}")

print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILED -> {FAILURES}")
    sys.exit(1)
print("RESULT: ALL PASS (fail-open 全部确认存在)")
