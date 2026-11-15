"""T-09 自定义参数契约校验（R13/R14，契约 task-execution §2）。

custom_parameters 精确规则：
- 外层键为已选 item_id 的十进制字符串，内层为扁平参数对象；
- 内层参数名必须存在于该项 parameters_schema.properties，缺 schema 时不接受自定义参数；
- 值只允许 string、有限 number、boolean；禁止 object、array、null；0、false、"" 原样保存；
- 参数名匹配 ^[A-Za-z_][A-Za-z0-9_]{0,63}$，字符串最长 1000，禁止 NUL、CR、LF；
- 非 URL 字符串拒绝 ;、|、>、<、$、反引号等 shell 控制符；
- 合法 http/https URL 允许路径、查询中的 ?、&、=、/，但不得含凭据、控制符或 shell 控制符。

创建侧（task_creation）调用 validate_custom_parameters 做全量校验；
执行侧（execution_engine）调用 validate_param_value 做值级兜底，防历史脏数据绕过。
"""
import math
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

# 参数名：字母/下划线开头，仅字母数字下划线，总长 1～64
PARAM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# 字符串值长度上限
PARAM_VALUE_MAX_LENGTH = 1000
# 字符串中禁止出现的控制字符（NUL/CR/LF）
_CONTROL_CHARS = ("\x00", "\r", "\n")
# 非 URL 字符串禁止的 shell 控制符（含引号与 &，防命令拼接/后台执行）
_SHELL_METACHARS = set(";|><$`&'\"")
# URL 中同样禁止的字符（& 在查询串中合法，故从 URL 集剔除）
_URL_FORBIDDEN_CHARS = set(";|><$`'\"")


class ParamValidationError(Exception):
    """参数契约校验失败：field 为精确字段路径，reason 为原因（对应 details）。"""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


def _check_string_value(field: str, value: str) -> Optional[str]:
    """字符串值字符级校验：合法 URL 放行查询字符，其余拒绝 shell 控制符。返回错误或 None。"""
    if len(value) > PARAM_VALUE_MAX_LENGTH:
        return f"字符串长度超过 {PARAM_VALUE_MAX_LENGTH}"
    for ch in _CONTROL_CHARS:
        if ch in value:
            return "字符串禁止包含 NUL、CR、LF 控制字符"
    if value.startswith(("http://", "https://")):
        try:
            parts = urlsplit(value)
        except ValueError:
            return "URL 格式不合法"
        if not parts.netloc:
            return "URL 缺少主机名"
        if parts.username is not None or parts.password is not None:
            return "URL 不得包含凭据（user:pass@host 形式）"
        bad = sorted(_URL_FORBIDDEN_CHARS & set(value))
        if bad:
            return f"URL 包含非法字符 {' '.join(bad)}（禁止 shell 控制符）"
        return None
    bad = sorted(_SHELL_METACHARS & set(value))
    if bad:
        return f"参数值包含非法字符 {' '.join(bad)}（为防止命令注入，禁止 shell 元字符）"
    return None


def validate_param_value(name: str, value: Any) -> Optional[str]:
    """值级校验（执行侧兜底）：合法返回 None，非法返回错误信息。

    值只允许 string、有限 number、boolean；禁止 object、array、null。
    """
    if value is None or isinstance(value, (dict, list)):
        return "不允许嵌套对象、数组或null"
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return "数值必须为有限数"
        return None
    if isinstance(value, str):
        return _check_string_value(name, value)
    return "值只允许 string、有限 number、boolean"


def validate_custom_parameters(
    custom_parameters: Dict[str, Any],
    selected_item_ids: list,
    items_by_id: Dict[int, Any],
) -> None:
    """custom_parameters 全量契约校验，非法抛 ParamValidationError。

    - custom_parameters：请求体原始嵌套结构（外层键为字符串）；
    - selected_item_ids：已选测试项 ID 列表；
    - items_by_id：已选测试项 ORM 对象映射（用于查 parameters_schema）。
    """
    selected = set(selected_item_ids)
    for outer_key, group in (custom_parameters or {}).items():
        field_outer = f"custom_parameters.{outer_key}"
        # 外层键必须是已选 item_id 的十进制字符串
        if not (isinstance(outer_key, str) and outer_key.isdecimal() and int(outer_key) in selected):
            raise ParamValidationError(field_outer, "外层键必须是已选测试项 ID 的十进制字符串")
        item_id = int(outer_key)
        item = items_by_id.get(item_id)
        schema = getattr(item, "parameters_schema", None) if item is not None else None
        properties = schema.get("properties") if isinstance(schema, dict) else None
        if not isinstance(properties, dict) or not properties:
            raise ParamValidationError(field_outer, "该测试项未定义 parameters_schema，不接受自定义参数")
        if not isinstance(group, dict):
            raise ParamValidationError(field_outer, "内层必须是扁平参数对象（不允许数组、标量或null）")
        for name, value in group.items():
            field = f"{field_outer}.{name}"
            if not PARAM_NAME_RE.match(name):
                raise ParamValidationError(
                    field, "参数名格式不合法（字母/下划线开头，仅字母数字下划线，最长 64 字符）"
                )
            if name not in properties:
                raise ParamValidationError(field, "参数名不存在于该项 parameters_schema.properties")
            error = validate_param_value(name, value)
            if error:
                raise ParamValidationError(field, error)
