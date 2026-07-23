"""知识库条目转测试资产服务。"""
import json
import logging
from typing import Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import KnowledgeEntry, TestModule, TestItem, FailurePattern, Baseline
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


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
        "conditional_rules": {"type": "array", "description": "要附加的断言规则列表"}
    },
    "required": ["target_item_name", "conditional_rules"]
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
            if isinstance(data.get("conditional_rules"), dict):
                data["conditional_rules"] = [data["conditional_rules"]]
            data.setdefault("conditional_rules", [])

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
        if target_type == "test_item":
            return await self._create_test_item(db, preview_data, current_user_id)
        if target_type == "failure_pattern":
            return await self._create_failure_pattern(db, preview_data, current_user_id)
        if target_type == "baseline":
            return await self._create_baseline(db, preview_data)
        if target_type == "rule":
            return await self._attach_rule(db, preview_data)
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
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """将规则附加到目标测试项。"""
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

        existing = item.conditional_rules or []
        new_rules = data.get("conditional_rules", [])
        if not isinstance(existing, list):
            existing = [existing]
        if not isinstance(new_rules, list):
            new_rules = [new_rules]
        item.conditional_rules = existing + new_rules

        await db.flush()
        await db.refresh(item)
        return {
            "asset_type": "rule",
            "item_id": item.id,
            "item_name": item.name,
            "rules_count": len(item.conditional_rules or [])
        }
