"""显式工具清单 + 哈希/依赖闭包校验（V1-08 / T-17 修订）。

核心变更（V1-08）：
- 必需工具**必须由 manifest 显式声明**（`tools:` 段）：host runner、共享 Python
  依赖闭包（common/*）、设备二进制（含 ABI/version）、可选测试资源（APK）。
- `discover_requirements` **不再仅 glob 现存文件**生成必需清单：删除任何已声明
  文件后，该条目仍存在并被判定缺失 → `assert_required_tools` 启动失败。
- 校验三类问题：文件不存在（missing）、SHA-256 不匹配（hash_mismatch）、
  依赖闭包缺失（closure_violations：host runner 引用的 common/兄弟模块未声明），
  另外模块目录含 host/二进制但 manifest 未声明 tools 时记 declaration_gaps（致命）。
- 只读：绝不写入/删除/移动 test-tools 下任何文件。

manifest `tools` 段格式（路径相对 test-tools 根）：
```yaml
tools:
  host:
    - path: upfm/host/mc_props_check.py
      sha256: <64 hex>
  shared:
    - path: common/adb_runner.py
      sha256: <64 hex>
  device:
    - path: emmc/binaries/armeabi-v7a/fio
      abi: armeabi-v7a
      version: unspecified
      sha256: <64 hex>
  assets:
    - path: upfm/assets/test_app.apk
      optional: true
```
"""

import ast
import hashlib
import logging
import re
import sys
from pathlib import Path
from typing import Optional, Union

import yaml

from app.config import get_settings

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.yaml"
HOST_TOOL_REF = re.compile(r"\{host_tool_dir\}/([^\s\"'`]+)")

KIND_HOST_RUNNER = "host_runner"
KIND_SHARED = "shared_python_dep"
KIND_DEVICE_BINARY = "device_binary"
KIND_ASSET = "asset"
KIND_UNDECLARED_REFERENCE = "undeclared_reference"

_DEVICE_KEYS = ("path", "abi", "version", "sha256")
_COMMON_IMPORT_FROM = re.compile(r"^\s*from\s+common\.(\w+)", re.MULTILINE)
_COMMON_IMPORT_FROM_PKG = re.compile(r"^\s*from\s+common\s+import\s+(.+)", re.MULTILINE)
_COMMON_IMPORT = re.compile(r"^\s*import\s+common\.(\w+)", re.MULTILINE)


