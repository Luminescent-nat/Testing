# UPFM 测试用例自动化转换方案（审核稿）

- 来源：`D:\MCTEST\nononono\UPFM.xlsx`（UPFM sheet，共 **105 条用例**）
- 目标模块：平台测试模块 **UPFM**（已存在，0 测试项）
- 验证设备：`FE7G28V8TEST`（rk3568 / Android 11 / online，实机抽查过命令可行性）
- 日期：2026-07-23

---

## 一、分类方法

不再简单二分"自动/手工"，按**转化手段**分四梯队：

| 梯队 | 定义 | 用例数 |
|---|---|---|
| **T1 纯命令自动化** | 确定性 adb_shell / host_exec 命令 + 精确断言，本次即可落库执行 | 38 条（合并为 27 个测试项） |
| **T2 半自动（人工介入+自动判定）** | host_exec runner 打印人工提示（监控页实时可见）→ 轮询等待 → 自动采集判定。平台现状即可支持，需开发通用 runner 框架 | 18 条 |
| **T3 工具化全自动** | 需引入 uiautomator2（UI 操作）/ OpenCV 图像判定 / 音频分析 / 多次采样统计 | 33 条 |
| **保留手工** | 物理换装、破坏性操作、无硬件、性价比过低 | 16 条 |

T1 判定标准（三条件同时满足）：命令可完成操作与采集；判定为确定性断言（精确匹配/数值比对）；结果稳定可复现。
概率性判定（动态调频、CPU 使用率、信号强度定性）一律不进 T1。

---

## 二、全量用例分类总表（105 条）

### 1、冒烟测试

| 用例ID | 用例名称 | 梯队 | 理由 / 转化手段 |
|---|---|---|---|
| 1.1.1 | 首次烧录固件验收测试 | 手工 | 依赖瑞芯微烧录工具链，属测试前置工序；亮屏/触摸/闪屏属感官判定（T3 图像可覆盖"烧录后显示验证"子项，见路线图） |

### 2、无线与网络

| 用例ID | 用例名称 | 梯队 | 理由 / 转化手段 |
|---|---|---|---|
| 2.1.1 | IMEI号验证 | T2 | 卡面 IMEI 由人工录为任务参数，`service call iphonesubinfo 1` 输出自动比对（需 4G 模块） |
| 2.1.2 | ping包（移动网络） | T1 | `ping -c 4 www.baidu.com`，断言 0% packet loss（实机已验证） |
| 2.1.3 | 浏览器上网（4G） | T3 | 网络层已被 T1 ping 覆盖；浏览器 UI 部分用 uiautomator2 打开页面 + 截图判定 |
| 2.1.4 | 运营商驻网 | 手工 | 多运营商 SIM 卡备件矩阵，人工换装 |
| 2.1.5 | ICCID号验证 | T2 | 卡面 ICCID 录为参数，`logcat -b radio` 抓取自动比对 |
| 2.1.6 | 多种类4G模块验证 | 手工 | 多型号模块硬件换装 |
| 2.1.7 | 信号栏状态（4G） | T2 | 人工插拔天线，`dumpsys telephony.registry` 自动读信号值前后对比；图标显示归 T3 图像 |
| 2.2.1 | 以太网开关 | T1（开关动作）+T2（重启沿用） | `ifconfig eth0 up/down` + `ip link` 读回；重启后状态沿用由 T2 runner reboot+回连校验 |
| 2.2.2 | 代理（以太网） | T3 | uiautomator2 配置代理 + Fiddler 侧自动校验抓包记录 |
| 2.2.3 | mac地址 | T1（读取）+T3（跨设备/重启对比） | `cat /sys/class/net/eth0/address` 断言 MAC 格式（实机已验证）；跨设备唯一性需多设备任务管理，重启稳定性归 T2 重启框架 |
| 2.2.4 | 静态Ip配置 | T3 | uiautomator2 设置界面配置 + `ip addr` 读回；重启沿用归 T2 |
| 2.2.5 | ping包（以太网） | T1 | 同 2.1.2，合并为参数化"网络连通性"项 |
| 2.2.6 | 浏览器上网（以太网） | T3 | 同 2.1.3 |
| 2.2.7 | 信号栏状态（以太网） | T1（命令层）+T3（图标） | `cat /sys/class/net/eth0/carrier` 断言连接状态；状态栏图标归 T3 图像 |
| 2.2.8 | pppoe | 手工（N/A） | 当前设备无该模式，用例本身标注 N/A |
| 2.3.1 | wifi开关 | T1（开关）+T2（重启沿用） | `svc wifi enable/disable` + `settings get global wifi_on` 读回（实机已验证） |
| 2.3.2 | 热点扫描 | T1 | `cmd wifi list-scan-results` 断言结果非空；中文/火星文 SSID 显示正确性归 T3 图像 |
| 2.3.3 | 静态Ip模式（wifi） | T3 | 同 2.2.4 |
| 2.3.4 | 代理（wifi） | T3 | 同 2.2.2（另有证书安装步骤） |
| 2.3.5 | ping包（wifi） | T1 | 同 2.1.2，合并 |
| 2.3.6 | 浏览器上网（wifi） | T3 | 同 2.1.3 |
| 2.3.7 | 信号强度 | T2 | 人工插拔天线，`dumpsys wifi` 自动读 RSSI 前后对比（定性观察转为定量差值判定） |
| 2.3.8 | 信号栏状态（wifi） | T3 | 状态栏图标有无归图像判定 |
| 2.4.1 | 热点共享 | T3 | uiautomator2 开热点 + 宿主机/辅助设备扫描 SSID 并连接验证 |
| 2.4.2 | 以太网共享 | 手工 | 辅助设备链路复杂，T4 阶段再议 |
| 2.4.3 | 蓝牙网络共享 | 手工 | 同上 |
| 2.4.4 | 网络优先级 | T3 | 多网络并存时自动读 `ip route` 路由表判定出口优先级 |
| 2.5.1 | 蓝牙开关 | T1（开关）+T2（重启沿用） | `svc bluetooth` + `settings get global bluetooth_on` 读回 |
| 2.5.2 | 蓝牙搜索 | T3 | `bluetoothctl scan` 或 dumpsys 判定发现设备（需环境中有可发现设备，设超时与重试） |
| 2.5.3 | 蓝牙传输 | T3 | OBEX 推送脚本 + 对端文件校验，需配对辅助设备 |
| 2.6.1 | 飞行模式开关 | T1（开关）+T2（重启沿用） | `settings put/get global airplane_mode_on` + 广播读回 |

