import re

with open('app/api/reports.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_html = r'''def _generate_html(report_data: dict) -> str:
    """生成 HTML 格式报告（参考标准测试卡）。"""
    is_batch = report_data.get("report_type") == "batch"
    device = report_data.get("device", {})
    summary = report_data["summary"]
    results = report_data["results"]

    summary_html = f"""
    <table>
        <tr><th>总项数</th><th>通过</th><th>失败</th><th>跳过</th><th>错误</th><th>通过率</th></tr>
        <tr>
            <td>{summary['total_items']}</td>
            <td>{summary['passed']}</td>
            <td>{summary['failed']}</td>
            <td>{summary['skipped']}</td>
            <td>{summary['error']}</td>
            <td>{summary['pass_rate']}</td>
        </tr>
    </table>
    """

    device_html = ""
    if not is_batch:
        device_html = f"""
        <h2>1. 基本信息</h2>
        <table>
            <tr><th>项目</th><th>内容</th></tr>
            <tr><td>任务名称</td><td>{report_data.get('task_name', '-')}</td></tr>
            <tr><td>设备型号</td><td>{device.get('model', '-')}</td></tr>
            <tr><td>设备序列号</td><td>{device.get('serial_number', '-')}</td></tr>
            <tr><td>Android 版本</td><td>{device.get('android_version', '-')}</td></tr>
            <tr><td>CPU 架构</td><td>{device.get('cpu_abi', '-')}</td></tr>
            <tr><td>执行人</td><td>{report_data['executor'].get('username', '-')} ({report_data['executor'].get('role', '-')})</td></tr>
            <tr><td>总耗时</td><td>{report_data.get('total_duration') or '-'}</td></tr>
            <tr><td>生成时间</td><td>{report_data.get('created_at')}</td></tr>
        </table>
        """

    extcsd = _extract_extcsd(results)
    extcsd_html = ""
    if extcsd and not is_batch:
        card_type = str(extcsd.get('card_type', 'N/A')).replace('\n', '<br>')
        extcsd_html = f"""
        <h2>2. 主要性能参数</h2>
        <table>
            <tr><th>参数</th><th>解析结果</th><th>影响</th></tr>
            <tr><td>缓存 Cache Size</td><td>{extcsd.get('cache_size', 'N/A')}</td><td>文件读写性能</td></tr>
            <tr><td>最大数据包(读取)</td><td>{extcsd.get('max_packed_reads', 'N/A')}</td><td>并发读取能力</td></tr>
            <tr><td>最大数据包(写入)</td><td>{extcsd.get('max_packed_writes', 'N/A')}</td><td>并发写入能力</td></tr>
            <tr><td>TRIM Multiplier</td><td>{extcsd.get('trim_multiplier', 'N/A')}</td><td>操作效率及寿命</td></tr>
            <tr><td>容量</td><td>{extcsd.get('capacity_gib', 'N/A')} GiB</td><td>实际容量</td></tr>
            <tr><td>睡眠电流(VCC/VCCQ)</td><td>{extcsd.get('sleep_current_vcc', '-')}/{extcsd.get('sleep_current_vccq', '-')}</td><td>休眠功耗</td></tr>
            <tr><td>HC WP Group Size</td><td>{extcsd.get('hc_wp_group_size', 'N/A')}</td><td>写保护分组尺寸</td></tr>
            <tr><td>休眠唤醒超时</td><td>{extcsd.get('sleep_awake_timeout', 'N/A')}</td><td>唤醒响应时长</td></tr>
            <tr><td>CMDQ 深度</td><td>{extcsd.get('cmdq_depth', 'N/A')}</td><td>随机并发提速</td></tr>
            <tr><td>驱动强度 Card Type</td><td>{card_type}</td><td>支持下行频率</td></tr>
        </table>
        """

    perf_results = _extract_perf_results(results)
    perf_html = ""
    if perf_results and not is_batch:
        rows = ""
        for p in perf_results:
            rows += f"""
            <tr>
                <td>{p['name']}</td>
                <td class="{p['status']}">{p['status']}</td>
                <td>{p['bw_mbps'] or '-'}</td>
                <td>{p['iops'] or '-'}</td>
                <td>{p['max_iops'] or '-'}</td>
                <td>{p['lat_p999_us'] or '-'}</td>
                <td>{p['cpu_total'] or '-'}</td>
                <td>{p['emmc_util'] or '-'}</td>
            </tr>
            """
        perf_html = f"""
        <h2>3. 基础性能测试（FIO）</h2>
        <table>
            <tr>
                <th>测试项</th><th>状态</th><th>带宽(MB/s)</th><th>IOPS</th>
                <th>MAX IOPS</th><th>P99.9延迟(us)</th><th>CPU(%)</th><th>EMMC利用率(%)</th>
            </tr>
            {rows}
        </table>
        """

    stability_results = _extract_stability_results(results)
    stability_html = ""
    if stability_results and not is_batch:
        sections = ""
        for s in stability_results:
            img_html = f'<img src="{s["chart_base64"]}" style="max-width:100%; border:1px solid #ddd;">' if s['chart_base64'] else '<p>无图表</p>'
            sections += f"""
            <div class="stability-section">
                <h3>{s['name']}</h3>
                <table>
                    <tr><th>指标</th><th>数值</th></tr>
                    <tr><td>状态</td><td class="{s['status']}">{s['status']}</td></tr>
                    <tr><td>BW 均值(MB/s)</td><td>{s['bw_mean'] or '-'}</td></tr>
                    <tr><td>BW 变异系数 CV</td><td>{s['bw_cv'] or '-'}%</td></tr>
                    <tr><td>IOPS 均值</td><td>{s['iops_mean'] or '-'}</td></tr>
                    <tr><td>IOPS 变异系数 CV</td><td>{s['iops_cv'] or '-'}%</td></tr>
                    <tr><td>曲线采样点数</td><td>{s['curve_points']}</td></tr>
                </table>
                <p><strong>BW/IOPS 曲线图：</strong></p>
                {img_html}
                <p class="analysis">分析：整体读写速率与 IOPS 利用率浮动情况如上所示。</p>
            </div>
            """
        stability_html = f"""
        <h2>4. EMMC 稳定性测试</h2>
        <p class="note">测试背景：挂载底层稳定性跑速，高负载队列下输出图表，持续压测运行观察带宽、IOPS 数据下沉情况。</p>
        {sections}
        """

    reliability_html = ""
    if extcsd and not is_batch:
        reliability_html = f"""
        <h2>5. 可靠性寿命估算</h2>
        <ul>
            <li>Life Time Type A: <code>{extcsd.get('life_time_type_a', 'N/A')}</code></li>
            <li>Life Time Type B: <code>{extcsd.get('life_time_type_b', 'N/A')}</code></li>
            <li>PRE EOL Info: <code>{extcsd.get('pre_eol_info', 'N/A')}</code></li>
        </ul>
        <p class="note">请根据以上数据进行综合评估。</p>
        """

    detail_rows = ""
    for r in results:
        detail_rows += f"""
        <tr>
            <td>{r['module_name']}</td>
            <td>{r['item_name']}</td>
            <td class="{r['status']}">{r['status']}</td>
            <td>{r['execution_time'] or 0}</td>
            <td>{r.get('fail_reason') or ''}</td>
        </tr>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>EMMC 性能测试与验证报告 {report_data['report_id']}</title>
    <style>
        body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 40px; color: #333; background: #f8f9fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: #fff; padding: 40px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a5276; border-bottom: 3px solid #3498db; padding-bottom: 15px; }}
        h2 {{ color: #2874a6; margin-top: 35px; border-left: 5px solid #3498db; padding-left: 12px; }}
        h3 {{ color: #2e86c1; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 14px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #eaf2f8; font-weight: bold; }}
        tr:nth-child(even) {{ background-color: #f8f9fa; }}
        .pass {{ color: #27ae60; font-weight: bold; }}
        .fail {{ color: #e74c3c; font-weight: bold; }}
        .skip {{ color: #7f8c8d; }}
        .error {{ color: #f39c12; font-weight: bold; }}
        .stability-section {{ margin: 25px 0; padding: 20px; background: #fafafa; border-radius: 8px; }}
        .stability-section img {{ max-width: 100%; height: auto; margin: 15px 0; }}
        .note {{ color: #666; font-size: 13px; font-style: italic; }}
        .analysis {{ color: #555; font-size: 14px; margin-top: 10px; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>EMMC 性能测试与验证报告</h1>
    <p><strong>报告 ID：</strong>{report_data['report_id']}</p>

    {device_html}

    <h2>汇总统计</h2>
    {summary_html}

    {extcsd_html}
    {perf_html}
    {stability_html}
    {reliability_html}

    <h2>详细结果</h2>
    <table>
        <tr><th>模块</th><th>测试项</th><th>状态</th><th>耗时(秒)</th><th>失败原因</th></tr>
        {detail_rows}
    </table>
</div>
</body>
</html>
    """
'''

pattern = r'def _generate_html\(report_data: dict\) -> str:.*?return f"""\n<!DOCTYPE html>.*?</html>\n    """'
content = re.sub(pattern, new_html.strip(), content, flags=re.DOTALL)

with open('app/api/reports.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('HTML report generator replaced')
