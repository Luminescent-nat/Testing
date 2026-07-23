#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 AI 测试自动化平台业务流程 XMind 思维导图（现代 XMind Zen 格式）。"""

import json
import os
import uuid
import zipfile

OUTPUT = "AI测试自动化平台业务流程.xmind"


def _new_id():
    """生成 XMind Zen 风格 26 位十六进制 ID。"""
    return uuid.uuid4().hex[:26]


def _build_topic(input_topic: dict) -> dict:
    """递归构建单个 topic JSON。"""
    topic = {
        "id": _new_id(),
        "class": "topic",
        "title": input_topic["title"],
    }

    notes = input_topic.get("notes")
    if notes:
        topic["notes"] = {"plain": {"content": notes}}

    children = input_topic.get("children")
    if children:
        topic["children"] = {
            "attached": [_build_topic(c) for c in children]
        }

    return topic


def create_xmind_zen(path: str, sheets: list):
    """生成现代 XMind Zen 格式的 .xmind 文件。"""
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


def add_topic(parent, title, notes=""):
    """在父主题下添加子主题，并可选设置备注。"""
    topic = {"title": title}
    if notes:
        topic["notes"] = notes
    if "children" not in parent:
        parent["children"] = []
    parent["children"].append(topic)
    return topic


def build_map():
    root = {"title": "AI测试自动化平台业务流程"}

    # 1. 平台概述与目标
    n1 = add_topic(root, "1. 平台概述与目标")
    add_topic(n1, "项目背景", "面向 Android 硬件板卡（rk3568 / A133P 等）的自动化测试平台；支持 WIFI、蓝牙、以太网、EMMC、DDR、CPU 等通用基础用例。")
    add_topic(n1, "核心目标", "适配不同 Android 版本、CPU 架构、DDR/EMMC/WIFI/蓝牙模组；自然语言创建任务；自动判定；沉淀测试经验；生成可导出报告。")
    n1_tech = add_topic(n1, "技术栈")
    add_topic(n1_tech, "前端", "Vue 3 + Element Plus + Pinia + ECharts")
    add_topic(n1_tech, "后端", "FastAPI + SQLAlchemy 2.0 + Pydantic v2 + SQLite")
    add_topic(n1_tech, "ADB", "系统 adb 命令，需提前加入 PATH")
    add_topic(n1_tech, "实时推送", "WebSocket")
    add_topic(n1_tech, "报告", "openpyxl / python-docx / jinja2")
    n1_dep = add_topic(n1, "部署形态")
    add_topic(n1_dep, "开发环境", "后端 python run_server.py（端口 8000）；前端 npm run dev（默认 3000）")
    add_topic(n1_dep, "生产建议", "SQLite → PostgreSQL；asyncio → Celery+Redis；Nginx 反向代理；日志轮转")

    # 2. 用户与权限
    n2 = add_topic(root, "2. 用户与权限")
    add_topic(n2, "注册", "用户名 3-20 字符、密码 6-32 字符；bcrypt 加密；记录 PC 标识（IP + MAC）；首个注册用户为 admin（文档说明，当前实现默认 user）")
    add_topic(n2, "登录", "用户名密码校验 → JWT Token（有效期 24h，Bearer）→ 更新最后登录时间与 PC 标识")
    n2_role = add_topic(n2, "角色体系")
    add_topic(n2_role, "admin", "查看所有设备 / 所有任务 / 用户管理 / 系统配置")
    add_topic(n2_role, "user", "仅查看本 PC 标识设备 / 个人任务 / 个人报告")
    add_topic(n2, "用户管理", "列表查询 / 禁用启用 / 删除 / 改角色 / 重置密码 / 个人信息查看 / 密码修改")

    # 3. 设备管理
    n3 = add_topic(root, "3. 设备管理")
    add_topic(n3, "设备发现", "POST /devices/refresh 调用 adb devices -l 扫描；自动创建或更新设备记录")
    n3_info = add_topic(n3, "信息采集")
    add_topic(n3_info, "基础信息", "serial_number / model / brand / android_version / sdk_version / cpu_abi / resolution / battery_level")
    add_topic(n3_info, "硬件画像", "board / hardware / ddr_info / emmc_info / wifi_chip / bt_chip / eth_interfaces / features")
    n3_state = add_topic(n3, "状态流转")
    add_topic(n3_state, "offline", "未连接或断开")
    add_topic(n3_state, "online", "已连接且空闲")
    add_topic(n3_state, "testing", "正在执行测试任务")
    add_topic(n3_state, "busy", "被其他用户占用（admin 视角）")
    add_topic(n3, "权限隔离", "普通用户仅可见 pc_identifier 匹配的本机设备；管理员可见全部设备")
    add_topic(n3, "设备锁", "DeviceLock 内存锁：同一设备同一时间只能执行一个任务，任务结束后释放")

    # 4. 测试资源管理
    n4 = add_topic(root, "4. 测试资源管理（工具/脚本）")
    n4_dir = add_topic(n4, "目录规范")
    add_topic(n4_dir, "test-tools/<module>/binaries/<arch>/", "按模块、按 CPU 架构存放二进制；当前支持 arm64-v8a / armeabi-v7a")
    add_topic(n4_dir, "test-tools/<module>/host/", "PC 端运行器 / 报告脚本")
    add_topic(n4_dir, "test-tools/common/", "通用基础设施：adb_runner.py / device_info.py / logger.py")
    add_topic(n4, "工具上传", "二进制文件 + 元数据（name/version/architecture/file_size/md5/file_path）；按架构分类存储")
    add_topic(n4, "脚本管理", "支持 Python / Bat / Shell；在线编辑；parameters_schema")
    n4_tools = add_topic(n4, "当前已集成工具")
    add_topic(n4_tools, "DDR", "memtester / stress-ng / stressapptest（armeabi-v7a）")
    add_topic(n4_tools, "EMMC", "fio / mmc_utils（arm64-v8a + armeabi-v7a）")
    add_topic(n4, "新增工具流程", "1) 放入目录；2) 编写 host 脚本；3) 更新 seed_data.py；4) 删除旧数据库或更新 test_items；5) 重启后端")

    # 5. 测试编排
    n5 = add_topic(root, "5. 测试编排（模块/测试项）")
    n5_mod = add_topic(n5, "测试模块")
    add_topic(n5_mod, "预置模块", "DDR / EMMC / WIFI / 蓝牙 / 以太网 / CPU")
    add_topic(n5_mod, "模块属性", "name / category / description / icon / sort_order / enabled")
    n5_item = add_topic(n5, "测试项配置")
    add_topic(n5_item, "执行类型", "adb_shell：直接执行设备原生命令\npush_exec：推送二进制到设备后执行\nhost_exec：PC 端执行脚本/命令")
    add_topic(n5_item, "执行命令与参数", "exec_command + parameters；ParameterRenderer 渲染占位符；支持 {serial} / {tool} / device 画像字段")
    add_topic(n5_item, "工具与推送", "tool_id + push_target（默认 /data/local/tmp）")
    n5_compat = add_topic(n5_item, "兼容性配置")
    add_topic(n5_compat, "系统版本", "min_android_version / max_android_version")
    add_topic(n5_compat, "CPU 架构", "supported_archs")
    add_topic(n5_compat, "能力特征", "required_features")
    add_topic(n5_compat, "主板/硬件", "board_patterns / hardware_patterns")
    n5_judge = add_topic(n5_item, "判定方式")
    add_topic(n5_judge, "assertion", "条件规则（conditional_rules）：source/operator/target/tolerance/on_fail；returncode_zero")
    add_topic(n5_judge, "rubric", "rubric_criteria：固定阈值或基线阈值，4 分制，>=2 为 pass")
    add_topic(n5_judge, "ai_fallback", "LLM 兜底判定（需配置 API Key），未配置时降级规则")
    add_topic(n5_item, "结果解析", "pass_pattern / fail_pattern / extract_pattern / timeout")
    add_topic(n5_item, "失败策略", "on_failure：continue（继续）/ stop（停止）；retry_count")
    add_topic(n5_item, "标签", "functional / performance / stability / stress / aging / all")
    add_topic(n5, "管理操作", "创建 / 编辑 / 删除 / 复制 / 排序 / 启用禁用 / 参数模板")

    # 6. 测试任务创建
    n6 = add_topic(root, "6. 测试任务创建")
    n6_manual = add_topic(n6, "手动创建")
    add_topic(n6_manual, "选择测试项", "多选测试项或整模块")
    add_topic(n6_manual, "选择设备", "目标 ADB 设备；校验 online/testing/offline")
    add_topic(n6_manual, "自定义参数", "任务级别为每个测试项覆盖参数")
    add_topic(n6_manual, "创建任务", "POST /tasks；状态 pending")
    n6_ai = add_topic(n6, "AI 自然语言创建")
    add_topic(n6_ai, "接口", "POST /ai/tasks/natural，请求 {\"text\": \"...\"}")
    n6_ai_flow = add_topic(n6_ai, "处理流程")
    add_topic(n6_ai_flow, "1) 文本解析", "规则匹配模块关键词 + 测试类型关键词")
    add_topic(n6_ai_flow, "2) 设备匹配", "优先真实本机设备；按 model/serial/board/brand 匹配；单一设备默认选中；无匹配回退示例设备")
    add_topic(n6_ai_flow, "3) LLM 辅助", "规则无法识别时调用 LLM（需 API Key）返回结构化 JSON")
    add_topic(n6_ai_flow, "4) 查询测试项", "按模块 + tags 过滤 enabled 测试项")
    add_topic(n6_ai_flow, "5) 创建并启动", "插入 TestTask → 设备状态 testing → TaskExecutor.start_task")
    add_topic(n6, "任务状态", "pending → running → completed / failed / cancelled")

    # 7. 测试执行引擎
    n7 = add_topic(root, "7. 测试执行引擎")
    n7_flow = add_topic(n7, "执行流程")
    add_topic(n7_flow, "1) 加载任务与设备", "通过 task_id 加载；设备不存在则任务 failed")
    add_topic(n7_flow, "2) 获取设备锁", "失败则任务 failed")
    add_topic(n7_flow, "3) 状态初始化", "task status=running / started_at / progress=0；WebSocket 推送")
    add_topic(n7_flow, "4) 循环测试项", "创建 TestRecord running → 兼容性检查 → 执行 → 保存结果 → 更新进度 → 推送进度")
    add_topic(n7_flow, "5) 失败停止判断", "on_failure=stop 时中断")
    add_topic(n7_flow, "6) 任务收尾", "status=completed；progress=100；释放锁；设备 online")
    add_topic(n7_flow, "7) 异常处理", "取消 → cancelled；异常 → failed；记录 error_message")
    n7_engine = add_topic(n7, "执行引擎实现")
    add_topic(n7_engine, "AdbShellEngine", "直接 adb shell 执行命令；渲染参数；超时控制；输出+返回码判定")
    add_topic(n7_engine, "PushExecEngine", "查询 TestTool → push_file → chmod +x → 渲染命令 → 执行 → 输出+返回码判定")
    add_topic(n7_engine, "HostExecEngine", "PC 端 create_subprocess_shell 执行；提取独立 JSON 块合并到 extracted_data")
    add_topic(n7, "EngineFactory", "根据 exec_type 返回对应引擎；支持注册新引擎")
    add_topic(n7, "并发控制", "asyncio.create_task 后台执行；DeviceLock 内存锁；同一设备串行")

    # 8. 结果判定
    n8 = add_topic(root, "8. 结果判定")
    add_topic(n8, "ADB 设备级失败识别", "device not found / device offline / no devices / permission denied / no such file → 直接 fail")
    n8_layer = add_topic(n8, "三层判定机制")
    add_topic(n8_layer, "1) 规则断言", "conditional_rules：source(regex:) / target(spec:或固定值) / operator(gt/gte/lt/lte/eq/approx_ratio/contains) / tolerance")
    add_topic(n8_layer, "2) Rubrics 评分", "criteria：extract_pattern + levels；支持 source=fixed 或 baseline；4 分制；>=2 pass")
    add_topic(n8_layer, "3) AI 兜底", "调用 LLM 返回 JSON 判定（confidence/metrics/evidence/suggestions）；未配置 Key 时降级")
    add_topic(n8, "数据提取", "正则提取 values；host_exec 提取 JSON 对象；合并到 extracted_data")
    add_topic(n8, "判定结果", "status: pass / fail / skip / error / unknown；fail_reason / metrics / evidence")

    # 9. 记忆体沉淀（知识库）
    n9 = add_topic(root, "9. 记忆体沉淀（知识库）")
    n9_fp = add_topic(n9, "失败模式库")
    add_topic(n9_fp, "默认模式", "ADB 设备未找到 / ADB 离线 / 命令超时 / 权限不足 / 二进制缺失 / 兼容性不满足")
    add_topic(n9_fp, "匹配逻辑", "任务完成后对 fail/error 记录用正则匹配；命中后 occurrence_count+1")
    n9_base = add_topic(n9, "统计基线")
    add_topic(n9_base, "更新时机", "pass 记录且 extracted_data 含数值指标时更新")
    add_topic(n9_base, "聚合维度", "device_model + item_id + metric_name → avg / min / max / sample_count")
    add_topic(n9_base, "应用", "Rubric baseline 判定；AI 上下文")
    n9_golden = add_topic(n9, "黄金案例")
    add_topic(n9_golden, "更新时机", "pass 记录沉淀")
    add_topic(n9_golden, "内容", "item_id + device_model + expected_status=pass + sample_output（最近 1000 字符）+ pass/total 计数")
    add_topic(n9, "沉淀触发", "任务完成后统一遍历 TestRecords 执行 match/update")

    # 10. 报告管理
    n10 = add_topic(root, "10. 报告管理")
    n10_api = add_topic(n10, "接口")
    add_topic(n10_api, "单任务报告", "GET /reports/{task_id}")
    add_topic(n10_api, "单任务导出", "GET /reports/{task_id}/export?format=html|markdown|excel|word|json")
    add_topic(n10_api, "批量导出", "GET /reports/batch/export?task_ids=1,2,3&format=...")
    add_topic(n10_api, "全部总报告", "GET /reports/summary/all")
    n10_content = add_topic(n10, "报告内容（标准测试卡）")
    add_topic(n10_content, "1) 基本信息", "任务名称 / 设备型号 / 序列号 / Android 版本 / CPU 架构 / 执行人 / 总耗时 / 生成时间")
    add_topic(n10_content, "2) 汇总统计", "总项数 / 通过 / 失败 / 跳过 / 错误 / 通过率")
    add_topic(n10_content, "3) 主要性能参数", "EXT_CSD：Cache Size / max_packed_reads/writes / TRIM / 容量 / sleep current / CMDQ / Card Type")
    add_topic(n10_content, "4) FIO 基础性能", "测试项 / 状态 / 带宽(MB/s) / IOPS / MAX IOPS / P99.9 延迟 / CPU / EMMC 利用率")
    add_topic(n10_content, "5) 稳定性测试", "BW/IOPS 均值、变异系数 CV、曲线采样点数、BW/IOPS 曲线图（base64 嵌入）")
    add_topic(n10_content, "6) 可靠性寿命", "Life Time Type A / Type B / PRE EOL Info")
    add_topic(n10_content, "7) 详细结果", "模块 / 测试项 / 状态 / 耗时 / 失败原因")
    n10_format = add_topic(n10, "导出格式")
    add_topic(n10_format, "HTML", "浏览器查看，含样式与图表")
    add_topic(n10_format, "Markdown", "文档集成，Data URL 图片")
    add_topic(n10_format, "Word", "正式交付，嵌入图表 PNG")
    add_topic(n10_format, "Excel", "表格分析")
    add_topic(n10_format, "JSON", "程序化处理")

    # 11. 前端页面
    n11 = add_topic(root, "11. 前端页面")
    add_topic(n11, "登录/注册", "亮色/暗色主题切换；JWT 登录；密码可见切换")
    add_topic(n11, "仪表盘", "统计概览")
    add_topic(n11, "设备管理", "刷新 ADB / 设备列表 / 状态 / 开始测试")
    add_topic(n11, "测试模块/测试项", "模块列表 / 测试项 CRUD / 参数配置")
    add_topic(n11, "测试任务", "任务列表 / 创建 / 进度 / 日志 / 取消")
    add_topic(n11, "测试报告", "报告卡片 / 详情弹窗 / 单条导出 / 批量导出")
    add_topic(n11, "用户管理", "仅 admin：用户列表 / 角色 / 状态")
    add_topic(n11, "主题切换", "light / dark，CSS 变量驱动")

    # 12. 开发任务流程
    n12 = add_topic(root, "12. 开发任务流程")
    n12_stage = add_topic(n12, "阶段")
    add_topic(n12_stage, "1) 需求澄清", "功能点 / 非功能点 / 验收标准 / 优先级；禁止虚构数据")
    add_topic(n12_stage, "2) 设计评审", "接口 / 数据库 / 前端交互 / 工具目录规划")
    add_topic(n12_stage, "3) 开发自测", "最小化改动；新增工具带 --help；配置集中；删除历史脚本而非注释")
    add_topic(n12_stage, "4) 测试验证", "后端 pytest（单元/集成/WebSocket/e2e）；前端 npm run build；curl/Postman；真实设备 E2E")
    add_topic(n12_stage, "5) 部署上线", "nohup / 服务化；访问 /health；保留日志")
    add_topic(n12_stage, "6) 验收归档", "对照需求确认；更新文档；删除临时文件与虚构数据")
    n12_doc = add_topic(n12, "文档规范")
    add_topic(n12_doc, "根目录", "PROJECT_DOCUMENTATION.md / DEVELOPMENT_WORKFLOW.md / 测试平台开发需求文档.md")
    add_topic(n12_doc, "后端", "backend/README.md")
    add_topic(n12_doc, "前端", "frontend/README.md")
    add_topic(n12_doc, "工具目录", "test-tools/README.md 及各模块 README")
    n12_code = add_topic(n12, "代码规范")
    add_topic(n12_code, "后端", "FastAPI + SQLAlchemy 2.0 + Pydantic v2；路由在 app/api/；业务在 app/services/；模型在 app/models/")
    add_topic(n12_code, "前端", "Vue 3 + Element Plus + Pinia；API 按模块拆分；页面在 src/views/<module>/index.vue")

    return [{"title": "业务流程", "rootTopic": root}]


def main():
    sheets = build_map()
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)
    create_xmind_zen(OUTPUT, sheets)
    abs_path = os.path.abspath(OUTPUT)
    print(f"已生成思维导图：{abs_path}")
    print(f"文件大小：{os.path.getsize(OUTPUT)} 字节")


if __name__ == "__main__":
    main()