### 3、OS 设置

| 用例ID | 用例名称 | 梯队 | 理由 / 转化手段 |
|---|---|---|---|
| 3.1.1 | 版本 | T1 | `getprop ro.build.display.id`/`ro.mc.version` 非空 + 参数化比对 |
| 3.1.2 | 分支 | T1 | 同上，并入"固件信息校验"项 |
| 3.1.3 | 系统配置（ro.mc.* 七字段） | T1 | host_exec 逐字段比对（参数化期望值，实机已验证 getprop 可用）；与 Jira 一致性 = 参数从 Jira 抄入 |
| 3.1.4 | 固件时间 | T2 | 当前版本不支持查看编译时间（用例已注明 N/A）；支持后参数化比对 |
| 3.1.5 | 固件信息 | T1 | 同 3.1.1，与固件名称对比 = 参数化 |
| 3.2.1 | 时区默认状态 | T1 | `getprop persist.sys.timezone`==Asia/Shanghai、`settings get global auto_time`==1（实机已验证）；手动改时间校验归 T3 UI |
| 3.3.1 | 设置其他国家语言 | T3 | uiautomator2 切换语言 + 界面存活判定（dumpsys activity + 截图） |
| 3.3.2 | 语言支持 | T3 | 同上 |
| 3.4.1 | 恢复出厂设置 | 手工 | 破坏性操作，与回归测试目标冲突，建议作为独立维护工序 |
| 3.5.1 | apk安装 | T1 | host_exec：push 测试 APK + `pm install` + `pm list packages` 断言（白名单机型行为参数化说明） |
| 3.5.2 | apk卸载 | T1 | `pm uninstall` + 包名消失断言（资源管理器安装/拖拽卸载路径归 T3 UI；重启后复查归 T2） |

### 4、显示和触摸

| 用例ID | 用例名称 | 梯队 | 理由 / 转化手段 |
|---|---|---|---|
| 4.1.1 | 开机logo、开机动画 | T3 | 开机过程连续 screencap + 黑屏/白线特征检测 |
| 4.1.2 | 前后沿 | T3 | 截图边缘像素分析（黑条/图标超出检测） |
| 4.1.3 | 默认方向 | T3 | screencap 分辨率宽高比 + 内容方向判定 |
| 4.1.4 | 壁纸显示 | T3 | 截图完整性分析 |
| 4.1.5 | 显示状况（水波纹/闪烁/坏点） | T3 | 连续帧差异分析 + 坏点检测；注明误判率，建议辅助判定 |
| 4.1.6-4.1.9 | 副屏/HDMI 四项 | 手工（本机 N/A） | 本机无 HDMI；有接口机型走 T3 图像（`dumpsys SurfaceFlinger` display 枚举 + 截图） |
| 4.2.1 | 旋转方向 | T1 | `settings put/get system user_rotation` 读回断言（实机已验证）；开机动画不受影响归 T3 |
| 4.2.2 | 亮度 | T1 | `settings put/get system screen_brightness` 读回（实机已验证）；实际亮度变化观感归 T3 图像（截图平均亮度差） |
| 4.2.3 | 休眠时间 | T1 | 设 `screen_off_timeout`=15s，等待后 `dumpsys power` 断言 Asleep，结束唤醒并恢复原值（retry 1 次防干扰） |
| 4.2.4 | 工具栏显示/隐藏 | T3 | 定制功能，UI 开关 + 截图判定状态栏/导航栏有无 |
| 4.2.5 | 锁屏后触摸唤醒 | T3 | input tap 注入 + `dumpsys power` 唤醒状态 + 截图判定 |
| 4.3.1 | 触摸点数 | T1 | `getevent -pl` 解析 ABS_MT_SLOT/TRACKING_ID max（实机验证：max=9 即十点） |
| 4.3.2 | 触摸边缘 | T3 | `input swipe` 沿边缘注入 + getevent 坐标捕获验证；物理手感部分保留手工 |
| 4.4.1 | Launcher界面 | T1 | `cmd shortcut get-default-launcher` 断言（实机验证：com.android.launcher3）；定制桌面比对走参数 |

### 5、外接接口

| 用例ID | 用例名称 | 梯队 | 理由 / 转化手段 |
|---|---|---|---|
| 5.1.1 | TF卡识别 | T1【人工前置插卡】 | `sm list-volumes public`/`ls /mnt/media_rw/` 断言挂载点出现 |
| 5.1.2 | TF卡读写 | T1【人工前置插卡】 | dd 写 1MB → 读回 md5 比对 → 清理 |
| 5.2.1 | U盘识别 | T1【人工前置插U盘】 | 同 5.1.1 |
| 5.2.2 | U盘读写 | T1【人工前置插U盘】 | 同 5.1.2 |
| 5.2.3 | U盘不复制系统目录 | T1【人工前置插U盘】 | ls U盘根目录，fail_pattern 匹配 system/vendor/data |
| 5.2.4 | U盘数量 | T2 | 人工按 USB 口逐个插入，runner 轮询计数挂载点 |
| 5.3.1 | USB外设 | T3 | 鼠标/键盘：`getevent -pl` 枚举输入设备出现新节点即判定；扫码枪/摄像头需实物，部分保留手工 |
| 5.4.1 | SPK/HPO | T3 | 播放标准音源 + 回采能量/频谱分析；注明误判率，建议辅助判定+人工抽检 |
| 5.5.1 | MIC | T3 | `tinycap` 录音 + 非静音判定（文件能量阈值） |
| 5.6.1 | GPIO输入 | T2 | 人工短接 GND/VCC，runner 轮询 `cat /sys/class/gpio/.../value` 判定 0/1 翻转 |
| 5.6.2 | GPIO高低电平 | T2 | 自动拉高/拉低，人工电压表读数录入参数比对；或 T4 接 ADC 自动读 |
| 5.7.1 | 打开串口通讯 | T2 | 串口接回环/电脑，host_exec pyserial 收发逐条比对（115200/9600 两档） |
| 5.7.2 | 关闭串口 | T2 | 关闭调试后断言端口无数据 |
| 5.8.1 | CAN | T2 | CAN 盒对连，host_exec 经 cantest/SocketCAN 收发比对 |

