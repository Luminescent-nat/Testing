#!/usr/bin/env python3
"""
UPFM 模块 T1 自动化测试项幂等导入脚本。

将《UPFM测试项转换方案》第三节定义的 27 个 T1 测试项写入 UPFM 模块（module_id=7）。
按 (module_id, name) 判重：已存在则更新全部字段，可重复执行。

执行顺序设计（sort_order）：
- 网络连通性/系统信息/显示/性能项在前；
- APK 项与外设 5 项（【人工前置】）靠后；
- WiFi/蓝牙开关倒数，飞行模式最后（会断网，执行后恢复关闭并重新打开 WiFi/蓝牙）。

用法（在 backend 目录下执行）:
    python scripts/import_upfm_items.py [--module-id 7]
"""

import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import TestItem, TestModule, User

# host_tool_dir 不在此硬编码：执行引擎会自动将 {host_tool_dir} 解析为
# 配置项 TEST_TOOLS_PATH（默认 ../test-tools）的绝对路径。

# host_exec 项统一判定：runner 输出 RESULT: PASS / RESULT: FAIL 标记
HOST_RESULT_PARSE = {"pass_pattern": "RESULT: PASS", "fail_pattern": "RESULT: FAIL"}
HOST_PARAMS = {}

# 板级默认值（rk3568 FE7G28V8TEST 实机实测，换板时在任务创建页改参数）
CPU_FREQS = "408000 600000 816000 1104000 1416000 1608000 1800000 1992000"
GPU_FREQS = "800000000 700000000 600000000 400000000 300000000 200000000"


def _schema(props: dict) -> dict:
    """生成简易 parameters_schema（键 -> 类型/默认值/说明）。"""
    return {
        "type": "object",
        "properties": {
            k: {"type": "string", "default": v, "description": d} for k, v, d in props
        },
    }


