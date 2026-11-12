"""T-17 启动只读工具清单校验（干净部署契约，设计文档第 6 节）。

从 ``TEST_TOOLS_PATH`` 下各模块的 ``manifest.yaml`` 提取「声明工具」并只读核对：

- ``host_exec`` 命令中 ``{host_tool_dir}/<rel>`` 引用的 PC 端 runner 脚本 → 必需；
- 模块 ``binaries/<arch>/`` 下的设备端二进制（各架构） → 必需；
- 命令中引用的 ``.apk`` 等测试资源 → 可选：缺失按 R3 记 **skip**，不伪造已就绪，
  也不阻断启动（放好资源后重跑即可）。

「manifest 声明存在但镜像/目录缺失的必需工具」→ ``ToolManifestError``，错误信息
必须指出缺失工具与其 manifest 路径；``app/main.py`` 的 lifespan 调用
``assert_required_tools()`` 接入启动失败路径。

本模块对 test-tools 只读：绝不写入、删除或移动任何文件。
"""

import logging
import re
from pathlib import Path
from typing import Optional, Union

import yaml

from app.config import get_settings

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.yaml"

# host_exec 命令中的 {host_tool_dir}/<相对路径> 引用
_HOST_TOOL_REF = re.compile(r"\{host_tool_dir\}/([^\s\"'`]+)")
# 引用了也允许缺失的测试资源后缀（范围内 APK/资源缺失按 R3 记 skip）
_OPTIONAL_SUFFIXES = (".apk",)

KIND_HOST_RUNNER = "host_runner"
KIND_DEVICE_BINARY = "device_binary"
KIND_ASSET = "asset"


class ToolManifestError(RuntimeError):
    """manifest 声明的必需工具缺失或 manifest 无法解析。"""


def _load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("manifest 顶层必须是 YAML 对象")
    module = data.get("module")
    if not isinstance(module, dict) or not module.get("name"):
        raise ValueError("manifest 缺少 module.name")
    items = data.get("items")
    if items is not None and not isinstance(items, list):
        raise ValueError("manifest items 必须是列表")
    return data


def _add(requirement: dict, rel: str, kind: str, required: bool,
         manifest: str, source: str) -> None:
    rel = rel.replace("\\", "/").strip("/ ")
    if not rel or ".." in rel.split("/"):
        return  # 拒绝越出 test-tools 根目录的引用
    entry = requirement.setdefault(
        rel,
        {
            "name": rel,
            "kind": kind,
            "required": required,
            "manifests": [],
            "sources": [],
        },
    )
    if manifest and manifest not in entry["manifests"]:
        entry["manifests"].append(manifest)
    if source and source not in entry["sources"]:
        entry["sources"].append(source)
    # 同一相对路径被更强类别引用时按必需处理
    entry["required"] = entry["required"] or required


def discover_requirements(tools_root: Union[str, Path]):
    """只读扫描 tools_root，返回 (requirements: dict[rel -> entry], manifest_paths: list[str])。

    manifest 解析失败属配置错误：抛 ToolManifestError（指出 manifest 路径），启动失败。
    """
    root = Path(tools_root)
    manifest_paths = sorted(root.glob(f"*/{MANIFEST_FILENAME}"))
    requirements: dict[str, dict] = {}

    for manifest_path in manifest_paths:
        try:
            data = _load_manifest(manifest_path)
        except (OSError, yaml.YAMLError, ValueError) as exc:
            raise ToolManifestError(f"manifest 解析失败: {manifest_path}: {exc}") from exc

        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            if item.get("exec_type") != "host_exec":
                continue
            command = item.get("exec_command") or ""
            for rel in _HOST_TOOL_REF.findall(command):
                kind = KIND_ASSET if rel.lower().endswith(_OPTIONAL_SUFFIXES) else KIND_HOST_RUNNER
                _add(
                    requirements,
                    rel,
                    kind,
                    required=(kind != KIND_ASSET),
                    manifest=str(manifest_path),
                    source=str(item.get("name", "")),
                )

    # 各架构设备端二进制：按目录约定 binaries/<arch>/<tool> 声明（必需）。
    for binary in sorted(root.glob("*/binaries/*/*")):
        if binary.is_file():
            module_dir = binary.parent.parent.parent
            declared = module_dir / MANIFEST_FILENAME
            manifest_label = (
                str(declared) if declared.exists()
                else f"{module_dir.name}/（无 manifest，按 binaries/<arch> 目录约定声明）"
            )
            _add(
                requirements,
                binary.relative_to(root).as_posix(),
                KIND_DEVICE_BINARY,
                required=True,
                manifest=manifest_label,
                source="binaries/<arch> 目录约定",
            )

    return requirements, [str(p) for p in manifest_paths]