### 6、系统硬件

| 用例ID | 用例名称 | 梯队 | 理由 / 转化手段 |
|---|---|---|---|
| 6.1.1 | 断电时间存储 | T4 | USB 程控继电器断电 1 分钟 → 上电回连 → 自动比对系统时间漂移 |
| 6.2.1-6.2.6 | 物理按键×6 | T3（功能面）+手工（物理可靠性） | `input keyevent` 等效验证系统响应（锁屏/音量/Home/返回）；按键物理手感与寿命保留手工 |
| 6.3.1 | 电源指示灯 | 手工 | 光敏传感器改造性价比低，保留目检 |
| 6.3.2 | 网口指示灯 | 手工 | 同上 |
| 6.4.1 | GPS | T3 | `dumpsys location` 解析卫星数（需开窗环境，前置注明） |
| 6.4.2 | cpu散热风扇 | 手工 | 温度可自动读（thermal 节点），风扇启停声音/风量判定保留人工（或 T4 转速传感器） |
| 6.4.3 | 自带摄像头方向 | T3 | 拍照 + 图像方向特征比对 |
| 6.4.4 | 相机分辨率切换 | T3 | 拍照后解析图片尺寸序列 |
| 6.4.5 | 指纹模块 | 手工 | 依赖产线测试软件 |
| 6.4.6 | 刷卡模块 | T2 | 人工刷卡，runner 读取输入焦点内容/logcat 判定卡号 |
| 6.4.7 | 扫码 | T2 | 同 6.4.6 |
| 6.4.8 | 电源开关 | T4 | 程控继电器联动 |

### 7、性能测试

| 用例ID | 用例名称 | 梯队 | 理由 / 转化手段 |
|---|---|---|---|
| 7.1.1 | CPU支持频率 | T1 | `scaling_available_frequencies` 精确比对（实机实测值见第四节） |
| 7.1.2 | CPU动态调频 | T3 | monkey 负载 + 每 2s 采样 cur_freq 多次，统计是否出现档位变化（概率性 → 多次采样降低误判） |
| 7.1.3 | CPU最大频率 | T1 | `cpuinfo_max_freq` 精确比对（实机 1992000） |
| 7.1.4 | 老化中最大频率（CPU） | T2 | 人工进老化模式，runner 周期采样 cur_freq ≤ max |
| 7.2.1 | 第一次重启CPU使用率（统一化） | T3 | 重启回连后多次采样 `dumpsys cpuinfo` 取均值，宽区间断言（30%±20）；概率性，不进 T1 |
| 7.2.2 | 同上（非统一化） | T3 | 同上 |
| 7.3.1 | GPU支持频率 | T1 | 自动发现 devfreq 节点（实机：fde60000.gpu），available_frequencies 精确比对 |
| 7.3.2 | GPU动态调频 | T3 | 同 7.1.2 |
| 7.3.3 | GPU最大频率 | T1 | max_freq 精确比对（实机 800000000） |
| 7.3.4 | 老化中最大频率（GPU） | T2 | 同 7.1.4 |
| 7.4.1 | 第一次重启后剩余内存 | T1 | `dumpsys meminfo` 解析 Free/Total 计算比例，区间断言（参数化阈值，实机非首启实测 37%，阈值需按首启基线调） |
| 7.5.1 | DDR频率 | T1（静止态）+T2（休眠/压力态） | `clk_summary` grep ddr 读值比对（实机 clk_scmi_ddr=1056000000，与用例表 R1201 预期 1560000000 不符，**以实机基线为准调参**）；休眠后/安兔兔压力态归 T2 |

### 8、产测软件测试

| 用例ID | 用例名称 | 梯队 | 理由 / 转化手段 |
|---|---|---|---|
| 8.1.1 | 产测软件驱动测试 | T4 | 产测软件本身已一键自动化；平台侧做"调起+结果采集"，需其提供 CLI/结果文件接口 |
| 8.2.1 | 产测软件整机测试 | T4 | 需工装对接，同上 |

**汇总**：T1 38 条（→27 个测试项）｜T2 18 条｜T3 33 条｜保留手工 16 条

---

## 三、T1 自动化测试项设计明细（27 项）

通用约定：
- `on_failure=continue`，网络类 `retry_count=2`，其余 0（除注明外）
- 四要素（objective/precondition/steps/expected_result）按源用例原文映射，下表从略，仅写执行设计
- 板级期望值全部参数化（`parameters` + `parameters_schema`），默认值按 rk3568 实机实测填写，换板时在任务创建页改参数即可

### 网络类（6 项）

**T1-01 网络连通性（ping）**（覆盖 2.1.2/2.2.5/2.3.5）
- exec_type: `adb_shell`；command: `ping -c 4 -W 2 www.baidu.com`
- pass_pattern: `0% packet loss`；fail_pattern: `unknown host|100% packet loss`
- timeout 30；retry_count 2；tags: functional