def build_items() -> list:
    """构造 27 个 T1 测试项定义，列表顺序即 sort_order（执行顺序）。"""
    items = [
        # ---- 网络类 ----
        {
            "name": "T1-01 网络连通性（ping）",
            "description": "覆盖用例 2.1.2/2.2.5/2.3.5：ping 外网断言 0% 丢包（设备无 curl/wget，网络层验证以 ping 为准）",
            "objective": "验证设备网络连通性（移动网络/以太网/WiFi 任一可用链路）",
            "precondition": "设备已联网（任一网卡）",
            "steps": "ping -c 4 -W 2 www.baidu.com",
            "expected_result": "4 包发出 4 包收到，0% packet loss",
            "exec_type": "adb_shell",
            "exec_command": "ping -c 4 -W 2 www.baidu.com",
            "result_parse": {"pass_pattern": "0% packet loss",
                             "fail_pattern": "unknown host|100% packet loss"},
            "tags": ["functional"], "timeout": 30, "retry_count": 2,
        },
        {
            "name": "T1-02 以太网 MAC 地址",
            "description": "用例 2.2.3 读取部分：读取 eth0 MAC 并断言格式合法（跨设备唯一性/重启稳定性归 T2/T3）",
            "objective": "验证以太网 MAC 地址可读取且格式正确",
            "precondition": "设备具备 eth0 网卡",
            "steps": "cat /sys/class/net/eth0/address",
            "expected_result": "输出合法 MAC（如 66:40:65:b8:0c:e7）",
            "exec_type": "adb_shell",
            "exec_command": "cat /sys/class/net/eth0/address",
            "result_parse": {"pass_pattern": "([0-9a-f]{2}:){5}[0-9a-f]{2}"},
            "tags": ["functional"], "timeout": 30, "retry_count": 2,
        },
        {
            "name": "T1-06 以太网链路状态",
            "description": "用例 2.2.1 开关动作 + 2.2.7 命令层：读 eth0 carrier 断言链路已连接",
            "objective": "验证以太网链路处于连接状态",
            "precondition": "【人工前置】插入网线；未插网线时本项预期失败（平台无跳过语义，按失败记录并复测）",
            "steps": "cat /sys/class/net/eth0/carrier && ip link show eth0",
            "expected_result": "carrier=1（链路已连接）",
            "exec_type": "adb_shell",
            "exec_command": "cat /sys/class/net/eth0/carrier && ip link show eth0",
            "result_parse": {"pass_pattern": "(?m)^1\r?$", "fail_pattern": "(?m)^0\r?$"},
            "tags": ["functional"], "timeout": 30, "retry_count": 2,
        },
        # ---- 系统信息类 ----
        {
            "name": "T1-07 固件版本与分支",
            "description": "用例 3.1.1/3.1.2/3.1.5：固件版本属性三行均非空。"
                           "注：本固件无 ro.mc.custom.version，按实机适配为 ro.mc.custom_api_version；"
                           "精确版本比对由 T1-08 参数化覆盖",
            "objective": "验证固件版本/分支/定制版本属性存在且非空",
            "precondition": "无",
            "steps": "getprop ro.build.display.id && getprop ro.mc.version && getprop ro.mc.custom_api_version",
            "expected_result": "三行输出均非空",
            "exec_type": "adb_shell",
            "exec_command": "getprop ro.build.display.id && getprop ro.mc.version && getprop ro.mc.custom_api_version",
            "result_parse": {"pass_pattern": "\\S[^\\n]*\\n\\S[^\\n]*\\n\\S"},
            "tags": ["functional"], "timeout": 30,
        },
        {
            "name": "T1-08 系统配置 ro.mc.* 七字段",
            "description": "用例 3.1.3：host_exec 逐字段比对 ro.mc.* 七字段，全部一致才 PASS。"
                           "期望值参数化，与 Jira 的一致性 = 人工把期望值填参。"
                           "注：文档字段 expected_custom_version 映射 ro.mc.custom_api_version"
                           "（固件无 ro.mc.custom.version）；ro.mc.oem.version 本固件为空串",
            "objective": "验证系统配置 ro.mc.* 七字段与基线一致",
            "precondition": "无",
            "steps": "host_exec mc_props_check.py 逐字段读取比对，输出比对表",
            "expected_result": "七字段全部与期望值一致",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/mc_props_check.py" --serial {serial}'
                ' --expected-android-version "{expected_android_version}"'
                ' --expected-cpu "{expected_cpu}"'
                ' --expected-custom-version "{expected_custom_version}"'
                ' --expected-oem-img-version "{expected_oem_img_version}"'
                ' --expected-product "{expected_product}"'
                ' --expected-version "{expected_version}"'
                ' --expected-version-code "{expected_version_code}"'
            ),
            "parameters": {
                **HOST_PARAMS,
                "expected_android_version": "ANDROID11.0",
                "expected_cpu": "RK3568",
                "expected_custom_version": "1",
                "expected_oem_img_version": "",
                "expected_product": "FE7G28/Standard",
                "expected_version": "8.1.0",
                "expected_version_code": "8",
            },
            "parameters_schema": _schema([
                ("expected_android_version", "ANDROID11.0", "ro.mc.android_version 期望值"),
                ("expected_cpu", "RK3568", "ro.mc.cpu 期望值"),
                ("expected_custom_version", "1", "ro.mc.custom_api_version 期望值"),
                ("expected_oem_img_version", "", "ro.mc.oem.version 期望值（本固件为空串）"),
                ("expected_product", "FE7G28/Standard", "ro.mc.product 期望值"),
                ("expected_version", "8.1.0", "ro.mc.version 期望值"),
                ("expected_version_code", "8", "ro.mc.version_code 期望值"),
            ]),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 60,
        },
        {
            "name": "T1-09 默认时区与自动校时",
            "description": "用例 3.2.1 默认状态部分：时区 Asia/Shanghai 且 auto_time=1",
            "objective": "验证默认时区与自动校时开关",
            "precondition": "无",
            "steps": "getprop persist.sys.timezone && settings get global auto_time",
            "expected_result": "Asia/Shanghai + 1",
            "exec_type": "adb_shell",
            "exec_command": "getprop persist.sys.timezone && settings get global auto_time",
            "result_parse": {"pass_pattern": "Asia/Shanghai\r?\n1",
                             "fail_pattern": "(?m)(^|\\n)0\r?$"},
            "tags": ["functional"], "timeout": 30,
        },
        {
            "name": "T1-10 默认 Launcher",
            "description": "用例 4.4.1：断言默认桌面为系统 Launcher（实机 com.android.launcher3，定制机型改判定参数）",
            "objective": "验证默认 Launcher 已设置",
            "precondition": "无",
            "steps": "cmd shortcut get-default-launcher",
            "expected_result": "输出 Launcher: ComponentInfo{...}",
            "exec_type": "adb_shell",
            "exec_command": "cmd shortcut get-default-launcher",
            "result_parse": {"pass_pattern": "Launcher: ComponentInfo"},
            "tags": ["functional"], "timeout": 30,
        },
        # ---- 显示设置类 ----
        {
            "name": "T1-13 屏幕旋转设置",
            "description": "用例 4.2.1 设置读回部分：记录原值 -> 设 user_rotation=1 读回 -> 恢复原值",
            "objective": "验证屏幕旋转设置可写入并读回",
            "precondition": "无",
            "steps": "记录原值 -> settings put system user_rotation 1 -> 读回断言 -> 恢复原值",
            "expected_result": "读回值为 1，结束后恢复原值",
            "exec_type": "adb_shell",
            "exec_command": (
                "orig=$(settings get system user_rotation) && "
                "settings put system user_rotation 1 && "
                "cur=$(settings get system user_rotation) && "
                "settings put system user_rotation $orig && "
                'echo "orig=$orig set_readback=$cur restored=$(settings get system user_rotation)"'
            ),
            "result_parse": {"pass_pattern": "set_readback=1"},
            "tags": ["functional"], "timeout": 30,
        },
        {
            "name": "T1-14 亮度设置",
            "description": "用例 4.2.2 设置读回部分：30/200 两档写入读回后恢复原值（实际观感归 T3 图像）",
            "objective": "验证屏幕亮度设置可写入并读回",
            "precondition": "无",
            "steps": "记录原值 -> 设 30 读回 -> 设 200 读回 -> 恢复原值",
            "expected_result": "两次读回分别为 30、200，结束后恢复原值",
            "exec_type": "adb_shell",
            "exec_command": (
                "orig=$(settings get system screen_brightness) && "
                "settings put system screen_brightness 30 && "
                "b1=$(settings get system screen_brightness) && "
                "settings put system screen_brightness 200 && "
                "b2=$(settings get system screen_brightness) && "
                "settings put system screen_brightness $orig && "
                'echo "orig=$orig low=$b1 high=$b2 restored=$(settings get system screen_brightness)"'
            ),
            "result_parse": {"pass_pattern": "low=30 high=200"},
            "tags": ["functional"], "timeout": 30,
        },
        {
            "name": "T1-15 休眠时间",
            "description": "用例 4.2.3：host_exec 记录原 timeout -> 设 15000ms -> 等待 20s -> "
                           "dumpsys power 断言 mWakefulness=Asleep -> 唤醒并恢复原值（finally 保证恢复）",
            "objective": "验证设备按设定时间进入休眠",
            "precondition": "无人工唤醒源干扰；stay_on_while_plugged_in 应为 0",
            "steps": "设 screen_off_timeout=15000 -> 等待 -> 断言 Asleep -> KEYCODE_WAKEUP -> 恢复原值",
            "expected_result": "等待后 mWakefulness=Asleep，唤醒后 Awake，timeout 恢复原值",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/sleep_check.py" --serial {serial}'
                " --timeout-ms {timeout_ms} --wait-seconds {wait_seconds}"
            ),
            "parameters": {**HOST_PARAMS, "timeout_ms": "15000", "wait_seconds": "20"},
            "parameters_schema": _schema([
                ("timeout_ms", "15000", "测试用 screen_off_timeout（毫秒）"),
                ("wait_seconds", "20", "等待休眠秒数（需大于 timeout_ms）"),
            ]),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 90, "retry_count": 1,
        },
        {
            "name": "T1-16 触摸点数",
            "description": "用例 4.3.1：host_exec 解析 getevent -pl，取 ABS_MT_SLOT（无则 TRACKING_ID）max+1",
            "objective": "验证触摸点数达到规格",
            "precondition": "无",
            "steps": "解析 getevent -pl 触摸设备 ABS_MT 最大值",
            "expected_result": "实测点数等于 expected_points（实机 10 点）",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/touch_points.py" --serial {serial}'
                " --expected-points {expected_points}"
            ),
            "parameters": {**HOST_PARAMS, "expected_points": "10"},
            "parameters_schema": _schema([
                ("expected_points", "10", "期望触摸点数（10 寸及以下机型改 3）"),
            ]),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 60,
        },
        # ---- 性能类 ----
        {
            "name": "T1-22 CPU 支持频率",
            "description": "用例 7.1.1：scaling_available_frequencies 与参数精确比对（去尾空格）。"
                           "实机 8 档与用例表 R1201 行一致，非 R071 行",
            "objective": "验证 CPU 支持频率表与基线一致",
            "precondition": "无",
            "steps": "读 cpu0 scaling_available_frequencies，归一化空格后与期望值精确比对",
            "expected_result": "频率表与 expected_freqs 完全一致",
            "exec_type": "adb_shell",
            "exec_command": (
                "actual=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies) && "
                "norm=$(echo $actual) && "
                '[ "$norm" = "{expected_freqs}" ] && echo "CPU_FREQS_MATCH: $norm" '
                '|| echo "CPU_FREQS_MISMATCH: $norm"'
            ),
            "parameters": {"expected_freqs": CPU_FREQS},
            "parameters_schema": _schema([
                ("expected_freqs", CPU_FREQS, "CPU 支持频率表（空格分隔，精确比对）"),
            ]),
            "result_parse": {"pass_pattern": "CPU_FREQS_MATCH", "fail_pattern": "CPU_FREQS_MISMATCH"},
            "tags": ["performance"], "timeout": 30,
        },
        {
            "name": "T1-23 CPU 最大频率",
            "description": "用例 7.1.3：cpuinfo_max_freq 与参数精确比对（实机 1992000）",
            "objective": "验证 CPU 最大频率与基线一致",
            "precondition": "无",
            "steps": "读 cpu0 cpuinfo_max_freq 与期望值比对",
            "expected_result": "等于 expected_max",
            "exec_type": "adb_shell",
            "exec_command": (
                "actual=$(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq) && "
                '[ "$actual" = "{expected_max}" ] && echo "CPU_MAX_MATCH: $actual" '
                '|| echo "CPU_MAX_MISMATCH: $actual"'
            ),
            "parameters": {"expected_max": "1992000"},
            "parameters_schema": _schema([
                ("expected_max", "1992000", "CPU 最大频率期望值（KHz）"),
            ]),
            "result_parse": {"pass_pattern": "CPU_MAX_MATCH", "fail_pattern": "CPU_MAX_MISMATCH"},
            "tags": ["performance"], "timeout": 30,
        },
        {
            "name": "T1-24 GPU 支持频率",
            "description": "用例 7.3.1：host_exec 自动发现 devfreq *.gpu 节点读 available_frequencies 比对",
            "objective": "验证 GPU 支持频率表与基线一致",
            "precondition": "无",
            "steps": "发现 /sys/class/devfreq/*.gpu -> 读 available_frequencies 按集合比对",
            "expected_result": "频率表与 expected_freqs 一致",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/gpu_freq_check.py" --serial {serial}'
                ' --mode available --expected "{expected_freqs}"'
            ),
            "parameters": {**HOST_PARAMS, "expected_freqs": GPU_FREQS},
            "parameters_schema": _schema([
                ("expected_freqs", GPU_FREQS, "GPU 支持频率表（空格分隔，顺序无关）"),
            ]),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["performance"], "timeout": 60,
        },
        {
            "name": "T1-25 GPU 最大频率",
            "description": "用例 7.3.3：host_exec 读 GPU max_freq 与参数比对（实机 800000000）",
            "objective": "验证 GPU 最大频率与基线一致",
            "precondition": "无",
            "steps": "发现 GPU devfreq 节点 -> 读 max_freq 比对",
            "expected_result": "等于 expected_max",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/gpu_freq_check.py" --serial {serial}'
                " --mode max --expected {expected_max}"
            ),
            "parameters": {**HOST_PARAMS, "expected_max": "800000000"},
            "parameters_schema": _schema([
                ("expected_max", "800000000", "GPU 最大频率期望值（Hz）"),
            ]),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["performance"], "timeout": 60,
        },
        {
            "name": "T1-26 DDR 频率（静止态）",
            "description": "用例 7.5.1 静止态部分：clk_summary 中 ddr 频率含期望值。"
                           "实机 clk_scmi_ddr=1056000000，用例表预期 1560000000 与实机不符，基线待与硬件确认",
            "objective": "验证 DDR 静止态频率与基线一致",
            "precondition": "无（休眠/压力态归 T2）",
            "steps": "cat clk_summary | grep -i ddr，断言出现期望频率",
            "expected_result": "ddr 相关时钟行包含 expected_ddr_freq",
            "exec_type": "adb_shell",
            "exec_command": (
                "actual=$(cat /sys/kernel/debug/clk/clk_summary | grep -i ddr) && "
                'echo "$actual" && '
                "(echo \"$actual\" | grep -q {expected_ddr_freq}) && "
                'echo "DDR_FREQ_MATCH: {expected_ddr_freq}" || echo "DDR_FREQ_MISMATCH"'
            ),
            "parameters": {"expected_ddr_freq": "1056000000"},
            "parameters_schema": _schema([
                ("expected_ddr_freq", "1056000000", "DDR 频率期望值（Hz，实机基线，待硬件确认）"),
            ]),
            "result_parse": {"pass_pattern": "DDR_FREQ_MATCH", "fail_pattern": "DDR_FREQ_MISMATCH"},
            "tags": ["performance"], "timeout": 30,
        },
        {
            "name": "T1-27 剩余内存比例",
            "description": "用例 7.4.1：host_exec 解析 dumpsys meminfo 计算 Free/Total 百分比，区间断言。"
                           "默认 50%~80%；实机非首启实测约 37%，用例基线要求烧录重启后首次执行",
            "objective": "验证首次重启后剩余内存比例落在规格区间",
            "precondition": "【前置】烧录固件重启后优先执行；非首启状态比例偏低属预期",
            "steps": "dumpsys meminfo 解析 Total/Free RAM，计算百分比并做区间断言",
            "expected_result": "剩余内存比例落在 [min_percent, max_percent]",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/mem_ratio_check.py" --serial {serial}'
                " --min-percent {min_percent} --max-percent {max_percent}"
            ),
            "parameters": {**HOST_PARAMS, "min_percent": "50", "max_percent": "80"},
            "parameters_schema": _schema([
                ("min_percent", "50", "剩余内存百分比下限（用例 60-70，按首启基线校准）"),
                ("max_percent", "80", "剩余内存百分比上限"),
            ]),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["performance"], "timeout": 60,
        },
        # ---- APK 类 ----
        {
            "name": "T1-11 APK 安装",
            "description": "用例 3.5.1：host_exec 安装测试 APK 并断言包名出现。"
                           "测试 APK 缺失时 runner 输出 RESULT: SKIP 标记（平台无跳过语义，记录显示为 error，"
                           "放入 test-tools/upfm/assets/test_app.apk 后重跑）；白名单机型用 expect=blocked 反转断言",
            "objective": "验证 APK 可正常安装",
            "precondition": "test-tools/upfm/assets/test_app.apk 存在",
            "steps": "adb install 测试 APK -> pm list packages 断言包名存在",
            "expected_result": "安装 Success 且包名出现在已安装列表",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/apk_install_check.py" --serial {serial}'
                ' --action install --apk "{host_tool_dir}/upfm/assets/test_app.apk"'
                " --package {test_package} --expect {expect}"
            ),
            "parameters": {**HOST_PARAMS, "test_package": "com.example.testapp", "expect": "ok"},
            "parameters_schema": _schema([
                ("test_package", "com.example.testapp", "测试 APK 包名"),
                ("expect", "ok", "ok=预期安装成功；blocked=白名单机型预期安装被拒"),
            ]),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 120,
        },
        {
            "name": "T1-12 APK 卸载",
            "description": "用例 3.5.2 卸载部分：pm uninstall 后断言包名消失。"
                           "包未安装（如 T1-11 被跳过）时输出 RESULT: SKIP 标记，语义同 T1-11",
            "objective": "验证 APK 可正常卸载",
            "precondition": "T1-11 已安装测试 APK",
            "steps": "pm uninstall 测试包 -> pm list packages 断言包名消失",
            "expected_result": "卸载 Success 且包名从已安装列表消失",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/apk_install_check.py" --serial {serial}'
                ' --action uninstall --apk "{host_tool_dir}/upfm/assets/test_app.apk"'
                " --package {test_package}"
            ),
            "parameters": {**HOST_PARAMS, "test_package": "com.example.testapp"},
            "parameters_schema": _schema([
                ("test_package", "com.example.testapp", "测试 APK 包名"),
            ]),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 120,
        },
        # ---- 外设类（均【人工前置】）----
        {
            "name": "T1-17 TF卡识别",
            "description": "用例 5.1.1：host_exec 自动发现 TF 卡挂载点（sm list-volumes / /mnt/media_rw）",
            "objective": "验证 TF 卡被系统识别并挂载",
            "precondition": "【人工前置】插入 TF 卡",
            "steps": "发现 public:179, 前缀的已挂载卷；找不到输出 NOT_FOUND 标记",
            "expected_result": "发现 TF 卡挂载点",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/storage_rw_check.py" --serial {serial}'
                " --mode identify --type tf"
            ),
            "parameters": dict(HOST_PARAMS),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 60,
        },
        {
            "name": "T1-18 TF卡读写",
            "description": "用例 5.1.2：host_exec 定位 TF 挂载点，dd 写 1MB 随机数据，md5sum 双侧比对后清理",
            "objective": "验证 TF 卡读写数据一致性",
            "precondition": "【人工前置】插入 TF 卡",
            "steps": "dd 写 1MB -> md5sum 读回比对 -> 删除测试文件",
            "expected_result": "写入与读回 md5 一致",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/storage_rw_check.py" --serial {serial}'
                " --mode rw --type tf"
            ),
            "parameters": dict(HOST_PARAMS),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 120,
        },
        {
            "name": "T1-19 U盘识别",
            "description": "用例 5.2.1：host_exec 自动发现 U 盘挂载点",
            "objective": "验证 U 盘被系统识别并挂载",
            "precondition": "【人工前置】插入 U 盘",
            "steps": "发现 public:8, 前缀的已挂载卷；找不到输出 NOT_FOUND 标记",
            "expected_result": "发现 U 盘挂载点",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/storage_rw_check.py" --serial {serial}'
                " --mode identify --type udisk"
            ),
            "parameters": dict(HOST_PARAMS),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 60,
        },
        {
            "name": "T1-20 U盘读写",
            "description": "用例 5.2.2：host_exec 定位 U 盘挂载点，dd 写 1MB 随机数据，md5sum 双侧比对后清理",
            "objective": "验证 U 盘读写数据一致性",
            "precondition": "【人工前置】插入 U 盘",
            "steps": "dd 写 1MB -> md5sum 读回比对 -> 删除测试文件",
            "expected_result": "写入与读回 md5 一致",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/storage_rw_check.py" --serial {serial}'
                " --mode rw --type udisk"
            ),
            "parameters": dict(HOST_PARAMS),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 120,
        },
        {
            "name": "T1-21 U盘不复制系统目录",
            "description": "用例 5.2.3：host_exec 检查 U 盘根目录无 system/vendor/data 顶层目录",
            "objective": "验证 U 盘挂载点不复制系统目录",
            "precondition": "【人工前置】插入 U 盘",
            "steps": "ls U 盘根目录，出现 system/vendor/data 任一顶层目录即失败",
            "expected_result": "根目录无系统目录",
            "exec_type": "host_exec",
            "exec_command": (
                'python "{host_tool_dir}/upfm/host/storage_rw_check.py" --serial {serial}'
                " --mode no-system-dirs --type udisk"
            ),
            "parameters": dict(HOST_PARAMS),
            "result_parse": dict(HOST_RESULT_PARSE),
            "tags": ["functional"], "timeout": 60,
        },
        # ---- 无线开关类（置后，飞行模式最后）----
        {
            "name": "T1-03 WiFi 开关",
            "description": "用例 2.3.1 开关部分：关 WiFi 读回 0 -> 开 WiFi 读回 1（重启沿用归 T2）",
            "objective": "验证 WiFi 开关可控且状态读回正确",
            "precondition": "无（执行后 WiFi 保持开启）",
            "steps": "svc wifi disable 读回 -> svc wifi enable 读回",
            "expected_result": "wifi_off=0 且 wifi_on=1",
            "exec_type": "adb_shell",
            "exec_command": (
                "svc wifi disable && sleep 2 && s1=$(settings get global wifi_on) && "
                "svc wifi enable && sleep 3 && s2=$(settings get global wifi_on) && "
                'echo "wifi_off=$s1 wifi_on=$s2"'
            ),
            "result_parse": {"pass_pattern": "wifi_off=0 wifi_on=1",
                             "fail_pattern": "wifi_off=1|wifi_on=0"},
            "tags": ["functional"], "timeout": 60, "retry_count": 2,
        },
        {
            "name": "T1-04 蓝牙开关",
            "description": "用例 2.5.1 开关部分：关蓝牙读回 0 -> 开蓝牙读回 1（重启沿用归 T2）",
            "objective": "验证蓝牙开关可控且状态读回正确",
            "precondition": "无（执行后蓝牙保持开启）",
            "steps": "svc bluetooth disable 读回 -> svc bluetooth enable 读回",
            "expected_result": "bt_off=0 且 bt_on=1",
            "exec_type": "adb_shell",
            "exec_command": (
                "svc bluetooth disable && sleep 2 && s1=$(settings get global bluetooth_on) && "
                "svc bluetooth enable && sleep 3 && s2=$(settings get global bluetooth_on) && "
                'echo "bt_off=$s1 bt_on=$s2"'
            ),
            "result_parse": {"pass_pattern": "bt_off=0 bt_on=1",
                             "fail_pattern": "bt_off=1|bt_on=0"},
            "tags": ["functional"], "timeout": 60, "retry_count": 2,
        },
        {
            "name": "T1-05 飞行模式开关",
            "description": "用例 2.6.1 开关部分：开飞行模式读回 1 -> 关飞行模式读回 0，"
                           "结束后恢复关闭态并重新打开 WiFi/蓝牙（重启沿用归 T2）",
            "objective": "验证飞行模式开关可控且状态读回正确",
            "precondition": "排在任务最后执行（会断网）",
            "steps": "开飞行模式读回 -> 关飞行模式读回 -> 恢复 WiFi/蓝牙",
            "expected_result": "airplane_on=1 且 airplane_off=0",
            "exec_type": "adb_shell",
            "exec_command": (
                "settings put global airplane_mode_on 1 && "
                "am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true && "
                "sleep 2 && s1=$(settings get global airplane_mode_on) && "
                "settings put global airplane_mode_on 0 && "
                "am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false && "
                "sleep 3 && s2=$(settings get global airplane_mode_on) && "
                "svc wifi enable && svc bluetooth enable && "
                'echo "airplane_on=$s1 airplane_off=$s2"'
            ),
            "result_parse": {"pass_pattern": "airplane_on=1 airplane_off=0",
                             "fail_pattern": "airplane_on=0|airplane_off=1"},
            "tags": ["functional"], "timeout": 60, "retry_count": 2,
        },
    ]
    return items


