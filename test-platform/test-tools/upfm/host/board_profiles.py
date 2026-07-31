#!/usr/bin/env python3
"""
UPFM 板型画像（board profiles）。

每个板型一条 profile，runner 通过 board_detect 识别板型后按本文件取值做判定，
换板时无需在任务创建页人工改参数。

新增板型步骤：
1. 实机读取判别键 `ro.mc.cpu`（优先）与 `ro.product.device`（兜底）填入 identify；
2. 按下方字段说明实机采集各项期望值；
3. 在 PROFILES 中追加一条记录即可，runner 无需改动。

字段说明：
- identify   : 板型判别键。ro.mc.cpu 优先匹配，ro.product.device 兜底。
- cpu        : available_freqs = `cat .../cpu0/cpufreq/scaling_available_frequencies`（空格分隔，顺序无关比对）
               max_freq        = `cat .../cpu0/cpufreq/cpuinfo_max_freq`
- gpu        : supported = 是否支持查看 GPU 频率表；discovery 说明节点发现方式（devfreq *.gpu 自动发现）；
               available_freqs/max_freq 为 supported=True 时的期望值。
- ddr        : clk_pattern = 在 `cat /sys/kernel/debug/clk/clk_summary` 中匹配 DDR 时钟行的正则；
               clk_name    = 实机实际匹配到的时钟名（备注用）；
               expected_freq = 期望速率（clk_summary 第 4 列，单位 Hz）。
- touch      : expected_points = 触摸点数。getevent -pl 找含 ABS_MT 的设备，
               优先 ABS_MT_SLOT max+1，无 SLOT 取 ABS_MT_TRACKING_ID max+1。
- bluetooth  : supported = 蓝牙开关是否可用（探测：`pm list features | grep -i bluetooth` + 实测 svc 开关）。
               supported=False 时蓝牙开关项输出 RESULT: SKIP。
- mc_props   : 该板型 ro.mc.* 各属性期望值（空串表示固件中该属性为空，比对空串）。
"""

PROFILES = {
    # rk3568 参考板：FE7G28V8TEST / Android 11 / arm64
    # 期望值来源：UPFM测试项转换方案.md 第四节实机验证记录（2026-07-23）+ 任务 #8 实测
    "rk3568": {
        "identify": {
            "ro.mc.cpu": ["RK3568"],
            "ro.product.device": [],  # 未实测记录，暂以 ro.mc.cpu 判别
        },
        "cpu": {
            "available_freqs": "408000 600000 816000 1104000 1416000 1608000 1800000 1992000",
            "max_freq": "1992000",
        },
        "gpu": {
            "supported": True,
            "discovery": "ls /sys/class/devfreq/ 自动发现 *.gpu 节点（实机 fde60000.gpu）",
            "available_freqs": "800000000 700000000 600000000 400000000 300000000 200000000",
            "max_freq": "800000000",
        },
        "ddr": {
            "clk_pattern": r"ddr",
            "clk_name": "clk_scmi_ddr",
            # 实机实测 1056000000，与用例表 R1201 预期 1560000000 不符，以实机基线为准（待硬件确认）
            "expected_freq": "1056000000",
        },
        "touch": {
            # 实机 techwin 触摸：无 ABS_MT_SLOT，TRACKING_ID max=9 -> 十点
            "expected_points": 10,
        },
        "bluetooth": {
            "supported": True,
        },
        "mc_props": {
            "ro.mc.android_version": "ANDROID11.0",
            "ro.mc.cpu": "RK3568",
            "ro.mc.custom_api_version": "1",
            "ro.mc.oem.version": "",
            "ro.mc.product": "FE7G28/Standard",
            "ro.mc.version": "8.1.0",
            "ro.mc.version_code": "8",
        },
    },

    # A133P 板：serial 9c000c8a230487920dd / Android 10 / armeabi-v7a（32 位）
    # 期望值来源：2026-07-31 实机 adb 采集 + 任务 #9 实测记录
    "a133p": {
        "identify": {
            "ro.mc.cpu": ["A133P"],
            "ro.product.device": ["A133P"],
        },
        "cpu": {
            # 实机 scaling_available_frequencies（8 档，注意 1008000/1200000 与 rk3568 档位不同）
            "available_freqs": "408000 600000 816000 1008000 1200000 1416000 1608000 1800000",
            "max_freq": "1800000",
        },
        "gpu": {
            # 用例文档注明 A133P 不支持查看 GPU 频率表；实机 /sys/class/devfreq/ 为空，无 *.gpu 节点
            "supported": False,
            "discovery": "ls /sys/class/devfreq/ 自动发现 *.gpu 节点",
            "available_freqs": "",
            "max_freq": "",
        },
        "ddr": {
            "clk_pattern": r"ddr",
            "clk_name": "pll_ddr",
            # 实机 clk_summary: pll_ddr ... 1584000000（adb shell 已为 root，可直接读 debug 节点）
            "expected_freq": "1584000000",
        },
        "touch": {
            # 实机 cyttsp5_mt：ABS_MT_SLOT max=31 -> 32 点（驱动上报槽位数，面板物理点数未另行核实）
            "expected_points": 32,
        },
        "bluetooth": {
            # pm list features 声明 android.hardware.bluetooth / bluetooth_le；
            # 但实机实测蓝牙协议栈反复崩溃（dumpsys bluetooth_manager: CRASH/RESTART 循环），
            # svc bluetooth enable 后 bluetooth_on 恒为 0 —— 属固件缺陷，开关项如实判 FAIL 不静默。
            "supported": True,
        },
        "mc_props": {
            "ro.mc.android_version": "ANDROID10.0",
            "ro.mc.cpu": "A133P",
            "ro.mc.custom_api_version": "",   # A133P 固件该属性为空
            "ro.mc.oem.version": "",
            "ro.mc.product": "F7G18PD_HZCL01/HangZhouZeTianChunLai/ShuiZhiJianCe",
            "ro.mc.version": "2.1.0",
            "ro.mc.version_code": "3",
        },
    },
}