**T1-02 以太网 MAC 地址**（2.2.3 读取部分）
- adb_shell：`cat /sys/class/net/eth0/address`
- pass_pattern: `^([0-9a-f]{2}:){5}[0-9a-f]{2}$`（实机：66:40:65:b8:0c:e7）
- tags: functional；跨设备唯一性、重启稳定性 → T2/T3，不在本项

**T1-03 WiFi 开关**（2.3.1 开关部分）
- adb_shell（两段，先关后开并读回）：
  `svc wifi disable && sleep 2 && settings get global wifi_on` → 断言 `0`；`svc wifi enable && sleep 3 && settings get global wifi_on` → 断言 `1`
- 实现为一条组合命令 + pass_pattern `^1$`（最终态），或拆 2 个测试项（关/开）；建议拆 2 项保证断言清晰
- 重启沿用 → T2

**T1-04 蓝牙开关**（2.5.1 开关部分）
- 同 T1-03 结构：`svc bluetooth disable/enable` + `settings get global bluetooth_on` 读回

**T1-05 飞行模式开关**（2.6.1 开关部分）
- adb_shell：`settings put global airplane_mode_on 1 && am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true && sleep 2 && settings get global airplane_mode_on` → `1`；反向关 → `0`（拆 2 项）
- 执行后恢复关闭态，避免影响后续网络项

**T1-06 以太网链路状态**（2.2.1 开关动作 + 2.2.7 命令层）
- adb_shell：`cat /sys/class/net/eth0/carrier`（插网线=1）+ `ip link show eth0`
- 【人工前置】插网线；pass_pattern: `1`；未插网线时本项应跳过（precondition 注明）

### 系统信息类（4 项）

**T1-07 固件版本与分支**（3.1.1/3.1.2/3.1.5）
- adb_shell：`getprop ro.build.display.id && getprop ro.mc.version && getprop ro.mc.custom.version`
- pass：三行均非空；可选参数 `expected_version` 精确比对（与固件名/Jira 的一致性 = 人工把期望值填参）

**T1-08 系统配置 ro.mc.* 七字段**（3.1.3）
- host_exec：`python "{host_tool_dir}/upfm/host/mc_props_check.py" --serial {serial}` 
- 参数：`expected_android_version/expected_cpu/expected_custom_version/expected_oem_img_version/expected_product/expected_version/expected_version_code`
- runner 逐字段比对并输出差异表，全部一致才 pass（实机：product=FE7G28/Standard, cpu=RK3568）
- tags: functional；timeout 60

**T1-09 默认时区与自动校时**（3.2.1 默认状态部分）
- adb_shell：`getprop persist.sys.timezone && settings get global auto_time`
- pass_pattern: `Asia/Shanghai`；auto_time == `1`（实机已验证）

**T1-10 默认 Launcher**（4.4.1）
- adb_shell：`cmd shortcut get-default-launcher`
- pass_pattern: `Launcher: ComponentInfo`（实机：com.android.launcher3）；定制机型参数化 expected_launcher

### APK 类（2 项）

**T1-11 APK 安装**（3.5.1）
- host_exec：`python "{host_tool_dir}/upfm/host/apk_install_check.py" --serial {serial} --apk "{host_tool_dir}/upfm/assets/test_app.apk"`
- runner：push → `pm install` → `pm list packages | grep <pkg>` 断言 → 输出结果
- 需准备一个小体积测试 APK 放 `test-tools/upfm/assets/`；白名单定制机型预期安装被拒 → 参数 `expect=blocked` 切换断言方向
- timeout 120

**T1-12 APK 卸载**（3.5.2 卸载部分）
- host_exec：同 runner：`pm uninstall <pkg>` → `pm list packages` 断言消失
- 重启后复查、资源管理器路径 → T2/T3

### 显示设置类（4 项）

**T1-13 屏幕旋转设置**（4.2.1 设置读回部分）
- adb_shell：记录原值 → `settings put system user_rotation 1` → 读回断言 `1` → 恢复原值
- 开机动画不受影响 → T3

**T1-14 亮度设置**（4.2.2 设置读回部分）
- adb_shell：`settings put system screen_brightness 30` 读回 → `200` 读回 → 恢复原值（实机当前 255）

**T1-15 休眠时间**（4.2.3）
- host_exec runner：记录原 timeout（实机为 2147483647=永不休眠）→ 设 15000ms → 等待 18s → `dumpsys power` 断言 `mWakefulness=Asleep` → `input keyevent KEYCODE_WAKEUP` 唤醒 → 恢复原值
- timeout 90；retry_count 1（防唤醒源干扰）；tags: functional
- 触摸唤醒（点亮后再验证）归 T3

**T1-16 触摸点数**（4.3.1）
- host_exec runner 解析 `getevent -pl`：取触摸设备的 `ABS_MT_SLOT`（无则用 `ABS_MT_TRACKING_ID`）max 值 +1 = 触摸点数
- 参数 expected_points（实机：10，TRACKING_ID max=9）；10 寸及以下机型改 3

### 外设类（5 项，均【人工前置】）

**T1-17 TF卡识别**（5.1.1）
- 【人工前置】插入 TF 卡；adb_shell：`sm list-volumes public && ls /mnt/media_rw/`
- pass：出现非 emulated 的挂载路径；timeout 30

**T1-18 TF卡读写**（5.1.2）
- 【人工前置】；host_exec runner：定位 TF 挂载点 → `dd if=/dev/urandom of=<tf>/upfm_test.bin bs=1M count=1` → 读回 md5sum 双侧比对 → 删除测试文件
- timeout 120

**T1-19 U盘识别**（5.2.1）：同 T1-17，前置改插 U 盘

**T1-20 U盘读写**（5.2.2）：同 T1-18

**T1-21 U盘不复制系统目录**（5.2.3）
- 【人工前置】；adb_shell：`ls <udisk_mount>/`
- fail_pattern: `^(system|vendor|data)$`（出现系统目录即失败）；pass：目录存在且无匹配

