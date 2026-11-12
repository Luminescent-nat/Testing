"""知识库条目转测试资产服务。"""
import hashlib
import json
import logging
import re
from typing import Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import KnowledgeEntry, TestModule, TestItem, FailurePattern, Baseline
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ========== 可执行 conditional_rules 唯一 schema（契约 knowledge-rules-v1.0 §1）==========
# 与 app/services/judgement_engine.py 的执行期校验保持同一事实：对象根 + conditions 数组。
VALID_OPERATORS = frozenset({"eq", "gt", "gte", "lt", "lte", "approx_ratio", "contains"})
OPERATOR_ALIASES = {"=": "eq", "==": "eq", ">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}
_ALLOWED_RULE_KEYS = frozenset({"conditions", "returncode_zero"})
_ALLOWED_CONDITION_KEYS = frozenset({"source", "operator", "target", "tolerance", "on_fail"})
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_TOLERANCE_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
_NUMERIC_OPERATORS = frozenset({"gt", "gte", "lt", "lte", "approx_ratio"})


class RuleValidationError(ValueError):
    """conditional_rules 结构非法。field 为契约 details.field 路径，reason 为安全摘要。"""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


def validate_conditional_rules(value: Any, field: str = "conditional_rules") -> Dict[str, Any]:
    """校验并规范化 conditional_rules，返回规范对象 {returncode_zero, conditions:[...]}。

    唯一合法根结构为对象（不接受 list/标量），conditions 必须为非空数组；
    逐条件校验 source(regex:)/operator/target/tolerance/on_fail，任一非法抛
    RuleValidationError（携带精确 field 路径）。写前校验用，不写库。
    """
    if not isinstance(value, dict):
        raise RuleValidationError(
            field, "conditional_rules 必须是对象（含 conditions 数组），不接受数组或标量"
        )
    unknown = set(value) - _ALLOWED_RULE_KEYS
    if unknown:
        raise RuleValidationError(field, f"未知字段: {sorted(unknown)}")

    returncode_zero = value.get("returncode_zero", True)
    if not isinstance(returncode_zero, bool):
        raise RuleValidationError(f"{field}.returncode_zero", "returncode_zero 必须为布尔值")

    conditions = value.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise RuleValidationError(
            f"{field}.conditions", "至少一个条件且不能使用空规则"
        )

    normalized: List[Dict[str, Any]] = []
    for index, condition in enumerate(conditions):
        fp = f"{field}.conditions.{index}"
        if not isinstance(condition, dict):
            raise RuleValidationError(fp, "条件必须是对象")
        unknown_cond = set(condition) - _ALLOWED_CONDITION_KEYS
        if unknown_cond:
            raise RuleValidationError(fp, f"未知条件字段: {sorted(unknown_cond)}")

        source = condition.get("source")
        if not isinstance(source, str) or not source.strip():
            raise RuleValidationError(f"{fp}.source", "source 必填且为非空字符串")
        if not source.startswith("regex:"):
            raise RuleValidationError(f"{fp}.source", "source 必须为 regex:<有效正则>")
        pattern = source[len("regex:"):]
        if not pattern:
            raise RuleValidationError(f"{fp}.source", "正则表达式不能为空")
        try:
            re.compile(pattern)
        except re.error:
            raise RuleValidationError(f"{fp}.source", "非法正则表达式")

        raw_operator = condition.get("operator")
        if not isinstance(raw_operator, str) or not raw_operator.strip():
            raise RuleValidationError(f"{fp}.operator", "operator 必填")
        operator = OPERATOR_ALIASES.get(raw_operator.strip(), raw_operator.strip())
        if operator not in VALID_OPERATORS:
            raise RuleValidationError(f"{fp}.operator", "未知操作符")

        target = condition.get("target")
        if target is None or isinstance(target, bool) or isinstance(target, (list, dict)):
            raise RuleValidationError(f"{fp}.target", "target 必填且为标量或 spec:<键>")
        target_str = str(target).strip()
        if not target_str:
            raise RuleValidationError(f"{fp}.target", "target 不能为空")
        if target_str.startswith("spec:"):
            if not target_str[len("spec:"):].strip():
                raise RuleValidationError(f"{fp}.target", "spec 键不能为空")
        elif operator in _NUMERIC_OPERATORS:
            try:
                numeric_target = float(target_str)
            except (TypeError, ValueError):
                raise RuleValidationError(f"{fp}.target", "数值比较的 target 必须为数值")
            if operator == "approx_ratio" and numeric_target == 0:
                raise RuleValidationError(f"{fp}.target", "approx_ratio 数值目标不得为 0")

        tolerance = condition.get("tolerance", "0%")
        if tolerance is None:
            tolerance = "0%"
        if not isinstance(tolerance, str):
            raise RuleValidationError(f"{fp}.tolerance", "tolerance 必须为百分比字符串")
        tolerance_str = tolerance.strip()
        if not _TOLERANCE_RE.match(tolerance_str):
            raise RuleValidationError(f"{fp}.tolerance", "tolerance 必须为非负百分比，如 5%")

        on_fail = condition.get("on_fail", "条件不满足")
        if on_fail is None:
            on_fail = "条件不满足"
        if not isinstance(on_fail, str):
            raise RuleValidationError(f"{fp}.on_fail", "on_fail 必须为字符串")
        if len(on_fail) > 500:
            raise RuleValidationError(f"{fp}.on_fail", "on_fail 最长 500 字符")
        if _CONTROL_CHARS.search(on_fail):
            raise RuleValidationError(f"{fp}.on_fail", "on_fail 不得包含控制字符")

        normalized.append({
            "source": source,
            "operator": operator,
            "target": target_str,
            "tolerance": tolerance_str,
            "on_fail": on_fail,
        })

    return {"returncode_zero": returncode_zero, "conditions": normalized}


def canonical_rule_hash(rules: Dict[str, Any]) -> str:
    """规则规范化 JSON 的 SHA-256，用于重复转换幂等判重。"""
    payload = json.dumps(rules, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _split_existing_rules(existing: Any) -> tuple:
    """把 DB 中可能存在的 legacy 结构（list/旧 dict）归一为 (conditions, returncode_zero)。

    仅做兼容读取，不改变既有数据；新写入统一为契约对象。
    """
    if isinstance(existing, dict):
        conditions = existing.get("conditions")
        return (
            list(conditions) if isinstance(conditions, list) else [],
            bool(existing.get("returncode_zero", True)),
        )
    if isinstance(existing, list):
        conditions: List[Any] = []
        returncode_zero = True
        for element in existing:
            if isinstance(element, dict) and "conditions" in element:
                inner = element.get("conditions")
                if isinstance(inner, list):
                    conditions.extend(inner)
                returncode_zero = bool(element.get("returncode_zero", returncode_zero))
            elif isinstance(element, dict):
                conditions.append(element)
        return conditions, returncode_zero
    return [], True



# ========== LLM 提取 Schema ==========

TEST_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "module_name": {"type": "string", "description": "所属测试模块名称，如 EMMC、DDR、WIFI"},
        "name": {"type": "string", "description": "测试项名称"},
        "objective": {"type": "string", "description": "测试目的"},
        "precondition": {"type": "string", "description": "前置条件"},
        "steps": {"type": "string", "description": "测试步骤"},
        "expected_result": {"type": "string", "description": "预期结果"},
        "exec_type": {"type": "string", "enum": ["adb_shell", "push_exec", "host_exec"], "description": "执行方式"},
        "exec_command": {"type": "string", "description": "执行命令或脚本内容"},
        "parameters": {"type": "object", "description": "参数模板"},
        "judgement_type": {"type": "string", "enum": ["assertion", "rubric", "ai_fallback"], "description": "判定方式"},
        "conditional_rules": {"type": "array", "description": "断言规则列表"},
        "rubric_criteria": {"type": "array", "description": "评分标准列表"},
        "result_parse": {"type": "object", "description": "结果解析配置"},
        "timeout": {"type": "integer", "description": "超时时间（秒）"},
        "compatibility": {"type": "object", "description": "兼容性要求"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"}
    },
    "required": ["module_name", "name", "exec_type", "exec_command", "judgement_type"]
}

FAILURE_PATTERN_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "失败模式名称"},
        "category": {"type": "string", "description": "类别，如 adb/compat/timeout/assertion"},
        "pattern": {"type": "string", "description": "用于匹配日志的正则表达式"},
        "description": {"type": "string", "description": "失败模式描述"},
        "suggested_fix": {"type": "string", "description": "修复建议"}
    },
    "required": ["name", "pattern"]
}

