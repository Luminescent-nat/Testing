"""T-17 工具清单启动校验契约测试（V1-08 显式清单/哈希/闭包语义）。

覆盖 docs/design/scheduler-and-data.md 第 6 节 + V1-08：
- manifest **显式声明**必需工具（host runner / shared 依赖 / device 二进制）；缺失时启动校验失败并指出 manifest 路径；
- 范围内 APK 等可选资源缺失记 skip，不伪造、不阻断；
- SHA-256 校验与依赖闭包由 test_v1_tool_manifest.py 深入覆盖；
- 无 manifest 时仅告警不阻断（API-only 场景）。
"""
import hashlib
from pathlib import Path

import pytest

from app.services.tool_manifest import (
    ToolManifestError,
    assert_required_tools,
    validate_tools,
)

REPO_TEST_TOOLS = Path(__file__).resolve().parents[3] / "test-tools"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(root: Path, module: str, items: list[dict], tools: str = "") -> Path:
    mod_dir = root / module
    (mod_dir / "host").mkdir(parents=True, exist_ok=True)
    lines = ["module:", f"  name: {module}", "items:"]
    for item in items:
        lines.append(f"- name: {item['name']}")
        lines.append(f"  exec_type: {item['exec_type']}")
        lines.append(f"  exec_command: '{item['exec_command']}'")
    if tools:
        lines.append(tools)
    manifest = mod_dir / "manifest.yaml"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def _touch(path: Path, content: str = "#!/bin/sh\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_all_declared_required_tools_present(tmp_path):
    root = tmp_path / "test-tools"
    _touch(root / "mod" / "host" / "run.py", "print('ok')\n")
    _touch(root / "mod" / "binaries" / "armeabi-v7a" / "tool", "bin")
    _write_manifest(
        root,
        "mod",
        [{"name": "runner", "exec_type": "host_exec",
          "exec_command": 'python "{host_tool_dir}/mod/host/run.py" --serial {serial}'}],
        tools=(
            "tools:\n  host:\n"
            "    - path: mod/host/run.py\n"
            f"      sha256: {_sha(root / 'mod' / 'host' / 'run.py')}\n"
            "  device:\n"
            "    - path: mod/binaries/armeabi-v7a/tool\n"
            "      abi: armeabi-v7a\n"
            "      version: '1.0'\n"
            f"      sha256: {_sha(root / 'mod' / 'binaries' / 'armeabi-v7a' / 'tool')}\n"
        ),
    )

    result = validate_tools(root)
    assert result["ok"] is True, result
    assert result["missing_required"] == []
    names = {req["name"] for req in result["requirements"]}
    assert "mod/host/run.py" in names
    assert "mod/binaries/armeabi-v7a/tool" in names
    assert result["manifest_paths"]


def test_missing_required_runner_fails_and_names_manifest(tmp_path):
    """A3（契约 v1.1）：未声明的 {host_tool_dir} 引用 → 加载硬失败，指明 manifest 与引用值。"""
    root = tmp_path / "test-tools"
    manifest = _write_manifest(
        root,
        "mod",
        [{"name": "runner", "exec_type": "host_exec",
          "exec_command": 'python "{host_tool_dir}/mod/host/missing.py" --serial {serial}'}],
    )
    with pytest.raises(ToolManifestError) as excinfo:
        validate_tools(root)
    message = str(excinfo.value)
    assert "mod/host/missing.py" in message
    assert str(manifest) in message

    with pytest.raises(ToolManifestError) as excinfo2:
        assert_required_tools(root)
    assert "mod/host/missing.py" in str(excinfo2.value)
    assert str(manifest) in str(excinfo2.value)


def test_missing_optional_apk_is_skip_not_failure(tmp_path):
    root = tmp_path / "test-tools"
    _touch(root / "mod" / "host" / "run.py", "print('install')\n")
    _write_manifest(
        root,
        "mod",
        [{"name": "install", "exec_type": "host_exec",
          "exec_command": 'python "{host_tool_dir}/mod/host/run.py" --apk "{host_tool_dir}/mod/assets/test_app.apk"'}],
        tools=(
            "tools:\n  host:\n"
            "    - path: mod/host/run.py\n"
            f"      sha256: {_sha(root / 'mod' / 'host' / 'run.py')}\n"
            "  assets:\n"
            "    - path: mod/assets/test_app.apk\n"
            "      optional: true\n"
        ),
    )
    # assets/test_app.apk 故意缺失

    result = validate_tools(root)
    assert result["ok"] is True, result
    assert result["missing_required"] == []
    skipped_names = {item["name"] for item in result["skipped"]}
    assert "mod/assets/test_app.apk" in skipped_names
    assert assert_required_tools(root)["ok"] is True


def test_missing_binary_is_required_failure(tmp_path):
    root = tmp_path / "test-tools"
    _touch(root / "mod" / "host" / "run.py", "print('ok')\n")
    _write_manifest(
        root,
        "mod",
        [{"name": "runner", "exec_type": "host_exec",
          "exec_command": 'python "{host_tool_dir}/mod/host/run.py" --serial {serial}'}],
        tools=(
            "tools:\n  host:\n"
            "    - path: mod/host/run.py\n"
            f"      sha256: {_sha(root / 'mod' / 'host' / 'run.py')}\n"
        ),
    )
    result = validate_tools(root, extra_required=["mod/binaries/arm64-v8a/fio"])
    assert result["ok"] is False
    assert any(x["name"] == "mod/binaries/arm64-v8a/fio" for x in result["missing_required"])


def test_no_manifest_root_rejected_a5(tmp_path):
    """A5（契约 v1.1）：TEST_TOOLS_PATH 存在但无 manifest.yaml → 拒绝启动（原 ok=True 语义反转）。"""
    root = tmp_path / "test-tools"
    root.mkdir()
    result = validate_tools(root)
    assert result["ok"] is False, "空工具目录不得静默通过"
    assert result["manifest_paths"] == []
    with pytest.raises(ToolManifestError) as excinfo:
        assert_required_tools(root)
    assert str(root.resolve()) in str(excinfo.value) or str(root) in str(excinfo.value)


def test_missing_tools_root_fails():
    with pytest.raises(ToolManifestError):
        assert_required_tools(Path("D:/__definitely_not_here_test_tools__"))


def test_real_repo_test_tools_is_consistent():
    """真实仓库 test-tools：manifest 显式声明的必需工具都在且哈希一致，缺失的测试 APK 记 skip。"""
    result = validate_tools(REPO_TEST_TOOLS)
    assert result["ok"] is True, {
        "missing": [i["name"] for i in result["missing_required"]],
        "hash": [i["name"] for i in result["hash_mismatch"]],
        "closure": [i["name"] for i in result["closure_violations"]],
        "gaps": [i["name"] for i in result["declaration_gaps"]],
    }
    names = {req["name"] for req in result["requirements"]}
    assert "upfm/host/mc_props_check.py" in names
    assert "emmc/host/emmc_fio_runner.py" in names
    assert any(s["name"].endswith(".apk") for s in result["skipped"])
    assert any(str(REPO_TEST_TOOLS / "upfm" / "manifest.yaml") == p for p in result["manifest_paths"])