class ToolManifestError(RuntimeError):
    """manifest 声明不完整、必需工具缺失/哈希不符/依赖闭包缺失。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _add(req: dict, rel: str, kind: str, *, required: bool, manifest: str,
         source: str, sha256: Optional[str] = None, abi: Optional[str] = None,
         version: Optional[str] = None, optional: bool = False) -> None:
    rel = (rel or "").replace("\\", "/").strip("/ ")
    if not rel or ".." in rel.split("/"):
        return
    entry = req.setdefault(
        rel,
        {
            "name": rel,
            "kind": kind,
            "required": required,
            "manifests": [],
            "sources": [],
            "sha256": sha256,
            "abi": abi,
            "version": version,
            "optional": optional,
        },
    )
    if manifest and manifest not in entry["manifests"]:
        entry["manifests"].append(manifest)
    if source and source not in entry["sources"]:
        entry["sources"].append(source)
    entry["required"] = entry["required"] or required
    entry.setdefault("sha256", sha256)
    if entry["sha256"] is None and sha256:
        entry["sha256"] = sha256
    if abi and not entry.get("abi"):
        entry["abi"] = abi
    if version and not entry.get("version"):
        entry["version"] = version
    entry["optional"] = entry["optional"] and optional


def _declared_tools(data: dict, manifest_path: str, req: dict) -> set[str]:
    """把 manifest 的 tools 声明并入 req，返回声明的 host 相对路径集合。"""
    tools = data.get("tools")
    host_paths: set[str] = set()
    if tools is None:
        return host_paths
    if not isinstance(tools, dict):
        raise ToolManifestError(f"{manifest_path}: tools 段必须是 YAML 对象")

    def _rows(key: str):
        rows = tools.get(key) or []
        if not isinstance(rows, list):
            raise ToolManifestError(f"{manifest_path}: tools.{key} 必须是列表")
        for row in rows:
            if not isinstance(row, dict) or not row.get("path"):
                raise ToolManifestError(f"{manifest_path}: tools.{key} 条目缺少 path: {row!r}")
            yield row

    for row in _rows("host"):
        rel = str(row["path"])
        _add(req, rel, KIND_HOST_RUNNER, required=True, manifest=manifest_path,
             source="tools.host", sha256=row.get("sha256"), version=row.get("version"))
        host_paths.add(rel.replace("\\", "/").strip("/ "))
    for row in _rows("shared"):
        _add(req, str(row["path"]), KIND_SHARED, required=True, manifest=manifest_path,
             source="tools.shared", sha256=row.get("sha256"), version=row.get("version"))
    for row in _rows("device"):
        missing = [k for k in ("path", "abi", "sha256") if not row.get(k)]
        if missing:
            raise ToolManifestError(
                f"{manifest_path}: tools.device 条目缺少必填字段 {missing}: {row!r}"
            )
        _add(req, str(row["path"]), KIND_DEVICE_BINARY, required=True, manifest=manifest_path,
             source=f"tools.device[{row['abi']}]", sha256=row["sha256"],
             abi=row["abi"], version=row.get("version"))
    for row in _rows("assets"):
        _add(req, str(row["path"]), KIND_ASSET, required=False, manifest=manifest_path,
             source="tools.assets", sha256=row.get("sha256"), optional=True)
    return host_paths


def discover_requirements(tools_root: Union[str, Path]):
    """只读扫描 tools_root，返回 (requirements: dict[rel -> entry], manifest_paths)。

    需求条目**仅来自 manifest 显式声明**（外加未声明引用的标记条目），
    不再因为文件存在就自动生成必需项。
    """
    root = Path(tools_root)
    manifest_paths = sorted(root.glob(f"*/{MANIFEST_FILENAME}"))
    requirements: dict[str, dict] = {}
    declared_host_anywhere: set[str] = set()

    for manifest_path in manifest_paths:
        try:
            data = _load_manifest(manifest_path)
        except (OSError, yaml.YAMLError, ValueError) as exc:
            raise ToolManifestError(f"manifest 解析失败: {manifest_path}: {exc}") from exc
        declared_host_anywhere |= _declared_tools(data, str(manifest_path), requirements)

    # 未声明引用：manifest item 的 host_exec 命令引用了本地 runner，但 tools.host 未声明
    for manifest_path in manifest_paths:
        try:
            data = _load_manifest(manifest_path)
        except (OSError, yaml.YAMLError, ValueError):
            continue
        for item in data.get("items") or []:
            if not isinstance(item, dict) or item.get("exec_type") != "host_exec":
                continue
            command = item.get("exec_command") or ""
            for rel in HOST_TOOL_REF.findall(command):
                clean = rel.replace("\\", "/").strip("/ ")
                if clean.lower().endswith(".apk") or clean in declared_host_anywhere:
                    continue
                _add(requirements, clean, KIND_UNDECLARED_REFERENCE, required=True,
                     manifest=str(manifest_path), source=str(item.get("name", "")))

    return requirements, [str(p) for p in manifest_paths]


def _imported_common_modules(host_file: Path) -> set[str]:
    """解析 host runner 中 `import common.x` / `from common.x import ..` 的 x。"""
    try:
        source = host_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    names = set(_COMMON_IMPORT_FROM.findall(source))
    names |= set(_COMMON_IMPORT.findall(source))
    for group in _COMMON_IMPORT_FROM_PKG.findall(source):
        for part in group.replace("(", " ").replace(")", " ").split(","):
            name = part.strip().split(" as ")[0].strip()
            if name:
                names.add(name)
    return names


def _imported_sibling_modules(host_file: Path) -> set[str]:
    """解析 host runner 导入的同目录兄弟模块（from X import / import X，且 X.py 存在）。"""
    try:
        tree = ast.parse(host_file.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return set()
    siblings = set()
    host_dir = host_file.parent
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if (host_dir / f"{name}.py").exists():
                    siblings.add(name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            name = node.module.split(".")[0]
            if (host_dir / f"{name}.py").exists():
                siblings.add(name)
    return siblings


def validate_tools(tools_root: Optional[Union[str, Path]] = None,
                   extra_required: Optional[list[str]] = None) -> dict:
    """只读校验显式工具清单：存在性 + sha256 + 依赖闭包。返回结构化结果。"""
    if tools_root is None:
        settings = get_settings()
        configured = Path(settings.TEST_TOOLS_PATH)
        root = configured if configured.is_absolute() else (Path.cwd() / configured)
    else:
        root = Path(tools_root)
    root = root.resolve()

    if not root.is_dir():
        raise ToolManifestError(
            f"TEST_TOOLS_PATH 不存在: {root}。干净镜像必须包含 manifest 显式声明的 test-tools"
            "（见 Dockerfile 与 docs/design/scheduler-and-data.md 第 6 节）"
        )

    requirements, manifest_paths = discover_requirements(root)
    for rel in extra_required or []:
        _add(requirements, rel, KIND_DEVICE_BINARY, required=True, manifest="extra_required",
             source="extra_required")

    missing_required: list[dict] = []
    hash_mismatch: list[dict] = []
    skipped: list[dict] = []
    declaration_gaps: list[dict] = []
    closure_violations: list[dict] = []

    for rel in sorted(requirements):
        entry = dict(requirements[rel])
        path = root / rel
        entry["exists"] = path.is_file()
        if not entry["exists"]:
            if entry["required"]:
                missing_required.append(entry)
            else:
                entry["reason"] = "可选测试资源缺失，按 R3 记 skip（不伪造已就绪）"
                skipped.append(entry)
            continue
        expected = entry.get("sha256")
        if expected is not None:
            actual = sha256_file(path)
            entry["actual_sha256"] = actual
            if actual.lower() != str(expected).strip().lower():
                hash_mismatch.append(entry)

    # 依赖闭包：host runner 引用的 common.x / 兄弟模块必须在声明中覆盖
    declared_paths = set(requirements.keys())
    for rel, entry in requirements.items():
        if entry["kind"] != KIND_HOST_RUNNER:
            continue
        host_file = root / rel
        if not host_file.is_file():
            continue
        for module_name in sorted(_imported_common_modules(host_file)):
            needed = f"common/{module_name}.py"
            if needed not in declared_paths:
                closure_violations.append({
                    "name": needed, "kind": KIND_SHARED, "required": True,
                    "manifests": entry["manifests"],
                    "sources": [f"{rel} imports common.{module_name}"],
                    "reason": "共享 Python 依赖未在 manifest tools.shared 声明",
                })
        host_dir_rel = str(Path(rel).parent).replace("\\", "/")
        for sibling in sorted(_imported_sibling_modules(host_file)):
            needed = f"{host_dir_rel}/{sibling}.py"
            if needed not in declared_paths:
                closure_violations.append({
                    "name": needed, "kind": KIND_HOST_RUNNER, "required": True,
                    "manifests": entry["manifests"],
                    "sources": [f"{rel} imports sibling {sibling}"],
                    "reason": "同目录兄弟模块未在 manifest tools.host 声明",
                })

    # 声明缺口：模块目录含 host/二进制但 manifest 未声明 tools（legacy manifest）
    for manifest_path in manifest_paths:
        try:
            data = _load_manifest(Path(manifest_path))
        except (OSError, yaml.YAMLError, ValueError):
            continue
        module_dir = Path(manifest_path).parent
        has_host = any((module_dir / "host").glob("*.py"))
        has_binaries = any((module_dir / "binaries").glob("*/*"))
        if "tools" not in data and (has_host or has_binaries):
            declaration_gaps.append({
                "name": str(manifest_path), "kind": "manifest", "required": True,
                "manifests": [str(manifest_path)],
                "sources": ["模块目录含 host/二进制但 manifest 无 tools 段"],
                "reason": "manifest 未显式声明 tools（V1-08 要求显式工具清单）",
            })

    for item in skipped:
        logger.warning("工具清单 skip: %s（%s）", item["name"], item.get("reason", ""))

    ok = not (missing_required or hash_mismatch or closure_violations or declaration_gaps)
    result = {
        "root": str(root),
        "manifest_paths": manifest_paths,
        "requirements": [dict(requirements[r]) for r in sorted(requirements)],
        "missing_required": missing_required,
        "hash_mismatch": hash_mismatch,
        "closure_violations": closure_violations,
        "declaration_gaps": declaration_gaps,
        "skipped": skipped,
        "ok": ok,
    }
    logger.info(
        "工具清单校验(V1-08 显式声明): root=%s manifests=%d 声明=%d 缺失=%d 哈希不符=%d "
        "闭包缺失=%d 声明缺口=%d skip=%d ok=%s",
        root, len(manifest_paths), len(result["requirements"]), len(missing_required),
        len(hash_mismatch), len(closure_violations), len(declaration_gaps), len(skipped), ok,
    )
    return result


def assert_required_tools(tools_root: Optional[Union[str, Path]] = None,
                          extra_required: Optional[list[str]] = None) -> dict:
    """启动门禁：任何声明缺失/哈希不符/闭包缺失/声明缺口都抛 ToolManifestError。"""
    result = validate_tools(tools_root, extra_required)
    problems: list[str] = []

    def _fmt(items: list[dict]) -> str:
        return "\n".join(
            f"  - {i['name']} [{i['kind']}] 声明于: {'; '.join(i['manifests'])}"
            + (f"（{i.get('reason','')}）" if i.get("reason") else "")
            for i in items
        )

    if result["missing_required"]:
        problems.append("缺少声明必需工具:\n" + _fmt(result["missing_required"]))
    if result["hash_mismatch"]:
        problems.append(
            "SHA-256 不匹配:\n"
            + "\n".join(
                f"  - {i['name']} 期望 {i['sha256']} 实际 {i.get('actual_sha256')}"
                for i in result["hash_mismatch"]
            )
        )
    if result["closure_violations"]:
        problems.append("共享依赖闭包缺失:\n" + _fmt(result["closure_violations"]))
    if result["declaration_gaps"]:
        problems.append("manifest 未显式声明工具清单:\n" + _fmt(result["declaration_gaps"]))
    if problems:
        raise ToolManifestError(
            "启动失败：TEST_TOOLS_PATH 工具清单校验未通过（V1-08 显式声明 + 哈希 + 依赖闭包）。\n"
            f"TEST_TOOLS_PATH={result['root']}\n" + "\n".join(problems)
        )
    return result


def main(argv=None) -> int:
    """生成/核对辅助：`python -m app.services.tool_manifest --emit <tools_root>` 打印各
    manifest 的 tools 声明 YAML（确定性，供人工核对/更新 manifest）。"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="V1-08 工具清单哈希生成/核对")
    parser.add_argument("--emit", metavar="TOOLS_ROOT", help="按现目录生成 tools 声明 YAML")
    parser.add_argument("--validate", metavar="TOOLS_ROOT", help="只读校验并输出 JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.emit:
        root = Path(args.emit).resolve()
        for manifest_path in sorted(root.glob(f"*/{MANIFEST_FILENAME}")):
            module_dir = manifest_path.parent
            print(f"# ---- {manifest_path.relative_to(root).as_posix()} ----")
            print("tools:")
            host = sorted(p for p in (module_dir / "host").glob("*.py")) if (module_dir / "host").is_dir() else []
            print("  host:")
            for p in host:
                print(f"    - path: {p.relative_to(root).as_posix()}")
                print(f'      sha256: "{sha256_file(p)}"')
            shared = sorted((root / "common").glob("*.py")) if (root / "common").is_dir() else []
            print("  shared:")
            for p in shared:
                print(f"    - path: {p.relative_to(root).as_posix()}")
                print(f'      sha256: "{sha256_file(p)}"')
            binaries = sorted((module_dir / "binaries").glob("*/*")) if (module_dir / "binaries").is_dir() else []
            print("  device:")
            for p in binaries:
                print(f"    - path: {p.relative_to(root).as_posix()}")
                print(f"      abi: {p.parent.name}")
                print("      version: unspecified")
                print(f'      sha256: "{sha256_file(p)}"')
            print()
        return 0
    if args.validate:
        root = Path(args.validate).resolve()
        try:
            result = validate_tools(root)
        except ToolManifestError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