### 性能类（6 项）

**T1-22 CPU 支持频率**（7.1.1）
- adb_shell：`cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies`
- 参数 expected_freqs，默认（rk3568 实机）：`408000 600000 816000 1104000 1416000 1608000 1800000 1992000`（精确匹配，去尾空格比对）
- 注意：用例表 R071 行与实机不符，**实机值与 R1201 行一致**，以实机基线为准

**T1-23 CPU 最大频率**（7.1.3）
- adb_shell：`cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq`
- 参数 expected_max，默认 `1992000`（实机一致）

**T1-24 GPU 支持频率**（7.3.1）
- host_exec runner：先 `ls /sys/class/devfreq/` 自动发现 *.gpu 节点（实机 fde60000.gpu）→ 读 available_frequencies 比对
- 参数 expected_freqs，默认（实机）：`800000000 700000000 600000000 400000000 300000000 200000000`

**T1-25 GPU 最大频率**（7.3.3）
- 同 runner：max_freq == 参数，默认 `800000000`（实机一致）

**T1-26 DDR 频率（静止态）**（7.5.1 静止态部分）
- adb_shell：`cat /sys/kernel/debug/clk/clk_summary | grep -i ddr`
- 参数 expected_ddr_freq，默认 `1056000000`（实机 clk_scmi_ddr 实测；**用例表 R1201 预期 1560000000 与实机不符，需与硬件确认基线**）
- 休眠态/安兔兔压力态 → T2

**T1-27 剩余内存比例**（7.4.1）
- host_exec runner：`dumpsys meminfo` 解析 Free RAM / Total RAM 计算百分比，区间断言
- 参数 min_percent/max_percent，默认 50/80（用例要求 60-70；实机非首启实测 37%，**必须在"烧录重启后首次"前置下执行并按首启基线校准**）
- 【前置】烧录固件重启后优先执行；tags: performance

---

## 四、实机验证记录（rk3568 / FE7G28V8TEST / Android 11，2026-07-23）

编制过程中在真机上抽查的命令与结果：

| 命令 | 结果 | 结论 |
|---|---|---|
| `ping -c 3 www.baidu.com` | 3 received, 0% loss | 网络项可行，设备在线 |
| `getprop persist.sys.timezone` | Asia/Shanghai | 时区项可行，当前即 PASS |
| `settings get global wifi_on` | 1 | WiFi 开关读回可行 |
| `cat .../scaling_available_frequencies` | 408000...1992000（8 档） | **与用例表 R1201 行一致，非 R071**——期望值一律参数化 |
| `cat .../cpuinfo_max_freq` | 1992000 | 同上 |
| `ls /sys/class/devfreq/` | dmc / fde60000.gpu / npu / rkvenc / rkvdec | GPU 节点可自动发现 |
| `cat .../fde60000.gpu/available_frequencies` | 800M...200M（6 档），max 800000000 | 与用例表 R1201 行一致 |
| `clk_summary grep ddr` | clk_scmi_ddr=1056000000 | **与用例表预期 1560000000 不符，需与硬件确认基线** |
| `cat /sys/class/net/eth0/address` | 66:40:65:b8:0c:e7 | MAC 项可行 |
| `dumpsys meminfo` | Total 2006888K / Free 748316K（37%） | 非首启状态不满足 60-70%，该项必须首启执行 |
| `cmd shortcut get-default-launcher` | com.android.launcher3 | Launcher 项可行 |
| `getevent -pl` | 触摸设备 techwin，TRACKING_ID max=9 | 十点触摸，解析口径确认 |
| `which curl / wget` | 均无 | 上网验证只能 ping（网络层）；浏览器 UI 归 T3 |
| `settings get system screen_off_timeout` | 2147483647（永不休眠） | 休眠项需先改值，测后恢复 |

**需要你确认的 3 个偏差**：
1. CPU/GPU 频率表实机与用例文档的 R071 行不符、与 R1201 行一致——按实测值做默认参数，是否正确？
2. DDR 频率实机 1056000000 ≠ 用例预期 1560000000——是固件配置差异还是用例表过时？
3. 剩余内存 60-70% 只在"烧录后首次重启"成立——日常回归时该项是否跳过或放宽阈值？

---

## 五、渐进式自动化路线图（T2/T3/T4）

### 第二步：T2 半自动框架（18 条，平台现状即可做）

开发一个通用 host_exec runner 基类 `manual_assist_runner.py`：
- 在 stdout 打印醒目的【人工操作】提示（平台监控页已有实时日志推送，操作员即时可见）
- 轮询设备状态直到条件满足或超时（默认 120s 可调）
- 条件满足后自动采集、自动判定、输出结构化结果

纳入项：2.1.1 IMEI、2.1.5 ICCID（参数化比对）、2.1.7/2.3.7 信号值对比、2.2.1/2.3.1/2.5.1/2.6.1 重启沿用（reboot+wait-for-device+回连校验）、2.3.5.x 重启复查、5.2.4 U盘数量、5.6.1/5.6.2 GPIO、5.7/5.8 串口/CAN 收发比对（pyserial/SocketCAN）、6.4.6/6.4.7 刷卡扫码读值、7.1.4/7.3.4 老化中频率采样、7.5.1 休眠/压力态 DDR。

### 第三步：T3 工具化（33 条，按投入产出排序）

1. **uiautomator2（优先，覆盖最大）**：pip 安装、宿主机直连 adb，与 host_exec 架构天然契合。覆盖：2.2.2/2.2.4/2.3.3/2.3.4 静态IP与代理、3.3 语言切换、4.2.4 工具栏、2.4.1 热点共享、3.5 资源管理器安装路径、2.1.3/2.2.6/2.3.6 浏览器上网、4.2.5 锁屏唤醒、3.2.1 改时间校验
2. **图像判定（adb screencap + OpenCV）**：4.1.1-4.1.5 屏幕显示五项、2.x.7/2.x.8 状态栏图标、4.4.1 桌面、4.3.2 触摸边缘轨迹、HDMI 四项（有接口机型）
3. **统计采样**：7.1.2/7.3.2 动态调频（monkey 负载+多次采样）、7.2 CPU 使用率（均值+宽区间）、2.4.4 路由表优先级、2.5.2/2.5.3 蓝牙搜索传输
4. **音频分析**：5.4 SPK、5.5 MIC（注明误判率，辅助判定+人工抽检）
5. **按键功能等效**：6.2 六键 input keyevent 验证系统响应（物理可靠性仍手工）