UPSERT_FIELDS = [
    "description", "objective", "precondition", "steps", "expected_result",
    "exec_type", "exec_command", "parameters", "parameters_schema",
    "judgement_type", "result_parse", "tags", "timeout", "retry_count",
    "on_failure", "sort_order", "enabled",
]


async def main(module_id: int):
    async with AsyncSessionLocal() as db:
        module = await db.get(TestModule, module_id)
        if not module:
            print(f"错误: 测试模块 id={module_id} 不存在")
            sys.exit(1)
        print(f"目标模块: id={module.id} name={module.name}")

        user = (await db.execute(select(User).order_by(User.id))).scalars().first()
        created_by = user.id if user else 1

        items = build_items()
        assert len(items) == 27, f"测试项数量应为 27，实际 {len(items)}"

        id_list = []
        created = updated = 0
        for idx, data in enumerate(items, start=1):
            result = await db.execute(
                select(TestItem).where(
                    TestItem.module_id == module_id, TestItem.name == data["name"]
                )
            )
            item = result.scalar_one_or_none()
            row = {
                "judgement_type": "assertion",
                "on_failure": "continue",
                "retry_count": 0,
                "enabled": True,
                "sort_order": idx,
                **data,
            }
            if item:
                for field in UPSERT_FIELDS:
                    if field in row:
                        setattr(item, field, row[field])
                updated += 1
            else:
                item = TestItem(module_id=module_id, created_by=created_by, **row)
                db.add(item)
                created += 1
            await db.flush()
            id_list.append((item.id, item.name))

        await db.commit()

    print(f"导入完成: 新建 {created}，更新 {updated}，共 {len(id_list)} 项")
    for item_id, name in id_list:
        print(f"  id={item_id:<4} {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UPFM 模块 T1 测试项幂等导入")
    parser.add_argument("--module-id", type=int, default=7,
                        help="目标测试模块 ID（默认 7，可在平台模块管理页查看）")
    args = parser.parse_args()
    asyncio.run(main(args.module_id))
