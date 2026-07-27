import re
import os
import json
import inspect
import logging
import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from enum import Enum
from app.services.device import ADBService, stream_process_output
from app.services.parameter_renderer import ParameterRenderer
from app.services.judgement_engine import JudgementEngine
from app.services.memory_engine import BaselineService
from app.services.knowledge_judge_context import JudgeKnowledgeContext, format_context_for_llm
from app.database import AsyncSessionLocal
from app.models import TestItem, Device
from app.config import get_settings

settings = get_settings()

# 自定义参数值中禁止出现的 shell 元字符（防命令注入）。
# 用户在创建任务时提交的 custom_parameters 会被原样拼入 shell 命令串，
# 允许字母数字与常见路径/URL字符，拒绝可改变命令结构的元字符。
FORBIDDEN_PARAM_CHARS = set('`$&|;<>"\'\n\r')


def validate_custom_param_value(value: Any) -> Optional[str]:
    """校验用户提交的自定义参数值，含有 shell 元字符时返回错误信息，合法返回 None。"""
    text = str(value)
    bad = sorted(FORBIDDEN_PARAM_CHARS & set(text))
    if bad:
        return f"参数值包含非法字符 {' '.join(bad)}（为防止命令注入，禁止 shell 元字符）"
    return None


async def _emit_output(on_output: Optional[Callable[[str], Any]], text: str):
    """调用实时输出回调（同步/异步均可），on_output 为 None 时跳过。"""
    if on_output is None:
        return
    result = on_output(text)
    if inspect.isawaitable(result):
        await result


class ExecutionResult:
    """执行结果"""
    def __init__(self, status: str, output: str = "", fail_reason: str = "", 
                 execution_time: int = 0, extracted_data: Optional[Dict] = None):
        self.status = status  # pass/fail/skip/error/timeout
        self.output = output
        self.fail_reason = fail_reason
        self.execution_time = execution_time
        self.extracted_data = extracted_data or {}


