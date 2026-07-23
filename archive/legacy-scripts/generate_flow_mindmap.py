#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 AI 测试自动化平台【业务流转流程图】思维导图（XMind Zen 格式）。

设计要点：
- 以"业务流转"为中心，按时间顺序展开主线；
- 每个节点的说明直接作为可见子主题（不会收起到备注里）；
- 新增"基线知识库"主线，包含设备指纹、ARM 版本、Android 版本、EMMC/DDR 类型等基础参数。
"""

import json
import os
import uuid
import zipfile

OUTPUT = "AI测试自动化平台业务流转图.xmind"


def _new_id() -> str:
    return uuid.uuid4().hex[:26]


def _build_topic(input_topic: dict) -> dict:
    topic = {
        "id": _new_id(),
        "class": "topic",
        "title": input_topic["title"],
    }
    if input_topic.get("structureClass"):
        topic["structureClass"] = input_topic["structureClass"]

    # 说明作为可见子主题，不放入 notes（notes 在 XMind 里默认收起）
    children = []
    for desc in input_topic.get("descriptions", []):
        children.append({"id": _new_id(), "class": "topic", "title": f"说明：{desc}"})

    if input_topic.get("children"):
        for c in input_topic["children"]:
            children.append(_build_topic(c))

    if children:
        topic["children"] = {"attached": children}

    return topic


def create_xmind_zen(path: str, sheets: list):
    built_sheets = []
    for sheet in sheets:
        built_sheets.append({
            "id": _new_id(),
            "class": "sheet",
            "title": sheet["title"],
            "rootTopic": _build_topic(sheet["rootTopic"]),
            "topicOverlapping": "overlap",
            "theme": {},
        })

    content = json.dumps(built_sheets, ensure_ascii=False, indent=2)
    metadata = json.dumps({
        "dataStructureVersion": "3",
        "creator": {"name": "xmind-skill", "version": "1.0.0"},
        "layoutEngineVersion": "5",
    }, ensure_ascii=False, indent=2)
    manifest = json.dumps({
        "file-entries": {
            "content.json": {},
            "metadata.json": {},
        }
    }, ensure_ascii=False, indent=2)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", content)
        zf.writestr("metadata.json", metadata)
        zf.writestr("manifest.json", manifest)


def node(title, descriptions=None, children=None, structure_class=None):
    """辅助构造节点。"""
    n = {"title": title}
    if descriptions:
        n["descriptions"] = descriptions
    if children:
        n["children"] = children
    if structure_class:
        n["structureClass"] = structure_class
    return n


def build_flow_map():
    # 业务主线，按时间顺序排列
    phases = [
        node("1. 用户接入与认证", descriptions=[
            "用户通过用户名/密码注册或登录，后端返回 JWT Token（有效期 24h）。",
            "首次注册时记录 PC 标识（IP + MAC），用于后续设备权限隔离。",
        ], children=[
            node("注册", descriptions=["用户名 3-20 字符，密码 bcrypt 加密，记录 PC 标识。"]),
            node("登录", descriptions=["校验密码 → 生成 Bearer Token → 更新最后登录时间。"]),
            node("权限隔离", descriptions=[
                "admin：查看所有设备、所有任务、用户管理、系统配置。",
                "user：只能看到本 PC 设备和个人任务/报告。",
            ]),
        ]),

        node("2. 设备接入与画像", descriptions=[
            '前端点击"刷新设备"，后端调用 adb devices -l 扫描 ADB 设备。',
            "新设备自动创建记录，已存在设备更新最后在线时间和状态。",
        ], children=[
            node("ADB 扫描", descriptions=["adb devices -l 获取序列号列表；逐个采集详细信息。"]),
            node("基础信息", descriptions=[
                "型号、品牌、Android 版本、SDK、CPU 架构、分辨率、电量。",
            ]),
            node("硬件画像", descriptions=[
                "主板平台(board)、硬件名称(hardware)、DDR 信息、EMMC 信息。",
                "WIFI 芯片、蓝牙芯片、以太网接口、能力特征(features)。",
            ]),
            node("设备状态", descriptions=[
                "offline → online → testing → online。",
                "DeviceLock 保证同一设备同时只执行一个任务。",
            ]),
        ]),

        node("3. 基线知识库初始化", descriptions=[
            "设备首次接入后，把确定性基础参数写入基线知识库，为兼容性判断和测试策略匹配提供依据。",
            "随着测试执行，基线库还会不断补充性能指标、失败模式、黄金案例。",
        ], children=[
            node("设备指纹", descriptions=[
                "由 model + serial_number + board + hardware 组合形成的唯一设备标识。",
                "用于关联历史记录、基线、黄金案例。",
            ]),
            node("ARM 版本", descriptions=[
                "arm64-v8a / armeabi-v7a。",
                "决定推送哪个架构的二进制工具（fio、mmc_utils 等）。",
            ]),
            node("Android 版本", descriptions=[
                "用于 min_android_version / max_android_version 兼容性校验。",
                "不同 Android 版本的命令和节点路径可能不同。",
            ]),
            node("EMMC 类型", descriptions=[
                "容量、型号、健康状态、EXT_CSD 参数（Cache Size、CMDQ、TRIM 等）。",
                "用于判断存储性能基线和可靠性寿命。",
            ]),
            node("DDR 类型", descriptions=[
                "容量、频率、通道数等 DDR 信息。",
                "用于内存类测试的参数匹配和结果分析。",
            ]),
            node("其他模组", descriptions=[
                "WIFI 芯片型号、蓝牙芯片型号、以太网接口列表。",
                "决定网络类测试项是否可用。",
            ]),
            node("能力特征", descriptions=[
                "如 wifi、bt、eth、root、camera 等能力标签。",
                "测试项兼容性检查 required_features 时使用。",
            ]),
        ]),

        node("4. 测试编排", descriptions=[
            "管理员预先配置测试模块和测试项，定义命令、参数、兼容性、判定规则。",
            "编排结果作为后续手动任务和 AI 任务的模板库。",
        ], children=[
            node("测试模块", descriptions=["DDR / EMMC / WIFI / 蓝牙 / 以太网 / CPU 等分类。"]),
            node("测试项", descriptions=[
                "执行命令、参数 schema、工具、推送目标、超时、失败策略。",
            ]),
            node("执行类型", descriptions=[
                "adb_shell：直接执行设备原生命令。",
                "push_exec：推送二进制到设备后执行。",
                "host_exec：PC 端脚本调度执行。",
            ]),
            node("兼容性", descriptions=[
                "Android 版本范围、支持的 CPU 架构、required_features、board/hardware 匹配。",
            ]),
            node("判定方式", descriptions=[
                "assertion：条件规则判定。",
                "rubric：按阈值评分（4 分制）。",
                "ai_fallback：LLM 兜底判定。",
            ]),
        ]),

        node("5. 任务创建", descriptions=[
            "用户选择设备 + 测试项后创建任务；也支持自然语言一句话创建。",
            "创建后设备状态变为 testing，任务进入 pending/running。",
        ], children=[
            node("手动创建", descriptions=[
                "选设备 → 选模块/测试项 → 配置自定义参数 → POST /tasks。",
            ]),
            node("AI 自然语言创建", descriptions=[
                'POST /ai/tasks/natural，输入如"对 rk3568 做 EMMC 稳定性测试"。',
                "文本解析 → 设备匹配 → LLM 辅助 → 查询测试项 → 自动创建并启动。",
            ]),
            node("任务状态", descriptions=[
                "pending → running → completed / failed / cancelled。",
                "WebSocket 实时推送进度。",
            ]),
        ]),

        node("6. 任务执行引擎", descriptions=[
            "TaskExecutor 在后台异步执行测试项，按顺序占用设备、执行、保存结果。",
            "执行过程中通过 WebSocket 向前端推送进度。",
        ], children=[
            node("获取设备锁", descriptions=["DeviceLock 保证同一设备串行，避免多任务冲突。"]),
            node("循环执行", descriptions=[
                "加载测试项 → 兼容性检查 → 工具推送 → 执行命令 → 结果保存。",
            ]),
            node("执行引擎", descriptions=[
                "AdbShellEngine：直接 adb shell。",
                "PushExecEngine：推送 + chmod + 执行。",
                "HostExecEngine：PC 端执行并提取 JSON。",
            ]),
            node("失败处理", descriptions=[
                "on_failure=continue 继续下一项；on_failure=stop 中断任务。",
                "超时、取消、异常分别记录为 error / cancelled / failed。",
            ]),
        ]),

        node("7. 结果判定", descriptions=[
            "每个测试项执行后，输出进入判定引擎，输出 pass/fail/skip/error。",
            "判定优先识别 ADB 设备级故障，再按规则/Rubrics/AI 顺序执行。",
        ], children=[
            node("ADB 故障识别", descriptions=[
                "device offline / not found / permission denied / no such file → 直接 fail。",
            ]),
            node("规则断言", descriptions=[
                "从输出中提取数值/文本，与期望值按 operator 比较。",
            ]),
            node("Rubrics 评分", descriptions=[
                "按固定阈值或历史基线评分，最终得分 ≥2 判 pass。",
            ]),
            node("AI 兜底", descriptions=[
                "规则无法判定时调用 LLM，输出 confidence/metrics/evidence。",
                "未配置 API Key 时降级为规则判定。",
            ]),
        ]),

        node("8. 知识沉淀", descriptions=[
            "任务完成后，系统把结果反向写入知识库，用于后续判定和排错。",
            "沉淀内容包括失败模式、统计基线、黄金案例。",
        ], children=[
            node("失败模式库", descriptions=[
                "对 fail/error 记录正则匹配，归类为 ADB/超时/权限/兼容性等问题。",
            ]),
            node("统计基线", descriptions=[
                "按 device_model + item_id + metric_name 聚合 avg/min/max/sample_count。",
            ]),
            node("黄金案例", descriptions=[
                "通过的记录沉淀为标准输出样本，供后续对比和 AI 上下文使用。",
            ]),
        ]),

        node("9. 报告输出", descriptions=[
            "测试完成后自动生成报告，支持单任务、批量、全部任务汇总。",
            "报告按标准测试卡格式组织，包含图表和可靠性估算。",
        ], children=[
            node("单任务报告", descriptions=[
                "基本信息 / 汇总统计 / EXT_CSD / FIO 性能 / 稳定性曲线 / 可靠性 / 详细结果。",
            ]),
            node("批量/总报告", descriptions=["多任务聚合，输出模块统计和汇总表格。"]),
            node("导出格式", descriptions=[
                "HTML（浏览器查看）、Markdown（文档集成）、Word（正式交付）、Excel（数据分析）、JSON（程序处理）。",
            ]),
        ]),

        node("10. 前端使用", descriptions=[
            "用户通过 Web 界面完成登录、设备管理、任务创建、进度查看、报告导出。",
            "支持亮色/暗色主题切换。",
        ], children=[
            node("核心页面", descriptions=[
                "登录注册 / 仪表盘 / 设备管理 / 测试模块与测试项 / 测试任务 / 测试报告 / 用户管理。",
            ]),
            node("实时反馈", descriptions=["WebSocket 推送任务进度和状态变更。"]),
            node("主题切换", descriptions=["light / dark 两套主题，CSS 变量驱动。"]),
        ]),
    ]

    root = node(
        "AI测试自动化平台业务流转\n从用户/设备接入 → 基线知识库 → 测试编排 → 任务创建 → 执行 → 判定 → 沉淀 → 报告输出",
        children=phases,
        structure_class="org.xmind.ui.logic.right",
    )

    return [{"title": "业务流转图", "rootTopic": root}]


def main():
    sheets = build_flow_map()
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)
    create_xmind_zen(OUTPUT, sheets)
    abs_path = os.path.abspath(OUTPUT)
    print(f"已生成思维导图：{abs_path}")
    print(f"文件大小：{os.path.getsize(OUTPUT)} 字节")


if __name__ == "__main__":
    main()