def validate_tools(tools_root: Optional[Union[str, Path]] = None,
                   extra_required: Optional[list[str]] = None) -> dict:
    """只读校验工具清单，返回结构化结果；不抛「缺失」异常（由 assert 版本负责）。

    返回: {root, manifest_paths, requirements, missing_required, skipped, ok}
    """
    if tools_root is None:
        settings = get_settings()
        configured = Path(settings.TEST_TOOLS_PATH)
        root = configured if configured.is_absolute() else (Path.cwd() / configured)
    else:
        root = Path(tools_root)
    root = root.resolve()

    if not root.is_dir():
        raise ToolManifestError(
            f"TEST_TOOLS_PATH 不存在: {root}。"
            "干净镜像必须包含 manifest 声明的 test-tools（见 Dockerfile 与 docs/design/scheduler-and-data.md 第 6 节）"
        )

    requirements, manifest_paths = discover_requirements(root)
    for rel in extra_required or []:
        _add(requirements, rel, KIND_DEVICE_BINARY, True, "extra_required", "extra_required")

    requirement_rows = []
    missing_required = []
    skipped = []
    for rel in sorted(requirements):
        entry = dict(requirements[rel])
        entry["exists"] = (root / rel).exists()
        requirement_rows.append(entry)
        if entry["exists"]:
            continue
        if entry["required"]:
            missing_required.append(entry)
        else:
            entry["reason"] = "可选测试资源缺失，按 R3 记 skip（不伪造已就绪）"
            skipped.append(entry)

    for item in skipped:
        logger.warning("工具清单 skip: %s（%s）", item["name"], item["reason"])

    result = {
        "root": str(root),
        "manifest_paths": manifest_paths,
        "requirements": requirement_rows,
        "missing_required": missing_required,
        "skipped": skipped,
        "ok": not missing_required,
    }
    logger.info(
        "工具清单校验: root=%s manifests=%d 必需工具=%d 缺失=%d skip=%d ok=%s",
        root, len(manifest_paths), len(requirement_rows), len(missing_required), len(skipped), result["ok"],
    )
    return result


def assert_required_tools(tools_root: Optional[Union[str, Path]] = None,
                          extra_required: Optional[list[str]] = None) -> dict:
    """启动门禁：必需工具缺失时抛 ToolManifestError，信息指出缺失工具与 manifest 路径。"""
    result = validate_tools(tools_root, extra_required)
    if result["missing_required"]:
        lines = "\n".join(
            f"  - {item['name']} [{item['kind']}] 声明于: {'; '.join(item['manifests'])}"
            f"（引用自: {', '.join(item['sources']) or '-'}）"
            for item in result["missing_required"]
        )
        raise ToolManifestError(
            "启动失败：TEST_TOOLS_PATH 下缺少 manifest 声明的必需工具（镜像/目录不完整）。\n"
            f"TEST_TOOLS_PATH={result['root']}\n"
            f"缺失清单:\n{lines}\n"
            "请核对 Dockerfile 是否完整复制 test-tools（manifest + runner + 各架构二进制）。"
        )
    return result