class ExecutionEngine(ABC):
    """执行引擎抽象基类"""
    
    @abstractmethod
    async def execute(self, device: Device, item: TestItem,
                     custom_params: Optional[Dict] = None,
                     on_output: Optional[Callable[[str], Any]] = None) -> ExecutionResult:
        """执行测试项，on_output 不为 None 时实时回调输出行"""
        pass
    
    async def validate(self, device: Device, item: TestItem) -> tuple:
        """验证兼容性"""
        import re
        compatibility = item.compatibility or {}

        # 检查Android最低版本
        if "min_android_version" in compatibility:
            if device.android_version:
                try:
                    device_version = float(device.android_version)
                    min_version = float(compatibility["min_android_version"])
                    if device_version < min_version:
                        return False, f"Android版本过低: 需要{min_version}+, 实际{device_version}"
                except ValueError:
                    pass

        # 检查Android最高版本
        if "max_android_version" in compatibility:
            if device.android_version:
                try:
                    device_version = float(device.android_version)
                    max_version = float(compatibility["max_android_version"])
                    if device_version > max_version:
                        return False, f"Android版本过高: 需要<={max_version}, 实际{device_version}"
                except ValueError:
                    pass

        # 检查架构
        if "supported_archs" in compatibility:
            if device.cpu_abi and device.cpu_abi not in compatibility["supported_archs"]:
                return False, f"架构不兼容: 需要{compatibility['supported_archs']}, 实际{device.cpu_abi}"

        # 检查设备能力特征
        if "required_features" in compatibility:
            features = device.features or []
            for feature in compatibility["required_features"]:
                if feature not in features:
                    return False, f"设备缺少必要能力: {feature}"

        # 检查主板平台
        if "board_patterns" in compatibility:
            board = device.board or ""
            if not any(re.search(pattern, board, re.IGNORECASE) for pattern in compatibility["board_patterns"]):
                return False, f"主板平台不兼容: 需要匹配{compatibility['board_patterns']}, 实际{board}"

        # 检查硬件名称
        if "hardware_patterns" in compatibility:
            hardware = device.hardware or ""
            if not any(re.search(pattern, hardware, re.IGNORECASE) for pattern in compatibility["hardware_patterns"]):
                return False, f"硬件名称不兼容: 需要匹配{compatibility['hardware_patterns']}, 实际{hardware}"

        return True, ""
    
    def _render_params(self, device: Device, item: TestItem,
                       custom_params: Optional[Dict] = None,
                       extra_params: Optional[Dict] = None) -> str:
        """渲染设备画像参数与自定义参数，替换命令中的 {placeholder} 占位符。

        合并顺序：设备画像渲染参数 < custom_params < extra_params（后者覆盖前者）。
        - {host_tool_dir} 未显式提供时，默认解析为配置 TEST_TOOLS_PATH 的绝对路径，
          测试项无需再硬编码绝对路径；
        - custom_params 来自用户任务创建请求，做 shell 元字符校验，防止命令注入。
        返回替换后的命令（可能仍含未替换占位符，由 _check_placeholders 检查）。
        """
        command = item.exec_command
        rendered_params = ParameterRenderer.render_parameters(device, item.parameters or {})
        params = {**rendered_params, **(custom_params or {})}
        if extra_params:
            params.update(extra_params)

        if "host_tool_dir" not in params:
            params["host_tool_dir"] = os.path.abspath(settings.TEST_TOOLS_PATH)

        if custom_params:
            for key, value in custom_params.items():
                error = validate_custom_param_value(value)
                if error:
                    raise ValueError(f"自定义参数 {key} 校验失败: {error}")

        for key, value in params.items():
            command = command.replace(f"{{{key}}}", str(value))
        return command

    def _check_placeholders(self, command: str) -> Optional[str]:
        """检查命令中是否还有未替换的占位符，有则返回错误信息，否则返回 None。"""
        if re.search(r"\{[a-zA-Z_][a-zA-Z0-9_.\s+\-*/%()]*\}", command):
            return f"命令包含未替换的占位符，请检查设备画像或测试项参数配置: {command}"
        return None

    def parse_result(self, output: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """解析执行结果"""
        result = {"status": "unknown", "fail_reason": "", "extracted_data": {}}
        
        # 检查失败
        if config.get("fail_pattern"):
            if re.search(config["fail_pattern"], output, re.IGNORECASE):
                result["status"] = "fail"
                result["fail_reason"] = self._extract_fail_reason(output)
                return result
        
        # 检查成功
        if config.get("pass_pattern"):
            if re.search(config["pass_pattern"], output, re.IGNORECASE):
                result["status"] = "pass"
        else:
            # 默认成功
            result["status"] = "pass"
        
        # 提取数据
        if config.get("extract_pattern"):
            matches = re.findall(config["extract_pattern"], output)
            if matches:
                result["extracted_data"]["values"] = matches
        
        return result
    
    def _extract_fail_reason(self, output: str) -> str:
        """提取失败原因"""
        # 查找包含error/fail的行
        lines = output.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['error', 'fail', 'exception', 'crash']):
                return line.strip()[:500]
        
        # 返回最后几行
        if lines:
            return lines[-1].strip()[:500]
        return "未知错误"

    # ADB 常见失败模式：设备离线、未找到、无权限、二进制缺失等应直接判 fail
    ADB_FAILURE_PATTERNS = [
        r"device\s+['\"]?[^'\"\n]*['\"]?\s+not found",
        r"error:\s*device\s+offline",
        r"error:\s*no devices/emulators found",
        r"adb\.exe:\s*device.*not found",
        r"no such file or directory",
        r"permission denied",
    ]

    async def _load_baselines(self, device: Device, item: TestItem) -> list:
        """加载当前设备型号在当前测试项上的基线。"""
        if not device.model:
            return []
        try:
            async with AsyncSessionLocal() as db:
                return await BaselineService.get_baselines(
                    db, device_model=device.model, item_id=item.id
                )
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.warning("加载基线失败: %s", exc)
            return []

    async def _load_knowledge_context(self, device: Device, item: TestItem) -> str:
        """加载与测试项相关的知识库上下文，用于 AI 判定。"""
        try:
            async with AsyncSessionLocal() as db:
                context = await JudgeKnowledgeContext.build(db, device, item, limit=3)
                return format_context_for_llm(context)
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.warning("加载知识库判定上下文失败: %s", exc)
            return ""

    async def _judge_result(
        self,
        device: Device,
        item: TestItem,
        output: str,
        returncode: int
    ) -> Dict[str, Any]:
        """调用判定引擎对结果进行判定。"""
        # 默认 judgement_type 为 assertion，但如果没有条件规则，仍走原有正则解析
        judgement_type = item.judgement_type or "assertion"
        rules = item.conditional_rules or {}
        rubric_criteria = item.rubric_criteria or {}

        # 先识别 ADB 设备级失败（离线、未找到等），避免落到 unknown
        combined = output + "\n" + (str(returncode) if returncode is not None else "")
        for pattern in self.ADB_FAILURE_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                return {
                    "status": "fail",
                    "fail_reason": f"ADB 设备异常: {output.strip()[-200:]}",
                    "extracted_data": {"adb_error": output.strip()[-500:], "returncode": returncode}
                }

        # 如果没有条件规则/Rubrics/AI 上下文，且 judgement_type 不是 ai_fallback，
        # 则回退到原有正则解析
        if judgement_type == "assertion" and not rules.get("conditions"):
            return self.parse_result(output, item.result_parse or {})

        # 预加载基线（用于 Rubric 基线判定）
        baselines = await self._load_baselines(device, item)

        # 预加载知识库上下文（用于 AI 判定）
        knowledge_context = ""
        if judgement_type == "ai_fallback":
            knowledge_context = await self._load_knowledge_context(device, item)

        device_context = {
            "serial_number": device.serial_number,
            "model": device.model,
            "brand": device.brand,
            "android_version": device.android_version,
            "sdk_version": device.sdk_version,
            "cpu_abi": device.cpu_abi,
            "board": device.board,
            "hardware": device.hardware,
            "ddr_info": device.ddr_info or {},
            "emmc_info": device.emmc_info or {},
            "wifi_chip": device.wifi_chip,
            "bt_chip": device.bt_chip,
            "eth_interfaces": device.eth_interfaces or [],
            "features": device.features or []
        }

        # 构造基线字典：metric_name -> baseline 对象
        baselines_dict = {}
        if baselines:
            for b in baselines:
                baselines_dict[b.metric_name] = {
                    "avg_value": b.avg_value,
                    "min_value": b.min_value,
                    "max_value": b.max_value,
                    "sample_count": b.sample_count,
                }

        # spec 用于 conditional_rules 中的 target 解析，如 spec:ddr_total_mb
        spec = {}
        if device.ddr_info:
            spec.update(device.ddr_info)
        if device.emmc_info:
            spec.update(device.emmc_info)

        ai_context = item.result_parse.get("ai_context", "") if item.result_parse else ""

        engine = JudgementEngine()
        result = await engine.judge(
            output=output,
            returncode=returncode,
            item_name=item.name,
            item_description=item.description or "",
            judgement_type=judgement_type,
            rules=rules,
            rubric_criteria=rubric_criteria,
            device_context=device_context,
            ai_context=ai_context,
            spec=spec,
            baselines=baselines_dict,
            knowledge_context=knowledge_context
        )

        return {
            "status": result.status,
            "fail_reason": result.fail_reason,
            "extracted_data": {
                **(result.metrics or {}),
                "judgement": result.to_dict()
            }
        }


