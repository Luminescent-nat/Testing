#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 XMind 8 兼容格式的 .xmind 业务流转图。

XMind 8 使用 XML 格式（content.xml + manifest.xml + meta.xml），
兼容性比 XMind Zen 的 JSON 格式更好，可在 XMind 8/2020/2024 中打开。
"""

import os
import uuid
import zipfile
from xml.etree.ElementTree import Element, SubElement, tostring

OUTPUT = "平台业务流转图.xmind"


def _new_id() -> str:
    return uuid.uuid4().hex[:26]


def _build_topic_xml(parent: Element, node: dict):
    """递归构建 topic XML 节点。"""
    topic = SubElement(parent, "topic", {"id": _new_id()})
    title = SubElement(topic, "title")
    title.text = node["title"]

    children = node.get("children", [])
    values = node.get("values", [])
    descriptions = node.get("descriptions", [])

    if values or descriptions or children:
        topics_container = SubElement(topic, "children")
        topics = SubElement(topics_container, "topics", {"type": "attached"})

        for v in values:
            t = SubElement(topics, "topic", {"id": _new_id()})
            SubElement(t, "title").text = f"价值：{v}"

        for d in descriptions:
            t = SubElement(topics, "topic", {"id": _new_id()})
            SubElement(t, "title").text = f"说明：{d}"

        for c in children:
            _build_topic_xml(topics, c)


def node(title, descriptions=None, values=None, children=None):
    n = {"title": title}
    if descriptions:
        n["descriptions"] = descriptions
    if values:
        n["values"] = values
    if children:
        n["children"] = children
    return n


def build_map():
    children = []

    children.append(node("1. 用户接入", descriptions=[
        "注册/登录 → JWT Token → 角色与 PC 标识绑定",
    ], values=[
        "首用户自动成为 admin，降低平台冷启动成本",
        "普通用户按 PC 标识隔离设备，避免跨机误操作",
    ], children=[
        node("admin", descriptions=["管理所有设备、任务、用户、系统配置、知识库"]),
        node("user", descriptions=["仅见本 PC 设备与个人任务/报告"]),
    ]))

    children.append(node("2. 设备接入与画像", descriptions=[
        "ADB 扫描 → 自动建档 → 采集软硬件画像",
        "设备锁保证同一时刻只执行一个任务",
    ], values=[
        "无需手动录入设备，即插即测",
        "自动识别 CPU 架构、Android 版本、模组型号，为后续兼容性匹配提供依据",
    ], children=[
        node("ADB 发现", descriptions=["adb devices -l 扫描，自动创建/更新设备记录"]),
        node("基础画像", descriptions=["型号 / 品牌 / Android 版本 / SDK / CPU 架构 / 分辨率 / 电量"]),
        node("硬件画像", descriptions=["board / hardware / DDR / EMMC / WIFI 芯片 / 蓝牙芯片 / 以太网 / features"]),
        node("状态流转", descriptions=["offline → online → testing → online，WebSocket 实时同步"]),
    ]))

    children.append(node("3. 知识库驱动（平台大脑）", descriptions=[
        "沉淀设备画像、测试规范、判定规则、失败模式、性能基线、执行技能",
        "AI 规划/判定时自动注入相关知识上下文",
    ], values=[
        "测试不再依赖个人经验，新人也能按标准执行",
        "不同设备自动匹配不同基线与策略，实现千人千面",
    ], children=[
        node("资料型知识", descriptions=["文档 / 规范 / 手册：支持 txt/md/pdf/docx/图片上传，自动解析分片"]),
        node("规则型知识", descriptions=["断言规则 / 兼容性规则 / 判定阈值：可直接注入测试项"]),
        node("基线型知识", descriptions=["按设备型号聚合历史性能指标：avg/min/max/sample_count"]),
        node("失败模式", descriptions=["正则匹配失败日志，自动归类原因并给出修复建议"]),
        node("设备画像库", descriptions=["设备指纹 + ARM 版本 + Android 版本 + EMMC/DDR 类型等确定性参数"]),
        node("文档转资产", descriptions=[
            "上传文档 → AI 解析 → 预览确认 → 一键生成测试项/失败模式/基线/规则",
            "分类与标签下拉建议，便于知识组织与检索",
        ]),
    ]))

    children.append(node("4. 测试编排（标准测试卡）", descriptions=[
        "管理员按模块/测试项组织用例，对齐原生测试流程",
        "每个测试项包含：目的、前置条件、步骤、预期结果、判定规则",
    ], values=[
        "用例即资产，可被 AI 和自然语言任务复用",
        "标准测试卡字段让测试报告可直接对外交付",
    ], children=[
        node("测试模块", descriptions=["DDR / EMMC / WIFI / 蓝牙 / 以太网 / CPU / 自定义模块"]),
        node("测试项", descriptions=["执行命令、参数、工具、推送目标、超时、失败策略、兼容性"]),
        node("执行类型", descriptions=["adb_shell / push_exec / host_exec，覆盖设备原生、二进制、PC 端三种场景"]),
        node("判定方式", descriptions=["assertion 规则判定 / rubric 评分 / ai_fallback LLM 兜底"]),
    ]))

    children.append(node("5. 任务创建与 AI 规划", descriptions=[
        "手动选择设备+测试项，或自然语言一句话生成任务",
        "AI 规划时自动查询知识库，注入设备画像和基线",
    ], values=[
        "一句话即可创建复杂测试任务，降低使用门槛",
        "知识库上下文让 AI 规划更贴近设备实际与历史经验",
    ], children=[
        node("手动创建", descriptions=["选设备 → 选模块/测试项 → 配置参数 → POST /tasks"]),
        node("AI 自然语言创建", descriptions=["输入测试意图 → 文本/LLM 解析 → 设备匹配 → 查询测试项 → 自动创建"]),
        node("知识库注入", descriptions=["根据设备型号自动匹配 device_profile / baseline / rule，写入 plan.notes"]),
        node("任务状态", descriptions=["pending → running → completed/failed/cancelled，WebSocket 实时推送"]),
    ]))

    children.append(node("6. 测试执行引擎", descriptions=[
        "TaskExecutor 异步调度，按顺序执行测试项，实时推送进度",
        "执行前做兼容性检查，避免在不支持的设备上浪费时间",
    ], values=[
        "设备占用可控，避免并发冲突",
        "兼容性前置校验，减少无效执行",
    ], children=[
        node("获取设备锁", descriptions=["DeviceLock 保证单设备串行执行"]),
        node("兼容性检查", descriptions=["Android 版本 / CPU 架构 / required_features / board/hardware 匹配"]),
        node("引擎执行", descriptions=["AdbShellEngine / PushExecEngine / HostExecEngine 分别执行"]),
        node("结果保存", descriptions=["output / extracted_data / fail_reason / execution_time 写入 TestRecord"]),
        node("进度推送", descriptions=["WebSocket 实时推送当前项、完成数、进度百分比"]),
    ]))

    children.append(node("7. 结果判定与 AI 辅助", descriptions=[
        "三层判定：规则断言 → Rubrics 评分 → AI 兜底",
        "AI 判定时注入知识库规则/基线/失败模式，提升准确性",
    ], values=[
        "规则明确时自动判定，规则模糊时 AI 兜底，兼顾效率与柔性",
        "每次判定结果反哺知识库，形成正向循环",
    ], children=[
        node("规则断言", descriptions=["conditional_rules：gt/gte/lt/lte/eq/approx_ratio/contains/returncode_zero"]),
        node("Rubric 评分", descriptions=["4 分制评分，>=2 分通过，支持固定阈值或基线阈值"]),
        node("AI 兜底", descriptions=["LLM 读取知识库上下文后返回 status/confidence/metrics/evidence/suggestions"]),
        node("失败模式匹配", descriptions=["自动归类失败日志，给出修复建议"]),
    ]))

    children.append(node("8. 测试报告与洞察", descriptions=[
        "单任务报告 + 批量汇总报告，支持 HTML / Markdown / Word / Excel / JSON",
        "报告中融入知识库洞察与标准测试卡详情",
    ], values=[
        "报告可直接用于项目评审或客户交付",
        "知识库洞察让报告不只是数据，更有判断依据",
    ], children=[
        node("基本信息", descriptions=["任务名称、设备型号、Android 版本、CPU 架构、执行人、耗时"]),
        node("汇总统计", descriptions=["总项数 / 通过 / 失败 / 跳过 / 错误 / 通过率"]),
        node("性能图表", descriptions=["EMMC 性能参数表、FIO 基础性能表、稳定性 BW/IOPS 曲线图"]),
        node("标准测试卡", descriptions=["每项展示：目的、前置条件、步骤、预期结果、实际结果、判定依据、修复建议"]),
        node("知识库洞察", descriptions=["自动关联设备画像、基线、规则、失败模式，给出上下文建议"]),
    ]))

    children.append(node("9. 经验沉淀（闭环）", descriptions=[
        "测试执行结果自动更新基线、黄金案例、失败模式命中次数",
        "人工审核后可将文档/报告结论转入知识库",
    ], values=[
        "平台越用越聪明，历史数据成为下一轮测试的基准",
        "团队经验不再随人员流动而丢失",
    ], children=[
        node("基线更新", descriptions=["同型号同测试项通过时更新 avg/min/max/sample_count"]),
        node("黄金案例", descriptions=["记录标准通过输出，作为后续比对的黄金样本"]),
        node("失败模式计数", descriptions=["失败命中次数 +1，帮助识别高频问题"]),
        node("知识库反哺", descriptions=["新测试自动使用更新后的基线与规则"]),
    ]))

    return node(
        "AI测试自动化平台\n从设备接入到经验沉淀\n——解决多型号/多系统/多模组测试难题，沉淀可复用知识资产",
        children=children
    )


def create_xmind8(path: str, root_node: dict):
    # content.xml
    xmap = Element("xmap-content", {
        "version": "2.0",
        "xmlns": "urn:xmind:xmap:xmlns:content:2.0"
    })
    sheet = SubElement(xmap, "sheet", {"id": _new_id()})
    root_topic = SubElement(sheet, "topic", {"id": _new_id(), "structure-class": "org.xmind.ui.logic.right"})
    SubElement(root_topic, "title").text = root_node["title"]

    topics_container = SubElement(root_topic, "children")
    topics = SubElement(topics_container, "topics", {"type": "attached"})
    for child in root_node["children"]:
        _build_topic_xml(topics, child)

    content_xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(xmap, encoding="utf-8")

    # meta.xml
    meta = Element("meta", {
        "xmlns": "urn:xmind:xmap:xmlns:meta:2.0",
        "version": "2.0"
    })
    creator = SubElement(meta, "Creator")
    SubElement(creator, "Name").text = "AI测试平台"
    meta_xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(meta, encoding="utf-8")

    # manifest.xml
    manifest = Element("manifest", {"xmlns": "urn:xmind:xmap:xmlns:manifest:1.0"})
    SubElement(manifest, "file-entry", {"full-path": "content.xml", "media-type": "text/xml"})
    SubElement(manifest, "file-entry", {"full-path": "meta.xml", "media-type": "text/xml"})
    manifest_xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(manifest, encoding="utf-8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.xml", content_xml)
        zf.writestr("meta.xml", meta_xml)
        zf.writestr("manifest.xml", manifest_xml)


if __name__ == "__main__":
    root = build_map()
    create_xmind8(OUTPUT, root)
    print(f"已生成：{os.path.abspath(OUTPUT)}")