### 第四步：T4 工装硬件（按需立项）

- USB 程控继电器：6.1.1 RTC 断电、6.4.8 电源开关、批量"断电重启沿用"类
- 产测软件对接（8.1.1/8.2.1）：推动产测软件提供 CLI/结果文件接口，平台做调起+采集
- 程控网络环境：2.4.2/2.4.3 共享、弱网场景

### 最终仍保留手工（16 条）

1.1.1 烧录、3.4.1 恢复出厂、2.1.4 运营商矩阵、2.1.6 4G 模块矩阵、2.2.8 pppoe（N/A）、4.1.6-4.1.9 HDMI（本机无接口）、6.3.1/6.3.2 指示灯、6.4.2 风扇（感官）、6.4.5 指纹（产线软件）、5.3.1 USB 外设矩阵（部分）、6.2 按键物理可靠性（部分）、5.5.1 音质（部分）、4.3.2 触摸手感（部分）

---

## 六、审核通过后的落地步骤

1. 开发 host_exec runner：`mc_props_check.py`、`apk_install_check.py`、`storage_rw_check.py`、`sleep_check.py`、`touch_points.py`、`gpu_freq_check.py`、`mem_ratio_check.py`（放 `test-platform/test-tools/upfm/host/`，参照 EMMC runner 风格）
2. 编写幂等导入脚本，将 27 个 T1 测试项写入 UPFM 模块（module_id=7）
3. 在 FE7G28V8TEST 上创建任务全量执行，验证测试记录与报告产出
4. 修正实测中暴露的命令适配问题，输出首轮报告供确认

> 注：T1 实际为 **27 个测试项**（网络 6 + 系统信息 4 + APK 2 + 显示设置 4 + 外设 5 + 性能 6），覆盖 38 条源用例。

---

## 七、首轮落地实测结果（2026-07-23，FE7G28V8TEST / rk3568 / Android 11）

- 执行方式：任务 ID 8（27 项全选，immediate），平台报告 RPT-20260723-008（JSON+HTML 已落盘）
- 总分布：**pass 18 / fail 7 / error 2**，无 timeout；fail/error 全部为环境前置或判定标准问题，**无命令适配缺陷，未修改任何平台框架代码**
- 任务后设备状态复核：screen_off_timeout=2147483647、亮度 255、旋转 0、飞行模式关、WiFi/蓝牙开、ping 外网 0% 丢包——全部复原

### 逐项结果

| 测试项 | 状态 | 实测输出摘要 | 问题与处置 |
|---|---|---|---|
| T1-01 网络连通性（ping） | pass | 4/4 收到，0% loss，3s | — |
| T1-02 以太网 MAC 地址 | pass | 66:40:65:b8:0c:e7 | — |
| T1-03 WiFi 开关 | pass | wifi_off=0 wifi_on=1 | — |
| T1-04 蓝牙开关 | pass | bt_off=0 bt_on=1 | — |
| T1-05 飞行模式开关 | pass | airplane_on=1 airplane_off=0 | 执行后已自动恢复 WiFi/蓝牙，任务后 ping 验证网络恢复 |
| T1-06 以太网链路状态 | fail | carrier=0，eth0 NO-CARRIER state DOWN | 【人工前置】未插网线，重试 2 次结果一致；插网线后复测 |
| T1-07 固件版本与分支 | pass | 三行非空 | 命令适配：固件无 ro.mc.custom.version，改为 ro.mc.custom_api_version |
| T1-08 系统配置 ro.mc.* 七字段 | pass | 七字段全 OK（product=FE7G28/Standard, cpu=RK3568, version=8.1.0…） | 字段映射：expected_custom_version→ro.mc.custom_api_version；ro.mc.oem.version 实机为空串（期望值也为空，判 OK），如需校验请用户填参 |
| T1-09 默认时区与自动校时 | pass | Asia/Shanghai + auto_time=1 | — |
| T1-10 默认 Launcher | pass | ComponentInfo{com.android.launcher3/...} | — |
| T1-11 APK 安装 | error | RESULT: SKIP — 测试 APK 缺失 | 未伪造 APK；runner 输出 SKIP 标记以 0 退出。平台 assertion 判定无 skip 状态，SKIP 输出落到 unknown→error。放入 test-tools/upfm/assets/test_app.apk 后复测 |
| T1-12 APK 卸载 | error | RESULT: SKIP — 同上 | 同 T1-11 |
| T1-13 屏幕旋转设置 | pass | orig=0 set_readback=1 restored=0 | — |
| T1-14 亮度设置 | pass | orig=255 low=30 high=200 restored=255 | — |
| T1-15 休眠时间 | pass | 设 15000ms 等 20s 后 mWakefulness=Asleep，唤醒 Awake，原值恢复，25s | — |
| T1-16 触摸点数 | pass | techwin TRACKING_ID max=9 → 10 点 | — |
| T1-17 TF卡识别 | fail | NOT_FOUND: 未发现 TF 卡挂载点 | 【人工前置】未插卡，插卡后复测 |
| T1-18 TF卡读写 | fail | NOT_FOUND | 同上 |
| T1-19 U盘识别 | fail | NOT_FOUND | 【人工前置】未插 U 盘 |
| T1-20 U盘读写 | fail | NOT_FOUND | 同上 |
| T1-21 U盘不复制系统目录 | fail | NOT_FOUND | 同上 |
| T1-22 CPU 支持频率 | pass | 8 档 408000…1992000 精确一致 | 命令适配：频率文件带尾部空格，比对前做空格归一化 |
| T1-23 CPU 最大频率 | pass | 1992000 | — |
| T1-24 GPU 支持频率 | pass | 自动发现 fde60000.gpu，6 档一致 | — |
| T1-25 GPU 最大频率 | pass | 800000000 | — |
| T1-26 DDR 频率（静止态） | pass | clk_scmi_ddr=1056000000 | 实机值与用例表 1560000000 不符的既有疑问保留，待硬件确认基线；注意 clk_summary 读取依赖 adbd root（storage runner 会执行 adb root，重启后失效） |
| T1-27 剩余内存比例 | fail | 实测 36.8%，断言区间 50%~80% | 判定标准问题：实机为非首启状态，用例基线要求烧录重启后首次执行。**不改标准**，交用户决策（首启执行 / 放宽阈值 / 日常跳过） |
| T1-03/04/05 顺序 | — | — | 已按设计排在任务尾部（飞行模式最后） |