class AdbShellEngine(ExecutionEngine):
    """ADB Shell命令执行引擎"""
    
    def __init__(self):
        self.adb = ADBService()
    
    async def execute(self, device: Device, item: TestItem,
                     custom_params: Optional[Dict] = None,
                     on_output: Optional[Callable[[str], Any]] = None) -> ExecutionResult:
        """执行ADB Shell命令"""
        start_time = datetime.now(timezone.utc)

        # 构建命令：渲染参数并替换占位符
        command = self._render_params(device, item, custom_params)

        # 检查是否还有未替换的占位符
        placeholder_error = self._check_placeholders(command)
        if placeholder_error:
            return ExecutionResult(
                status="error",
                output=command,
                fail_reason=placeholder_error,
                execution_time=0
            )

        # 执行命令（on_output 不为 None 时逐行实时回调输出）
        timeout = item.timeout or 300
        stdout, stderr, returncode = await self.adb.execute_shell(
            device.serial_number, command, timeout, on_output=on_output
        )

        execution_time = int((datetime.now(timezone.utc) - start_time).total_seconds())

        # adb 子进程等待超时，标记为 timeout 状态而非走判定逻辑
        if returncode == -1 and "Timeout after" in stderr:
            return ExecutionResult(
                status="timeout",
                output=stdout + "\n" + stderr,
                fail_reason=f"执行超时（{timeout}秒）",
                execution_time=execution_time
            )

        # 解析结果
        parsed = await self._judge_result(device, item, stdout + "\n" + stderr, returncode)

        return ExecutionResult(
            status=parsed["status"],
            output=stdout + "\n" + stderr,
            fail_reason=parsed["fail_reason"],
            execution_time=execution_time,
            extracted_data=parsed["extracted_data"]
        )