BASELINE_SCHEMA = {
    "type": "object",
    "properties": {
        "device_model": {"type": "string", "description": "设备型号"},
        "item_name": {"type": "string", "description": "测试项名称"},
        "metric_name": {"type": "string", "description": "指标名称，如 bw_read_mbps"},
        "avg_value": {"type": "string", "description": "平均值"},
        "min_value": {"type": "string", "description": "最小值"},
        "max_value": {"type": "string", "description": "最大值"},
        "sample_count": {"type": "integer", "description": "样本数"}
    },
    "required": ["device_model", "item_name", "metric_name"]
}

RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "target_item_name": {"type": "string", "description": "目标测试项名称"},
        "conditional_rules": {
            "type": "object",
            "description": "可执行断言规则对象：{returncode_zero:boolean, conditions:array}",
            "properties": {
                "returncode_zero": {"type": "boolean"},
                "conditions": {"type": "array"},
            },
            "required": ["conditions"],
        },
    },
    "required": ["target_item_name", "conditional_rules"],
}

SCHEMA_MAP = {
    "test_item": TEST_ITEM_SCHEMA,
    "failure_pattern": FAILURE_PATTERN_SCHEMA,
    "baseline": BASELINE_SCHEMA,
    "rule": RULE_SCHEMA,
}