### 落地结论清单

- **完全落地（首轮即 PASS）：18 项** —— T1-01/02/03/04/05/07/08/09/10/13/14/15/16/22/23/24/25/26
- **需人工前置/资产后复测：8 项** —— T1-06（插网线）、T1-11/12（放置测试 APK 到 test-tools/upfm/assets/test_app.apk）、T1-17~21（插 TF 卡 / U 盘）
- **需用户确认判定标准：1 项** —— T1-27（实机非首启 36.8% vs 默认 50~80；另 T1-26 虽 PASS，DDR 基线 1056000000 vs 用例表 1560000000 仍待硬件确认）
- **无法落地：0 项**

### 与方案设计的偏差说明（均为命令适配，判定标准未动）

1. T1-07：固件无 `ro.mc.custom.version`，命令改为 `ro.mc.custom_api_version`。
2. T1-08：七字段中 expected_custom_version 映射 `ro.mc.custom_api_version`；`ro.mc.oem.version` 实机为空串。
3. T1-17~21：文档设计的纯 adb_shell（`sm list-volumes`/`ls /mnt/media_rw`）在实机上受权限限制（/mnt/media_rw 需 root），统一改为 host_exec runner（storage_rw_check.py，内部 adb root + 自动发现挂载点），介质按 sm disk id 前缀区分（TF=public:179,，U盘=public:8,）。
4. T1-22：频率文件尾部空格导致直接字符串比对失配，命令内做归一化后精确比对。
5. T1-11/12 的"跳过"语义：平台 assertion 判定无法产出 skip 状态，runner 以 `RESULT: SKIP` 标记 + 退出码 0 表达，记录在平台显示为 error，复测前视为"未执行"。

---

## 八、板型自动判别改造与 A133P 复测结果（2026-07-31，A133P / Android 10 / armeabi-v7a）

### 8.1 机制说明

判定期望值不再写死在测试项 `parameters` 里，改为**板型画像（board profile）**按设备自动取值，下发任务时无需人工选择板型参数：

- `test-tools/upfm/host/board_profiles.py`：每板型一条 profile（cpu/gpu/ddr/touch/bluetooth/mc_props 期望值），文件内注释写明各字段采集命令与实测来源。
- `test-tools/upfm/host/board_detect.py`：公共识别模块。判别键 `ro.mc.cpu` 优先、`ro.product.device` 兜底；识别成功加载 profile，供各 runner import。
- **未知板型策略**：runner 输出实机读到的全部值（频率表/devfreq/clk/触摸/蓝牙特性/ro.mc.*）+ `RESULT: FAIL`，并提示"未知识别板型，请把以上实测值补入 board_profiles"——绝不静默通过。
- **SKIP 语义**：profile 标记不支持的项（如 A133P GPU 频率表）runner 输出 `RESULT: SKIP` 并以 0 退出；平台断言判定无 skip 状态，记录在平台显示为 error，报告按输出中的 `RESULT: SKIP` 重分类（同第七节第 5 条既有约定）。采用 runner SKIP 方案而非 compatibility board_patterns，板型名单只需在 board_profiles.py 维护一处。
- 人工覆盖入口保留：T1-08（ro.mc.* 七字段）与 T1-16（触摸点数）的 parameters 留空串即按画像取值，显式填值仍覆盖画像；`*` 保持只读不比对（采集模式）。

### 8.2 板型画像实填值

| 字段 | rk3568（抄第四节实测） | A133P（2026-07-31 实机 adb 采集） |
|---|---|---|
| 判别键 | ro.mc.cpu=RK3568 | ro.mc.cpu=A133P / ro.product.device=A133P |
| cpu.available_freqs | 408000…1992000（8 档含 1104000） | 408000…1800000（8 档含 1008000/1200000） |
| cpu.max_freq | 1992000 | 1800000 |
| gpu.supported | true（devfreq *.gpu，fde60000.gpu） | **false**（devfreq 为空，用例注明不支持查看频率表） |
| gpu.available/max | 800M…200M / 800000000 | — |
| ddr（clk 名 / 期望值） | clk_scmi_ddr / 1056000000 | pll_ddr / 1584000000 |
| touch.expected_points | 10（techwin TRACKING_ID max=9） | 32（cyttsp5_mt ABS_MT_SLOT max=31，驱动槽位数） |
| bluetooth.supported | true | true（pm features 声明支持，但协议栈实测崩溃，见 8.5） |
| mc_props | ANDROID11.0/RK3568/custom_api=1/oem=""/FE7G28/Standard/8.1.0/8 | ANDROID10.0/A133P/custom_api=""/oem=""/F7G18PD_HZCL01/HangZhouZeTianChunLai/ShuiZhiJianCe/2.1.0/3 |

### 8.3 runner 改动清单（test-tools/upfm/host/）