class PushExecEngine(ExecutionEngine):
    """推送后执行引擎"""

    def __init__(self):
        self.adb = ADBService()

    async def execute(self, device: Device, item: TestItem,
                     custom_params: Optional[Dict] = None,
                     on_output: Optional[Callable[[str], Any]] = None) -> ExecutionResult:
        """推送工具并执行"""
        import os
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models import TestTool

        start_time = datetime.now(timezone.utc)
        outputs = []

        async def log(text: str):
            """累积输出并实时回调（保持日志文件/前端流与最终 output 一致）。"""
            outputs.append(text)
            await _emit_output(on_output, text + "\n")

        # 1. 加载并推送工具
        tool_remote_path = None
        if item.tool_id:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(TestTool).where(TestTool.id == item.tool_id))
                tool = result.scalar_one_or_none()

            if not tool:
                return ExecutionResult(
                    status="error",
                    output="",
                    fail_reason=f"工具不存在: tool_id={item.tool_id}",
                    execution_time=0
                )

            if not os.path.exists(tool.file_path):
                return ExecutionResult(
                    status="error",
                    output="",
                    fail_reason=f"工具文件不存在: {tool.file_path}",
                    execution_time=0
                )

            push_target = item.push_target or "/data/local/tmp"
            tool_name = os.path.basename(tool.filename or tool.file_path)
            tool_remote_path = f"{push_target}/{tool_name}"

            stdout, stderr, returncode = await self.adb.push_file(
                device.serial_number, tool.file_path, tool_remote_path
            )
            await log(f"[PUSH] {tool.file_path} -> {tool_remote_path}")
            await log(stdout)
            if stderr:
                await log(stderr)

            if returncode != 0:
                return ExecutionResult(
                    status="error",
                    output="\n".join(outputs),
                    fail_reason=f"推送工具失败，返回码: {returncode}",
                    execution_time=int((datetime.now(timezone.utc) - start_time).total_seconds())
                )

            # 添加执行权限
            chmod_stdout, chmod_stderr, chmod_rc = await self.adb.execute_shell(
                device.serial_number, f"chmod +x {tool_remote_path}", timeout=30
            )
            await log(chmod_stdout)
            if chmod_stderr:
                await log(chmod_stderr)
            if chmod_rc != 0:
                return ExecutionResult(
                    status="error",
                    output="\n".join(outputs),
                    fail_reason=f"chmod +x 失败，返回码: {chmod_rc}",
                    execution_time=int((datetime.now(timezone.utc) - start_time).total_seconds())
                )

        # 2. 渲染命令
        extra_params = {"tool": tool_remote_path} if tool_remote_path else None
        command = self._render_params(device, item, custom_params, extra_params=extra_params)

        # 检查是否还有未替换的占位符
        placeholder_error = self._check_placeholders(command)
        if placeholder_error:
            return ExecutionResult(
                status="error",
                output="\n".join(outputs),
                fail_reason=placeholder_error,
                execution_time=int((datetime.now(timezone.utc) - start_time).total_seconds())
            )

        # 3. 执行命令（on_output 不为 None 时逐行实时回调，stdout/stderr 不再重复回调）
        timeout = item.timeout or 300
        await log(f"[EXEC] {command}")
        stdout, stderr, returncode = await self.adb.execute_shell(
            device.serial_number, command, timeout, on_output=on_output
        )
        outputs.append(stdout)
        if stderr:
            outputs.append(stderr)

        execution_time = int((datetime.now(timezone.utc) - start_time).total_seconds())

        # adb 子进程等待超时，标记为 timeout 状态而非走判定逻辑
        if returncode == -1 and "Timeout after" in stderr:
            return ExecutionResult(
                status="timeout",
                output="\n".join(outputs),
                fail_reason=f"执行超时（{timeout}秒）",
                execution_time=execution_time
            )

        # 4. 解析结果
        parsed = await self._judge_result(device, item, "\n".join(outputs), returncode)

        return ExecutionResult(
            status=parsed["status"],
            output="\n".join(outputs),
            fail_reason=parsed["fail_reason"],
            execution_time=execution_time,
            extracted_data=parsed["extracted_data"]
        )


