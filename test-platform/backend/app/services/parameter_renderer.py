import re
import logging
from typing import Dict, Any

from app.models import Device

logger = logging.getLogger(__name__)


class ParameterRenderer:
    """根据设备画像渲染测试项参数模板。"""

    # 支持的占位符模式：{device.ddr_info.total_mb} 或 {device.cpu_abi}
    PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.\s\+\-\*/%()]*)\}")

    @classmethod
    def render(cls, device: Device, template_value: Any, extra_context: Dict[str, Any] = None) -> Any:
        """渲染单个参数值。"""
        if not isinstance(template_value, str):
            return template_value

        context = {
            "device": cls._build_device_context(device),
            **(extra_context or {})
        }

        # 如果整个字符串都是占位符，尝试计算表达式
        match = cls.PLACEHOLDER_PATTERN.fullmatch(template_value.strip())
        if match:
            expr = match.group(1).strip()
            result = cls._evaluate(expr, context)
            return result if result is not None else template_value

        # 否则只替换占位符部分
        def _replacer(m: re.Match) -> str:
            expr = m.group(1).strip()
            result = cls._evaluate(expr, context)
            return str(result) if result is not None else m.group(0)

        return cls.PLACEHOLDER_PATTERN.sub(_replacer, template_value)

    @classmethod
    def render_parameters(cls, device: Device, parameters: Dict[str, Any],
                          extra_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """渲染整个参数字典。"""
        rendered = {}
        for key, value in parameters.items():
            rendered[key] = cls.render(device, value, extra_context)
        return rendered

    @classmethod
    def _build_device_context(cls, device: Device) -> Dict[str, Any]:
        """构建设备画像上下文。"""
        return {
            "serial_number": device.serial_number,
            "model": device.model,
            "brand": device.brand,
            "android_version": device.android_version,
            "sdk_version": device.sdk_version,
            "cpu_abi": device.cpu_abi,
            "resolution": device.resolution,
            "battery_level": device.battery_level,
            "board": device.board,
            "hardware": device.hardware,
            "ddr_info": device.ddr_info or {},
            "emmc_info": device.emmc_info or {},
            "wifi_chip": device.wifi_chip,
            "bt_chip": device.bt_chip,
            "eth_interfaces": device.eth_interfaces or [],
            "features": device.features or []
        }

    @classmethod
    def _evaluate(cls, expr: str, context: Dict[str, Any]) -> Any:
        """安全地计算占位符表达式。"""
        # 1. 尝试作为纯属性路径解析：device.ddr_info.total_mb
        value = cls._resolve_path(expr, context)
        if value is not None:
            return value

        # 2. 尝试作为简单算术表达式解析（仅允许 device.xxx 和数字/运算符）
        try:
            # 识别表达式中的 device.xxx 属性引用，仅替换属性部分
            # 例如 "device.ddr_info.total_mb // 4" -> "1960 // 4"
            path_pattern = re.compile(r"\b(device\.[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\b")

            def _resolve_placeholder(m: re.Match) -> str:
                path = m.group(1).strip()
                val = cls._resolve_path(path, context)
                if val is None:
                    return "None"
                if isinstance(val, (int, float)):
                    return str(val)
                # 字符串值需要加引号
                return repr(str(val))

            expr_with_values = path_pattern.sub(_resolve_placeholder, expr)

            # 只允许安全字符
            if not re.match(r"^[\d\s+\-*/%().,None'\"]+$", expr_with_values):
                logger.warning("表达式包含不安全字符: %s", expr_with_values)
                return None

            return eval(expr_with_values, {"__builtins__": {}}, {})
        except Exception as exc:
            logger.warning("计算表达式失败 '%s': %s", expr, exc)
            return None

    @classmethod
    def _resolve_path(cls, expr: str, context: Dict[str, Any]) -> Any:
        """按点号路径解析值。"""
        parts = [p.strip() for p in expr.split(".")]
        value = context.get(parts[0])

        for part in parts[1:]:
            if value is None:
                return None
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

        return value