class KnowledgeConverter:
    """将知识库条目转换为可执行测试资产。"""

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client

    @classmethod
    def get_default_converter(cls) -> "KnowledgeConverter":
        try:
            client = LLMClient.get_default_client()
            if client and client.api_key:
                return cls(client)
        except Exception:
            pass
        return cls(None)

    async def preview(
        self,
        entry: KnowledgeEntry,
        target_type: str,
        extra_hint: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """使用 LLM 从知识条目提取目标资产预览，不写入数据库。"""
        if target_type not in SCHEMA_MAP:
            raise ValueError(f"不支持的目标资产类型：{target_type}")

        if not self.client:
            return None

        schema = SCHEMA_MAP[target_type]
        system_prompt = (
            "你是一位测试资产整理专家。请阅读用户提供的测试资料，"
            "提取并输出可用于创建测试资产的结构化信息。"
        )
        if extra_hint:
            system_prompt += f"\n用户补充要求：{extra_hint}"

        user_prompt = f"""资料标题：{entry.title or '未命名'}
资料类型：{entry.entry_type}
资料分类：{entry.category or '未分类'}
资料标签：{', '.join(entry.tags or [])}

资料内容：
```
{entry.content or ''}
```

请根据资料内容提取 {target_type} 所需的字段。
"""
        try:
            result = await self.client.chat_completion_structured(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                schema=schema
            )
            return self._normalize_preview(target_type, result)
        except Exception as exc:
            logger.warning("知识条目 %s 转 %s 预览失败: %s", entry.id, target_type, exc)
            return None

    def _normalize_preview(self, target_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """规范化 LLM 预览结果。"""
        if not data:
            return {}
        data = {k: v for k, v in data.items() if v is not None}

        if target_type == "test_item":
            data.setdefault("module_name", "未分类")
            data.setdefault("timeout", 300)
            data.setdefault("tags", [])
            if isinstance(data.get("tags"), str):
                data["tags"] = [t.strip() for t in data["tags"].replace("，", ",").split(",") if t.strip()]

        if target_type == "failure_pattern":
            data.setdefault("category", "general")
            data.setdefault("description", "")
            data.setdefault("suggested_fix", "")

        if target_type == "baseline":
            data.setdefault("sample_count", 1)

        if target_type == "rule":
            # 契约 §1/§4：conditional_rules 唯一结构为对象（含 conditions 数组），
            # 不得再把对象自动包成 list；缺失时保留 None/缺省交由写前校验报错。
            rules = data.get("conditional_rules")
            if isinstance(rules, dict):
                try:
                    data["conditional_rules"] = validate_conditional_rules(
                        rules, "preview_data.conditional_rules"
                    )
                except RuleValidationError:
                    # 预览保留原始结构，由 API 层按契约返回 400 VALIDATION_ERROR
                    data["conditional_rules"] = rules
            elif rules is not None:
                # list/标量根结构非法：保留原值，交由 API 层校验报错
                data["conditional_rules"] = rules

        return data

    async def convert(
        self,
        db: AsyncSession,
        entry: KnowledgeEntry,
        target_type: str,
        preview_data: Dict[str, Any],
        current_user_id: int
    ) -> Dict[str, Any]:
        """根据预览数据创建实际测试资产。"""
        if target_type == "rule":
            # 写前校验（在目标测试项查询与任何写入之前）：
            # conditional_rules 唯一合法结构为对象（conditions 数组），非法抛 RuleValidationError。
            normalized_rules = validate_conditional_rules(
                preview_data.get("conditional_rules"), "preview_data.conditional_rules"
            )
            return await self._attach_rule(db, preview_data, normalized_rules)
        if target_type == "test_item":
            rules = preview_data.get("conditional_rules")
            if isinstance(rules, dict):
                # test_item 若提供对象结构规则，同样按契约规范化后再落库
                preview_data = {
                    **preview_data,
                    "conditional_rules": validate_conditional_rules(
                        rules, "preview_data.conditional_rules"
                    ),
                }
            return await self._create_test_item(db, preview_data, current_user_id)
        if target_type == "failure_pattern":
            return await self._create_failure_pattern(db, preview_data, current_user_id)
        if target_type == "baseline":
            return await self._create_baseline(db, preview_data)
        raise ValueError(f"不支持的目标资产类型：{target_type}")

    async def _get_or_create_module(
        self,
        db: AsyncSession,
        module_name: str,
        current_user_id: int,
        category: Optional[str] = None
    ) -> TestModule:
        """根据名称查找或创建测试模块。"""
        result = await db.execute(
            select(TestModule).where(TestModule.name == module_name)
        )
        module = result.scalar_one_or_none()
        if not module:
            module = TestModule(
                name=module_name,
                category=category or "other",
                description=f"由知识库条目转换自动生成：{module_name}",
                created_by=current_user_id
            )
            db.add(module)
            await db.flush()
            await db.refresh(module)
        return module

    async def _create_test_item(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
        current_user_id: int
    ) -> Dict[str, Any]:
        """创建测试项。"""
        module = await self._get_or_create_module(
            db, data["module_name"], current_user_id, data.get("module_category")
        )

        item = TestItem(
            module_id=module.id,
            name=data["name"],
            objective=data.get("objective"),
            precondition=data.get("precondition"),
            steps=data.get("steps"),
            expected_result=data.get("expected_result"),
            exec_type=data.get("exec_type", "adb_shell"),
            exec_command=data.get("exec_command", ""),
            parameters=data.get("parameters"),
            judgement_type=data.get("judgement_type", "assertion"),
            conditional_rules=data.get("conditional_rules"),
            rubric_criteria=data.get("rubric_criteria"),
            result_parse=data.get("result_parse"),
            timeout=data.get("timeout", 300),
            compatibility=data.get("compatibility"),
            tags=data.get("tags"),
            created_by=current_user_id
        )
        db.add(item)
        await db.flush()
        await db.refresh(item)
        return {
            "asset_type": "test_item",
            "module_id": module.id,
            "module_name": module.name,
            "item_id": item.id,
            "item_name": item.name
        }

    async def _create_failure_pattern(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
        current_user_id: int
    ) -> Dict[str, Any]:
        """创建失败模式。"""
        pattern = FailurePattern(
            name=data["name"],
            category=data.get("category", "general"),
            pattern=data["pattern"],
            description=data.get("description"),
            suggested_fix=data.get("suggested_fix"),
            created_by=current_user_id
        )
        db.add(pattern)
        await db.flush()
        await db.refresh(pattern)
        return {
            "asset_type": "failure_pattern",
            "pattern_id": pattern.id,
            "name": pattern.name
        }

    async def _create_baseline(
        self,
        db: AsyncSession,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建统计基线。"""
        # 按名称查找测试项
        item_id = data.get("item_id")
        if not item_id and data.get("item_name"):
            result = await db.execute(
                select(TestItem).where(TestItem.name == data["item_name"])
            )
            item = result.scalar_one_or_none()
            if item:
                item_id = item.id

        baseline = Baseline(
            device_model=data["device_model"],
            item_id=item_id or 0,
            metric_name=data["metric_name"],
            avg_value=str(data.get("avg_value", "")),
            min_value=str(data.get("min_value", "")),
            max_value=str(data.get("max_value", "")),
            sample_count=data.get("sample_count", 1)
        )
        db.add(baseline)
        await db.flush()
        await db.refresh(baseline)
        return {
            "asset_type": "baseline",
            "baseline_id": baseline.id,
            "device_model": baseline.device_model,
            "metric_name": baseline.metric_name
        }

    async def _attach_rule(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
        normalized_rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """将规则对象附加到目标测试项（同一对象 schema、重复规则幂等）。"""
        item_id = data.get("target_item_id")
        if not item_id and data.get("target_item_name"):
            result = await db.execute(
                select(TestItem).where(TestItem.name == data["target_item_name"])
            )
            item = result.scalar_one_or_none()
            if not item:
                raise ValueError(f"未找到目标测试项：{data['target_item_name']}")
            item_id = item.id

        result = await db.execute(select(TestItem).where(TestItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError(f"未找到目标测试项 ID：{item_id}")

        # 兼容读取历史 legacy 结构（list/旧 dict）后升级为契约对象；新写入统一对象。
        existing_conditions, existing_returncode = _split_existing_rules(item.conditional_rules)
        existing_rules = {
            "returncode_zero": existing_returncode,
            "conditions": existing_conditions,
        }

        # 重复规则幂等：完全相同的规范化规则对象不重复附加（对应契约唯一键语义）
        if canonical_rule_hash(existing_rules) == canonical_rule_hash(normalized_rules):
            return {
                "asset_type": "rule",
                "target_item_id": item.id,
                "item_id": item.id,
                "item_name": item.name,
                "rules_count": len(existing_conditions),
            }

        merged_conditions = existing_conditions + list(normalized_rules["conditions"])
        merged_rules = {
            "returncode_zero": normalized_rules.get("returncode_zero", True),
            "conditions": merged_conditions,
        }
        item.conditional_rules = merged_rules

        await db.flush()
        await db.refresh(item)
        return {
            "asset_type": "rule",
            "target_item_id": item.id,
            "item_id": item.id,
            "item_name": item.name,
            "rules_count": len(merged_conditions),
        }