class HostExecEngine(ExecutionEngine):
    """本地执行引擎（PC端执行）"""

    @staticmethod
    async def _terminate_process(process):
        """终止子进程：先 terminate，超时后 kill（Windows 上 terminate 即 kill）。"""
        if process is None or process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    @staticmethod
    def _extract_json_from_output(output: str) -> Optional[Dict[str, Any]]:
        """从命令输出中提取最后一个独立的 JSON 对象。"""
        # 从后往前尝试每一个 '{' 位置，返回第一个能解析为 dict 的 JSON
        for start in range(len(output) - 1, -1, -1):
            if output[start] != "{":
                continue
            candidate = output[start:]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
        return None

    async def execute(self, device: Device, item: TestItem,
                     custom_params: Optional[Dict] = None,
                     on_output: Optional[Callable[[str], Any]] = None) -> ExecutionResult:
        """在PC端执行命令"""
        start_time = datetime.now(timezone.utc)
        
        # 构建命令：渲染参数并替换占位符（注入设备序列号 {serial}）
        command = self._render_params(
            device, item, custom_params,
            extra_params={"serial": device.serial_number}
        )

        # 检查是否还有未替换的占位符
        placeholder_error = self._check_placeholders(command)
        if placeholder_error:
            return ExecutionResult(
                status="error",
                output=command,
                fail_reason=placeholder_error,
                execution_time=0
            )

        # 在PC端执行
        process = None
        timed_out = False
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            timeout = item.timeout or 300
            if on_output is None:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                stdout_str = stdout.decode('utf-8', errors='ignore')
                stderr_str = stderr.decode('utf-8', errors='ignore')
            else:
                # 逐行读取并实时回调（超时/取消同样向上传播，由下方异常处理终止进程）
                stdout_str, stderr_str = await stream_process_output(process, timeout, on_output)

            returncode = process.returncode

        except asyncio.TimeoutError:
            returncode = -1
            timed_out = True
            stdout_str = ""
            stderr_str = f"Timeout after {item.timeout} seconds"
            # 超时必须终止底层子进程，避免进程残留
            await self._terminate_process(process)
        except asyncio.CancelledError:
            # 任务取消时终止子进程后再向上传播
            await self._terminate_process(process)
            raise
        except Exception as e:
            returncode = -1
            stdout_str = ""
            stderr_str = str(e)
        finally:
            # Windows ProactorEventLoop 下，communicate() 被 cancel/超时打断后
            # 管道 transport 可能不自动关闭并产生资源告警；正规 terminate/kill
            # 之后这里再兜底关闭一次，属已知平台 workaround。
            if process is not None and getattr(process, "_transport", None) is not None:
                process._transport.close()

        execution_time = int((datetime.now(timezone.utc) - start_time).total_seconds())

        # asyncio.wait_for 超时路径，标记为 timeout 状态而非走判定逻辑
        combined_output = stdout_str + "\n" + stderr_str
        if timed_out:
            return ExecutionResult(
                status="timeout",
                output=combined_output,
                fail_reason=f"执行超时（{item.timeout or 300}秒）",
                execution_time=execution_time
            )

        # 解析结果
        parsed = await self._judge_result(device, item, combined_output, returncode)

        # 如果测试项输出包含独立 JSON 块（运行器标准输出），将其合并到 extracted_data
        extracted_data = parsed.get("extracted_data") or {}
        json_data = self._extract_json_from_output(combined_output)
        if json_data:
            extracted_data = {**extracted_data, **json_data}

        return ExecutionResult(
            status=parsed["status"],
            output=combined_output,
            fail_reason=parsed["fail_reason"],
            execution_time=execution_time,
            extracted_data=extracted_data
        )


class EngineFactory:
    """执行引擎工厂"""
    
    _engines = {
        "adb_shell": AdbShellEngine,
        "push_exec": PushExecEngine,
        "host_exec": HostExecEngine,
    }
    
    @classmethod
    def get_engine(cls, exec_type: str) -> ExecutionEngine:
        """获取执行引擎"""
        engine_class = cls._engines.get(exec_type)
        if not engine_class:
            raise ValueError(f"未知的执行类型: {exec_type}")
        return engine_class()
    
    @classmethod
    def register_engine(cls, exec_type: str, engine_class: type):
        """注册新的执行引擎"""
        cls._engines[exec_type] = engine_class
