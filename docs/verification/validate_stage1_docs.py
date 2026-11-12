from pathlib import Path
import json
import re
import sys
from urllib.parse import unquote

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

root = Path("D:/MCTEST/docs")
errors = []
checks = []


def require(condition, message):
    if not condition:
        errors.append(message)


def ok(label, detail):
    checks.append(f"PASS {label}: {detail}")


files = sorted(root.rglob("*.md"))
texts = {}
for path in files:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        errors.append(f"UTF-8读取失败 {path}: {exc}")
        continue
    texts[path] = text
    require("\ufffd" not in text, f"存在替换字符: {path}")
    require(
        not re.search(r"[\U0001F000-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]", text),
        f"存在emoji: {path}",
    )
ok("Markdown/UTF-8/无emoji", f"{len(texts)}个文件")

json_count = 0
for path, text in texts.items():
    for index, block in enumerate(
        re.findall(r"```json\s*\n(.*?)```", text, re.S), 1
    ):
        try:
            json.loads(block)
            json_count += 1
        except Exception as exc:
            errors.append(f"JSON无效 {path.relative_to(root)} 第{index}块: {exc}")
ok("JSON示例", f"{json_count}块完成解析")

link_count = 0
for path, text in texts.items():
    for match in re.finditer(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
        target = match.group(1).strip().strip("<>")
        if not target or target.startswith(
            ("#", "http://", "https://", "mailto:", "data:")
        ):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        resolved = (path.parent / unquote(target)).resolve()
        require(
            resolved.exists(),
            f"相对链接不存在 {path.relative_to(root)} -> {match.group(1)}",
        )
        link_count += 1
ok("相对链接", f"{link_count}个目标存在")

adr_files = sorted((root / "adr").glob("adr-*.md"))
require(len(adr_files) == 8, f"ADR数量应为8，实际{len(adr_files)}")
for path in adr_files:
    text = texts[path]
    require("- 状态：accepted" in text, f"ADR未accepted: {path.name}")
    require("2026-11-12 用户确认" in text, f"ADR缺确认记录: {path.name}")
    for heading in ("## 背景", "## 决策", "## 备选方案", "## 后果", "## 状态"):
        require(heading in text, f"ADR缺{heading}: {path.name}")
adr_index = texts[root / "adr" / "README.md"]
require(len(re.findall(r"\| accepted \|", adr_index)) == 8, "ADR索引accepted数量不是8")
require("确认前使用 `proposed`" in adr_index, "ADR索引未来proposed流程被误改")
ok("ADR", "8篇accepted、五段及确认记录齐全")

required_sections = (
    "## 结构",
    "## 变体",
    "## 状态",
    "## 交互",
    "## 响应式断点",
    "## 可访问性",
)
states = (
    "default",
    "hover",
    "active",
    "focus",
    "disabled",
    "loading",
    "empty",
    "error",
    "readonly",
)
component_files = sorted((root / "design" / "components").glob("*.md"))
page_files = sorted((root / "design" / "pages").glob("*.md"))
require(len(component_files) == 6, f"组件规格应为6，实际{len(component_files)}")
require(len(page_files) == 15, f"页面规格应为15，实际{len(page_files)}")
for path in component_files + page_files:
    text = texts[path]
    require("评审版，待用户确认" in text, f"规格评审状态缺失: {path.name}")
    for section in required_sections:
        require(section in text, f"规格缺{section}: {path.relative_to(root)}")
    if "## 状态" in text and "## 交互" in text:
        state_text = text.split("## 状态", 1)[1].split("## 交互", 1)[0]
        for state in states:
            require(
                re.search(rf"\|\s*{re.escape(state)}\s*\|", state_text) is not None,
                f"缺状态{state}: {path.relative_to(root)}",
            )
    for bp in ("<768px", "768~1024px", ">1024px"):
        require(bp in text, f"缺断点{bp}: {path.relative_to(root)}")
    require(
        not re.search(r"#[0-9A-Fa-f]{6}\b", text),
        f"规格存在裸十六进制颜色: {path.relative_to(root)}",
    )
ok("六段规格", f"{len(component_files)}组件+{len(page_files)}页面，九状态/三断点齐全")

expected_components = (
    "StatusTag",
    "BoundaryState",
    "MetricCard",
    "TaskProgress",
    "DeviceSelect",
    "ReportSummary",
)
expected_pages = (
    "MainLayout",
    "LoginPage",
    "DashboardPage",
    "DevicesPage",
    "ModulesPage",
    "AITestPage",
    "TasksPage",
    "TaskCreatePage",
    "TaskMonitorPage",
    "ReportsPage",
    "MemoryPage",
    "KnowledgePage",
    "AdminUsersPage",
    "ProfilePage",
    "NotFoundPage",
)


def get_block(text, name):
    match = re.search(rf"^## {re.escape(name)}\s*$", text, re.M)
    if not match:
        return None
    next_match = re.search(r"^## ", text[match.end() :], re.M)
    end = match.end() + next_match.start() if next_match else len(text)
    return text[match.start() : end]


def validate_contract(path, names):
    text = texts[path]
    require("待用户确认" in text, f"前端契约缺待确认状态: {path.name}")
    table_count = 0
    for name in names:
        block = get_block(text, name)
        require(block is not None, f"契约缺组件/页面{name}: {path.name}")
        if block is None:
            continue
        for table in ("props", "state", "events", "插槽"):
            require(f"### {table}" in block, f"{name}缺{table}表: {path.name}")
            table_count += 1
        props = (
            block.split("### props", 1)[1].split("### state", 1)[0]
            if "### props" in block and "### state" in block
            else ""
        )
        real_props = 0
        for line in props.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if (
                len(cells) != 5
                or cells[0] in ("名称", "---")
                or set(cells[0]) == {"-"}
            ):
                continue
            prop_name, prop_type, required, default, description = cells
            if prop_name == "无":
                continue
            real_props += 1
            require(not re.search(r"\bany\b", prop_type), f"{name}.{prop_name}使用any")
            require(bool(description), f"{name}.{prop_name}缺说明")
            if required == "是":
                require(default == "无", f"{name}.{prop_name}必填prop不应有默认值")
            elif required == "否":
                require(default not in ("", "无"), f"{name}.{prop_name}可选prop缺默认值")
            else:
                errors.append(f"{name}.{prop_name}必填列非法: {required}")
        require(real_props <= 10, f"{name} props超过10个")
        if "### events" in block and "### 插槽" in block:
            events = block.split("### events", 1)[1].split("### 插槽", 1)[0]
            for line in events.splitlines():
                if not line.startswith("|"):
                    continue
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                if (
                    len(cells) != 3
                    or cells[0] in ("事件名", "---")
                    or set(cells[0]) == {"-"}
                ):
                    continue
                event_name, payload, _ = cells
                require(
                    event_name == "无"
                    or re.fullmatch(r"on[A-Z][A-Za-z0-9]*", event_name) is not None,
                    f"{name}事件名非onXxx: {event_name}",
                )
                require(
                    not re.search(r"\bany\b", payload),
                    f"{name}.{event_name}载荷使用any",
                )
    return table_count


component_tables = validate_contract(
    root / "contracts" / "frontend-components-v1.0-review.md", expected_components
)
page_tables = validate_contract(
    root / "contracts" / "frontend-pages-v1.0-review.md", expected_pages
)
ok("前端四表契约", f"6组件+15页面/布局，共{component_tables + page_tables}张表")

board_path = root / "plan" / "task-board-v1.0.md"
board = texts[board_path]
matches = list(re.finditer(r"^## (T-\d{2})\s+(.+)$", board, re.M))
task_ids = [match.group(1) for match in matches]
expected_tasks = [f"T-{i:02d}" for i in range(1, 39)]
require(task_ids == expected_tasks, f"任务编号/顺序异常: {task_ids}")
graph = {}
for index, match in enumerate(matches):
    task_id = match.group(1)
    end = matches[index + 1].start() if index + 1 < len(matches) else len(board)
    block = board[match.start() : end]
    for field in ("改动", "依赖", "DoD", "验证", "回退", "状态"):
        require(
            re.search(rf"^- {re.escape(field)}[：:]", block, re.M) is not None,
            f"{task_id}缺{field}",
        )
    require(len(re.findall(r"^\s*- \[ \]", block, re.M)) >= 2, f"{task_id} DoD少于2项")
    require("- 状态：未开始" in block, f"{task_id}状态不是未开始")
    dep_match = re.search(r"^- 依赖：(.+)$", block, re.M)
    dep_text = dep_match.group(1).split("可与", 1)[0].split("；", 1)[0] if dep_match else ""
    deps = [] if dep_text.strip().startswith("无") else re.findall(r"T-\d{2}", dep_text)
    for dep in deps:
        require(dep in expected_tasks, f"{task_id}依赖不存在: {dep}")
    graph[task_id] = deps
require("T-12" in graph.get("T-14", []), "T-14缺少T-12调度恢复依赖")

visited = set()
active = set()


def visit(node):
    if node in active:
        errors.append(f"任务依赖存在环: {node}")
        return
    if node in visited:
        return
    active.add(node)
    for dep in graph.get(node, []):
        visit(dep)
    active.remove(node)
    visited.add(node)


for task_id in graph:
    visit(task_id)
ok("任务板", "38个任务字段/DoD/状态/依赖引用及无环检查完成")

matrix = texts[root / "verification" / "traceability-matrix.md"]
r_rows = re.findall(r"^\| (R\d+) \|", matrix, re.M)
require(
    r_rows == [f"R{i}" for i in range(1, 32)],
    f"R1～R31追踪行异常: {r_rows}",
)
ok("追踪矩阵", "R1～R31连续且各一行")

handoff = texts[root / "verification" / "stage1-handoff.md"]
require(handoff.count("**结论：放行。**") == 2, "交接单放行分包数量不是2")
require(handoff.count("**结论：不放行。**") == 1, "交接单不放行分包数量不是1")
for path in page_files:
    require(path.name in handoff, f"交接单未列出页面规格: {path.name}")
ok("交接门禁", "后端/基础设施与T-20/T-21放行，组件/页面不放行")

ui = texts[root / "design" / "ui-tokens.md"]
require(
    "状态：已确认" in ui and "草案" not in ui and "均待确认" not in ui,
    "UI token仍残留草案/待确认状态",
)
ok("UI token状态", "v1.0及扩展项确认状态一致")

for line in checks:
    print(line)
print(
    f"SUMMARY files={len(texts)} json={json_count} links={link_count} "
    f"adrs={len(adr_files)} components={len(component_files)} "
    f"pages={len(page_files)} tasks={len(task_ids)} requirements={len(r_rows)} "
    f"errors={len(errors)}"
)
if errors:
    for error in errors:
        print(f"FAIL {error}")
    sys.exit(1)
print("RESULT PASS 文档结构回归通过；不代表业务实现或最终验收通过")
