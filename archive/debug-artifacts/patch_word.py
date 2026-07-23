import re

NEW_FUNC = '''def _generate_word(report_data: dict) -> bytes:
    """生成 Word 格式报告（参考标准测试卡），返回 docx 字节流。"""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少 python-docx 依赖")

    def add_table(doc, headers, rows):
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr_cells = table.rows[0].cells
        for i, h in enumerate(headers):
            hdr_cells[i].text = str(h)
            for para in hdr_cells[i].paragraphs:
                for run in para.runs:
                    run.font.bold = True
        for row in rows:
            cells = table.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = str(v) if v is not None else ""
        return table

    is_batch = report_data.get("report_type") == "batch"
    doc = Document()

    # 标题
    title = doc.add_heading("EMMC 性能测试与验证报告", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"报告 ID：{report_data['report_id']}", style="Intense Quote").alignment = WD_ALIGN_PARAGRAPH.CENTER

    if is_batch:
        doc.add_paragraph(f"报告类型：批量汇总")
        doc.add_paragraph(f"汇总任务数：{report_data['task_count']}")
    else:
        device = report_data.get("device", {})
        # 1. 基本信息
        doc.add_heading("1. 基本信息", level=1)
        add_table(doc,
                  ["项目", "内容"],
                  [
                      ["任务名称", report_data.get("task_name", "-")],
                      ["设备型号", device.get("model", "-")],
                      ["设备序列号", device.get("serial_number", "-")],
                      ["Android 版本", device.get("android_version", "-")],
                      ["CPU 架构", device.get("cpu_abi", "-")],
                      ["执行人", f"{report_data['executor'].get('username', '-')} ({report_data['executor'].get('role', '-')})"],
                      ["总耗时", report_data.get("total_duration") or "-"],
                      ["生成时间", str(report_data.get("created_at"))],
                  ])

    # 2. 汇总统计
    doc.add_heading("2. 汇总统计", level=1)
    summary = report_data["summary"]
    add_table(doc,
              ["总项数", "通过", "失败", "跳过", "错误", "通过率"],
              [[summary["total_items"], summary["passed"], summary["failed"],
                summary["skipped"], summary["error"], summary["pass_rate"]]])

    if is_batch and report_data.get("module_statistics"):
        doc.add_heading("模块统计", level=1)
        rows = []
        for module, stats in report_data["module_statistics"].items():
            rows.append([module, stats["total"], stats["passed"], stats["failed"], stats["skipped"], stats["error"]])
        add_table(doc, ["模块", "总项数", "通过", "失败", "跳过", "错误"], rows)

    if not is_batch:
        results = report_data["results"]
        extcsd = _extract_extcsd(results)

        # 3. 主要性能参数
        if extcsd:
            doc.add_heading("3. 主要性能参数", level=1)
            card_type = str(extcsd.get("card_type", "N/A")).replace("\\n", "; ")
            add_table(doc,
                      ["参数", "解析结果", "影响"],
                      [
                          ["缓存 Cache Size", extcsd.get("cache_size", "N/A"), "文件读写性能"],
                          ["最大数据包(读取)", extcsd.get("max_packed_reads", "N/A"), "并发读取能力"],
                          ["最大数据包(写入)", extcsd.get("max_packed_writes", "N/A"), "并发写入能力"],
                          ["TRIM Multiplier", extcsd.get("trim_multiplier", "N/A"), "操作效率及寿命"],
                          ["容量", f"{extcsd.get('capacity_gib', 'N/A')} GiB", "实际容量"],
                          ["睡眠电流(VCC/VCCQ)", f"{extcsd.get('sleep_current_vcc', '-')}/{extcsd.get('sleep_current_vccq', '-')}", "休眠功耗"],
                          ["HC WP Group Size", extcsd.get("hc_wp_group_size", "N/A"), "写保护分组尺寸"],
                          ["休眠唤醒超时", extcsd.get("sleep_awake_timeout", "N/A"), "唤醒响应时长"],
                          ["CMDQ 深度", extcsd.get("cmdq_depth", "N/A"), "随机并发提速"],
                          ["驱动强度 Card Type", card_type, "支持下行频率"],
                      ])

        # 4. 基础性能测试（FIO）
        perf_results = _extract_perf_results(results)
        if perf_results:
            doc.add_heading("4. 基础性能测试（FIO）", level=1)
            rows = []
            for p in perf_results:
                rows.append([
                    p["name"], p["status"],
                    p["bw_mbps"] if p["bw_mbps"] is not None else "-",
                    p["iops"] if p["iops"] is not None else "-",
                    p["max_iops"] if p["max_iops"] is not None else "-",
                    p["lat_p999_us"] if p["lat_p999_us"] is not None else "-",
                    p["cpu_total"] if p["cpu_total"] is not None else "-",
                    p["emmc_util"] if p["emmc_util"] is not None else "-",
                ])
            add_table(doc,
                      ["测试项", "状态", "带宽(MB/s)", "IOPS", "MAX IOPS", "P99.9延迟(us)", "CPU(%)", "EMMC利用率(%)"],
                      rows)

        # 5. 稳定性测试
        stability_results = _extract_stability_results(results)
        if stability_results:
            doc.add_heading("5. EMMC 稳定性测试", level=1)
            doc.add_paragraph(
                "测试背景：挂载底层稳定性跑速，高负载队列下输出图表，持续压测运行观察带宽、IOPS 数据下沉情况。",
                style="Intense Quote"
            )
            for s in stability_results:
                doc.add_heading(s["name"], level=2)
                add_table(doc,
                          ["指标", "数值"],
                          [
                              ["状态", s["status"]],
                              ["BW 均值(MB/s)", s["bw_mean"] if s["bw_mean"] is not None else "-"],
                              ["BW 变异系数 CV", f"{s['bw_cv']}%" if s["bw_cv"] is not None else "-"],
                              ["IOPS 均值", s["iops_mean"] if s["iops_mean"] is not None else "-"],
                              ["IOPS 变异系数 CV", f"{s['iops_cv']}%" if s["iops_cv"] is not None else "-"],
                              ["曲线采样点数", s["curve_points"]],
                          ])
                if s["chart_base64"]:
                    try:
                        import base64
                        img_data = s["chart_base64"]
                        if "," in img_data:
                            img_data = img_data.split(",", 1)[1]
                        image_bytes = io.BytesIO(base64.b64decode(img_data))
                        doc.add_paragraph("BW/IOPS 曲线图：")
                        doc.add_picture(image_bytes, width=Inches(5.5))
                    except Exception as e:
                        doc.add_paragraph(f"[图表嵌入失败：{e}]")
                doc.add_paragraph("分析：整体读写速率与 IOPS 利用率浮动情况如上所示。")

        # 6. 可靠性寿命估算
        if extcsd:
            doc.add_heading("6. 可靠性寿命估算", level=1)
            doc.add_paragraph(f"Life Time Type A：{extcsd.get('life_time_type_a', 'N/A')}")
            doc.add_paragraph(f"Life Time Type B：{extcsd.get('life_time_type_b', 'N/A')}")
            doc.add_paragraph(f"PRE EOL Info：{extcsd.get('pre_eol_info', 'N/A')}")
            doc.add_paragraph("请根据以上数据进行综合评估。", style="Intense Quote")

    # 详细结果
    doc.add_heading("详细结果", level=1)
    rows = []
    for r in report_data["results"]:
        rows.append([
            r["module_name"],
            r["item_name"],
            r["status"],
            r["execution_time"] or 0,
            r.get("fail_reason") or "",
        ])
    add_table(doc, ["模块", "测试项", "状态", "耗时(秒)", "失败原因"], rows)

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()
'''

path = "app/api/reports.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

pattern = r"def _generate_word\(report_data: dict\) -> bytes:.*?def _generate_excel"
replacement = NEW_FUNC.strip() + "\n\n\ndef _generate_excel"
new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

if new_content == content:
    print("No replacement made")
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Word report generator replaced")
