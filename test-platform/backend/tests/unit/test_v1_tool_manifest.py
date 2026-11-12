"""V1-08 显式工具清单/哈希/依赖闭包契约测试。

对应审计 RR-V1-READINESS-20261112 V1-08：
- 由 manifest 显式声明必需工具；**删除已声明文件后条目仍在且启动校验失败**
  （不再靠 glob 现存文件生成必需清单）；
- SHA-256 不匹配、共享 Python 依赖闭包缺失、同目录兄弟模块未声明都使启动失败；
- 无 manifest 的根目录不虚构需求（仅告警，ok）；
- 真实仓库所有 manifest 必须显式声明 tools，且哈希与实际文件一致。

实现前红测证据：审计定向复现
docs/verification/reviews/evidence/v1-readiness-20261112/targeted-defect-repro.log
中 test_audit_missing_device_binary_remains_a_required_manifest_entry 失败。
"""
import hashlib
from pathlib import Path

import pytest

from app.services.tool_manifest import (
    ToolManifestError,
    assert_required_tools,
    discover_requirements,
    validate_tools,
)

REPO_TEST_TOOLS = Path(__file__).resolve().parents[3] / "test-tools"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _manifest(root: Path, module: str, body: str) -> Path:
    (root / module).mkdir(parents=True, exist_ok=True)
    path = root / module / "manifest.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_deleting_declared_device_binary_keeps_requirement_and_fails_startup(tmp_path):
    """删除已声明必需设备二进制后：条目仍在、validate 缺失、启动门禁失败。"""
    root = tmp_path / "test-tools"
    binary = _write(root / "demo" / "binaries" / "arm64-v8a" / "tool", "audit-binary")
    _manifest(
        root,
        "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  device:\n"
        "    - path: demo/binaries/arm64-v8a/tool\n"
        "      abi: arm64-v8a\n"
        "      version: '1.0'\n"
        f"      sha256: {_sha(binary)}\n",
    )

    before, _ = discover_requirements(root)
    assert "demo/binaries/arm64-v8a/tool" in before

    binary.unlink()
    after, _ = discover_requirements(root)
    assert "demo/binaries/arm64-v8a/tool" in after, "删除文件后声明条目不能消失"

    result = validate_tools(root)
    assert result["ok"] is False
    assert any(i["name"] == "demo/binaries/arm64-v8a/tool" for i in result["missing_required"])
    with pytest.raises(ToolManifestError) as excinfo:
        assert_required_tools(root)
    assert "demo/binaries/arm64-v8a/tool" in str(excinfo.value)


def test_legacy_manifest_without_tools_is_rejected(tmp_path):
    """审计复现的字面场景：manifest 无 tools 段但目录有二进制 → 不再 glob，判声明缺口失败。"""
    root = tmp_path / "test-tools"
    _write(root / "demo" / "binaries" / "arm64-v8a" / "tool", "audit-binary")
    _manifest(root, "demo", "module:\n  name: demo\nitems: []\n")

    reqs, _ = discover_requirements(root)
    assert "demo/binaries/arm64-v8a/tool" not in reqs  # 不再由现存文件虚构必需项

    result = validate_tools(root)
    assert result["ok"] is False
    assert result["declaration_gaps"], "无 tools 声明的模块目录必须记为声明缺口"
    with pytest.raises(ToolManifestError):
        assert_required_tools(root)


def test_sha256_mismatch_fails(tmp_path):
    root = tmp_path / "test-tools"
    runner = _write(root / "demo" / "host" / "run.py", "print('ok')\n")
    _manifest(
        root,
        "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n"
        "    - path: demo/host/run.py\n"
        "      sha256: \"" + "f" * 64 + "\"\n",
    )
    result = validate_tools(root)
    assert result["ok"] is False
    assert any(i["name"] == "demo/host/run.py" for i in result["hash_mismatch"])
    with pytest.raises(ToolManifestError) as excinfo:
        assert_required_tools(root)
    assert "SHA-256" in str(excinfo.value)
    # 正确哈希应通过（对照组）
    _manifest(
        root,
        "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n"
        "    - path: demo/host/run.py\n"
        f"      sha256: \"{_sha(runner)}\"\n",
    )
    assert validate_tools(root)["ok"] is True