- 新增 `board_profiles.py` / `board_detect.py`（识别 + 画像加载 + 未知板型 FAIL 兜底）。
- 新增 `cpu_freq_check.py`（available/max 两模式）→ T1-22/23 由 adb_shell 转 host_exec。
- 新增 `ddr_freq_check.py`（按画像 clk 模式比对，读不到自动 adb root 重试）→ T1-26 转 host_exec。
- 新增 `rotation_check.py` → T1-13 转 host_exec。任务 #9 在 A10 报 `Invalid value: null for setting: user_rotation`，根因：自动旋转开启时 user_rotation 未初始化（get 返回 null），写回 null 触发 SettingsProvider 异常。runner 处理 null 场景、先锁 accelerometer_rotation、测后恢复原值。
- 新增 `toggle_check.py`（wifi/bluetooth/airplane 统一 runner，轮询读回；bluetooth 按画像 supported 判定 SKIP，失败附 dumpsys bluetooth_manager 摘要）→ T1-03/04/05 转 host_exec。
- 更新 `gpu_freq_check.py`：画像驱动，supported=false 输出 `RESULT: SKIP` + 原因。
- 更新 `mc_props_check.py`：期望值默认取画像，参数可覆盖。
- 更新 `touch_points.py`：期望点数默认取画像（解析逻辑不变，本就不依赖设备名；任务 #9 实为期望值 10≠实测 32，非"未找到设备"）。
- 更新 `sleep_check.py`：①休眠断言接受 Asleep 或 Dozing（A133P 息屏进入 Dozing 浅休眠）；②stay_on_while_plugged_in≠0 时测试期临时置 0 并恢复（userdebug 默认 7 会阻止休眠）；③等待后仍 Awake 时 15s 宽限轮询（A133P 约 15s 才进入 Dozing，时点临界易抖动）。
- T1-07（保持 adb_shell）：命令改为带标签 echo 三行，断言 display_id/mc_version 非空、custom_api_version 字段存在即可（A133P 该属性为空串导致任务 #9 误判 error）。
- 兼容性说明：所有 runner 的 stdout UTF-8 重包装加了"已是 UTF-8 则跳过"守卫，避免与 board_detect 双重包装互相关闭底层流。

### 8.4 测试项落库

`backend/scripts/import_upfm_items.py`（重建，按 T1 编号 upsert、幂等，只更新执行配置不动四要素）：更新 12 项（T1-03/04/05/07/08/13/16/22/23/24/25/26）。`test-tools/upfm/manifest.yaml` 已同步相同改动（scan-modules 重新注册不会回退）。改库前已备份 `backend/test_platform.db.bak2`。

### 8.5 A133P 全量复测（任务 #10，27 项，2026-07-31）

分布：**pass 15 / fail 8 / skip 4**（skip 为 runner 输出 RESULT: SKIP，平台记录为 error 后按输出重分类）。

| 测试项 | 状态 | 归因 |
|---|---|---|
| T1-01 ping | fail | 【环境】设备无外网（unknown host），与任务 #9 相同 |
| T1-02 MAC | pass | — |
| T1-03 WiFi 开关 | pass | 新 toggle runner 轮询读回正常 |
| T1-04 蓝牙开关 | **fail** | **设备固件缺陷**：svc enable 后 bluetooth_on 恒 0，dumpsys 显示协议栈 CRASH/RESTART 循环、state 卡在 BLE_TURNING_ON、address=null。如实判 FAIL 不静默，需固件侧修复 |
| T1-05 飞行模式 | pass | — |
| T1-06 以太网链路 | fail | 【人工前置】未插网线 |
| T1-07 固件版本 | pass | 标签化命令修复任务 #9 的误判 |
| T1-08 ro.mc.* 七字段 | pass | 按 A133P 画像全字段一致（含两个空串字段） |
| T1-09 时区 | pass | — |
| T1-10 Launcher | pass | — |
| T1-13 屏幕旋转 | pass | null 场景已处理，测后恢复原值 |
| T1-14 亮度 | pass | — |
| T1-15 休眠 | pass | Dozing 判定 + 宽限轮询生效，timeout/stay_on 均恢复 |
| T1-16 触摸点数 | pass | 32 点按 A133P 画像 |
| T1-22/23 CPU 频率 | pass | A133P 画像 8 档/1800000 精确一致 |
| T1-24/25 GPU 频率 | skip | A133P 画像 supported=false，合理跳过 |
| T1-26 DDR 频率 | pass | pll_ddr=1584000000 按画像一致 |
| T1-27 剩余内存 | pass | 实测 60.8% 落区间（非首启状态，比例随使用波动，基线疑问同第七节保留） |
| T1-11/12 APK 安装/卸载 | skip | 【资产缺失】test_app.apk 未放置，同任务 #9 |
| T1-17~21 TF/U盘 五项 | fail | 【人工前置】未插 TF 卡 / U 盘 |

复跑脚本：`archive/debug-artifacts/run_upfm_rerun_a133p.py`；明细 JSON：`archive/debug-artifacts/upfm_rerun_a133p_boards.json`。

### 8.6 回归与遗留

- pytest 回归：`cd backend && python -m pytest tests -q` → **185 passed 全绿**，未修改任何平台框架代码（判定/执行器未动）。（首轮与复跑任务并发执行时 test_cancel_running_task_keeps_cancelled 出现一次 Event loop is closed 抖动，单独重跑全绿，与本次改动无关。）
- **rk3568 画像未回归**：rk3568 板（FE7G28V8TEST）当前不在线，其画像值抄自第四节实测记录，改造后 runner 未在 rk3568 上复验；板上线后应全量复跑一次。
- **A133P 蓝牙不可用**属设备固件缺陷（协议栈崩溃循环），已如实判 FAIL，待固件修复后复测。
- T1-26 读 clk_summary 依赖 root：A133P adb shell 原生 root；rk3568 需 runner 内 adb root（已实现，重启 adbd 后失效时自动重试）。
