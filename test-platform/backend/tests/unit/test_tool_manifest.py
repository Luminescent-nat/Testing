"""T-17 工具清单启动校验契约测试（先于实现编写的红测）。

覆盖 docs/design/scheduler-and-data.md 第 6 节：
- manifest 声明的必需工具（host_exec runner + 各架构 device 二进制）在镜像内缺失时，
  启动校验必须失败并指出 manifest 路径；
- 范围内 APK 等可选资源缺失必须记为 skip，不伪造为已就绪、也不阻断启动；
- 无 manifest 时仅告警不阻断（API-only 场景）。
"""
from pathlib import Path

import pytest

from app.services.tool_manifest import (
    ToolManifestError,
    assert_required_tools,
    validate_tools,
)

REPO_TEST_TOOLS = Path(__file__).resolve().parents[3] / "test-tools"


def _write_manifest(root: Path, module: str, items: list[dict]) -> Path:
    mod_dir = root / module
    (mod_dir / "host").mkdir(parents=True, exist_ok=True)
    lines = [f"module:", f"  name: {module}", "items:"]
    for item in items:
        lines.append(f"- name: {item['name']}")
        lines.append(f"  exec_type: {item['exec_type']}")
        lines.append(f"  exec_command: '{item['exec_command']}'")
    manifest = mod_dir / "manifest.yaml"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    return path


def test_all_declared_required_tools_present(tmp_path):
    root = tmp_path / "test-tools"
    _write_manifest(
        root,
        "mod",
        [
            {"name": "runner", "exec_type": "host_exec",
             "exec_command": 'python "{host_tool_dir}/mod/host/run.py" --serial {serial}'},
        ],
    )
    _touch(root / "mod" / "host" / "run.py")
    _touch(root / "mod" / "binaries" / "armeabi-v7a" / "tool")

    result = validate_tools(root)
    assert result["ok"] is True
    assert result["missing_required"] == []
    names = {req["name"] for req in result["requirements"]}
    assert "mod/host/run.py" in names
    assert "mod/binaries/armeabi-v7a/tool" in names
    assert result["manifest_paths"]


def test_missing_required_runner_fails_and_names_manifest(tmp_path):
    root = tmp_path / "test-tools"
    manifest = _write_manifest(
        root,
        "mod",
        [
            {"name": "runner", "exec_type": "host_exec",
             "exec_command": 'python "{host_tool_dir}/mod/host/missing.py" --serial {serial}'},
        ],
    )
    result = validate_tools(root)
    assert result["ok"] is False
    missing_names = {item["name"] for item in result["missing_required"]}
    assert "mod/host/missing.py" in missing_names

    with pytest.raises(ToolManifestError) as excinfo:
        assert_required_tools(root)
    message = str(excinfo.value)
    assert "mod/host/missing.py" in message
    assert str(manifest) in message  # 必须指出 manifest 路径


def test_missing_optional_apk_is_skip_not_failure(tmp_path):
    root = tmp_path / "test-tools"
    _write_manifest(
        root,
        "mod",
        [
            {"name": "install", "exec_type": "host_exec",
             "exec_command": 'python "{host_tool_dir}/mod/host/run.py" --apk "{host_tool_dir}/mod/assets/test_app.apk"'},
        ],
    )
    _touch(root / "mod" / "host" / "run.py")
    # assets/test_app.apk 故意缺失

    result = validate_tools(root)
    assert result["ok"] is True
    assert result["missing_required"] == []
    skipped_names = {item["name"] for item in result["skipped"]}
    assert "mod/assets/test_app.apk" in skipped_names
    # 可选缺失不得让启动失败
    assert assert_required_tools(root)["ok"] is True


def test_missing_binary_is_required_failure(tmp_path):
    root = tmp_path / "test-tools"
    _write_manifest(
        root,
        "mod",
        [
            {"name": "runner", "exec_type": "host_exec",
             "exec_command": 'python "{host_tool_dir}/mod/host/run.py" --serial {serial}'},
        ],
    )
    _touch(root / "mod" / "host" / "run.py")
    # 声明目录里缺少某个架构二进制：manifest 本身未逐个列出，但按目录约定探测到缺失
    (root / "mod" / "binaries" / "arm64-v8a").mkdir(parents=True)
    # 用 requirements 显式注入一个缺失的声明二进制，模拟 manifest tools: 段声明
    result = validate_tools(root, extra_required=["mod/binaries/arm64-v8a/fio"])
    assert result["ok"] is False
    assert any(x["name"] == "mod/binaries/arm64-v8a/fio" for x in result["missing_required"])


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


def test_real_repo_test_tools_is_consistent():
    """真实仓库 test-tools：manifest 声明的必需工具都在，缺失的测试 APK 记 skip。"""
    result = validate_tools(REPO_TEST_TOOLS)
    assert result["ok"] is True, result["missing_required"]
    names = {req["name"] for req in result["requirements"]}
    assert "upfm/host/mc_props_check.py" in names
    assert "emmc/host/emmc_fio_runner.py" in names
    assert any(name.endswith(".apk") for name, _ in [(s["name"], s) for s in result["skipped"]])
    # manifest 路径必须被记录
    assert any(str(REPO_TEST_TOOLS / "upfm" / "manifest.yaml") == p for p in result["manifest_paths"])