def test_missing_shared_dependency_fails(tmp_path):
    root = tmp_path / "test-tools"
    _write(root / "demo" / "host" / "run.py", "from common.adb_runner import AdbRunner\n")
    _write(root / "common" / "adb_runner.py", "class AdbRunner: pass\n")
    _manifest(
        root,
        "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n"
        "    - path: demo/host/run.py\n"
        f"      sha256: {_sha(root / 'demo' / 'host' / 'run.py')}\n"
        "  shared:\n"
        "    - path: common/adb_runner.py\n"
        f"      sha256: {_sha(root / 'common' / 'adb_runner.py')}\n",
    )
    assert validate_tools(root)["ok"] is True

    (root / "common" / "adb_runner.py").unlink()
    result = validate_tools(root)
    assert result["ok"] is False
    assert any(i["name"] == "common/adb_runner.py" for i in result["missing_required"])
    with pytest.raises(ToolManifestError):
        assert_required_tools(root)


def test_undeclared_common_import_is_closure_violation(tmp_path):
    root = tmp_path / "test-tools"
    _write(root / "demo" / "host" / "run.py", "from common.device_info import detect_arch\n")
    _write(root / "common" / "device_info.py", "def detect_arch(a): return 'x'\n")
    _write(root / "common" / "logger.py", "def setup_logger(): pass\n")
    _manifest(
        root,
        "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n"
        "    - path: demo/host/run.py\n"
        f"      sha256: {_sha(root / 'demo' / 'host' / 'run.py')}\n"
        "  shared:\n"
        "    - path: common/logger.py\n"
        f"      sha256: {_sha(root / 'common' / 'logger.py')}\n",
    )
    result = validate_tools(root)
    assert result["ok"] is False
    assert any(i["name"] == "common/device_info.py" for i in result["closure_violations"])
    with pytest.raises(ToolManifestError) as excinfo:
        assert_required_tools(root)
    assert "依赖闭包" in str(excinfo.value)


def test_undeclared_sibling_module_is_closure_violation(tmp_path):
    root = tmp_path / "test-tools"
    _write(root / "demo" / "host" / "run.py", "from helper import tool\n")
    _write(root / "demo" / "host" / "helper.py", "def tool(): return 1\n")
    _manifest(
        root,
        "demo",
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  host:\n"
        "    - path: demo/host/run.py\n"
        f"      sha256: {_sha(root / 'demo' / 'host' / 'run.py')}\n",
    )
    result = validate_tools(root)
    assert result["ok"] is False
    assert any(i["name"] == "demo/host/helper.py" for i in result["closure_violations"])


def test_extra_required_missing_binary_fails(tmp_path):
    root = tmp_path / "test-tools"
    _manifest(root, "demo", "module:\n  name: demo\nitems: []\ntools:\n  host: []\n")
    result = validate_tools(root, extra_required=["demo/binaries/x/y"])
    assert result["ok"] is False
    assert any(i["name"] == "demo/binaries/x/y" for i in result["missing_required"])


def test_no_manifest_root_warns_but_ok(tmp_path):
    root = tmp_path / "test-tools"
    root.mkdir()
    result = validate_tools(root)
    assert result["ok"] is True
    assert result["manifest_paths"] == []
    assert result["requirements"] == []


def test_missing_tools_root_fails():
    with pytest.raises(ToolManifestError):
        assert_required_tools(Path("D:/__definitely_not_here_test_tools__"))


def test_real_repo_manifests_are_explicit_and_hashes_match():
    """真实仓库：所有 manifest 显式声明 tools，哈希与文件一致，闭包完整，host 启动校验通过。"""
    result = validate_tools(REPO_TEST_TOOLS)
    assert result["ok"] is True, {
        "missing": [i["name"] for i in result["missing_required"]],
        "hash": [i["name"] for i in result["hash_mismatch"]],
        "closure": [i["name"] for i in result["closure_violations"]],
        "gaps": [i["name"] for i in result["declaration_gaps"]],
    }
    assert result["declaration_gaps"] == []
    names = {r["name"] for r in result["requirements"]}
    assert "upfm/host/mc_props_check.py" in names
    assert "emmc/host/emmc_fio_runner.py" in names
    assert "emmc/binaries/armeabi-v7a/fio" in names
    # 所有必需项都必须带 sha256；device 必须带 abi
    for entry in result["requirements"]:
        if entry["required"]:
            assert entry["sha256"], entry
        if entry["kind"] == "device_binary":
            assert entry["abi"], entry
    # 缺失的测试 APK 仍按可选 skip 处理
    assert any(s["name"] == "upfm/assets/test_app.apk" for s in result["skipped"])
