"""知识库 AI 提取服务：自动从文档中提取标题、分类、标签、摘要、关联测试项。"""
import json
import logging
from typing import Dict, Any, Optional

from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "资料标题，不超过 50 字"},
        "category": {"type": "string", "description": "资料分类，如 测试规范 / 操作手册 / 故障案例"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "5-10 个关键词标签，如 ['EMMC', '性能测试', 'FIO']"
        },
        "summary": {"type": "string", "description": "资料摘要，200 字以内"},
        "entry_type": {
            "type": "string",
            "enum": ["document", "test_case", "device_profile", "rule", "failure_pattern", "baseline", "skill"],
            "description": "最适合的知识条目类型"
        },
        "suggested_item_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "建议关联的测试项 ID 列表，无则留空"
        }
    },
    "required": ["title", "category", "tags", "summary", "entry_type"]
}


TEST_CASE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "module_name": {"type": "string", "description": "所属模块，如 EMMC / DDR / WIFI"},
                    "name": {"type": "string", "description": "测试项名称"},
                    "objective": {"type": "string", "description": "测试目的"},
                    "precondition": {"type": "string", "description": "前置条件"},
                    "steps": {"type": "string", "description": "测试步骤"},
                    "expected_result": {"type": "string", "description": "预期结果"},
                    "exec_type": {"type": "string", "enum": ["adb_shell", "push_exec", "host_exec"], "description": "执行方式"},
                    "exec_command": {"type": "string", "description": "执行命令或脚本"},
                    "judgement_type": {"type": "string", "enum": ["assertion", "rubric", "ai_fallback"], "description": "判定方式"},
                    "conditional_rules": {"type": "array", "description": "断言规则列表"},
                    "timeout": {"type": "integer", "description": "超时秒数"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"}
                },
                "required": ["module_name", "name"]
            }
        },
        "summary": {"type": "string", "description": "表格整体摘要，100 字以内"}
    },
    "required": ["test_cases"]
}


class KnowledgeExtractor:
    """使用 LLM 从原始文本中提取结构化知识信息。"""

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client

    async def extract(self, text: str, filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """提取文档结构化信息。"""
        if not self.client:
            logger.warning("未配置 LLM 客户端，跳过 AI 提取")
            return None

        if not text or not text.strip():
            return None

        system_prompt = (
            "你是一位测试知识库整理专家。请阅读用户上传的测试资料，"
            "提取出标题、分类、标签、摘要和最适合的知识条目类型。"
            "必须返回结构化 JSON，不要包含额外说明。"
        )

        user_prompt = f"""文件名: {filename or '未命名'}

资料内容:
```
{text[:8000]}
```

请按 JSON Schema 输出提取结果。
"""

        try:
            result = await self.client.chat_completion_structured(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                schema=EXTRACTION_SCHEMA
            )
            return self._normalize(result)
        except Exception as exc:
            logger.warning("AI 提取失败: %s", exc)
            return None

    async def extract_test_cases(self, text: str, filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """从表格化测试用例文档中提取结构化测试用例列表。"""
        if not self.client:
            logger.warning("未配置 LLM 客户端，跳过测试用例 AI 提取")
            return None

        if not text or not text.strip():
            return None

        system_prompt = (
            "你是一位测试用例整理专家。用户上传了一份 Excel 测试用例表格，"
            "表格已被转换为 Markdown 格式。请识别每一行测试用例，"
            "提取出测试项名称、所属模块、测试目的、前置条件、测试步骤、预期结果、执行方式、判定方式等。"
            "如果表格中缺少某些字段，请根据上下文合理推断或留空。"
            "必须返回结构化 JSON，不要包含额外说明。"
        )

        user_prompt = f"""文件名: {filename or '未命名'}

表格内容（Markdown 格式）:
```
{text[:12000]}
```

请按 JSON Schema 输出提取到的测试用例列表。
"""

        try:
            result = await self.client.chat_completion_structured(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                schema=TEST_CASE_EXTRACTION_SCHEMA
            )
            return self._normalize_test_cases(result)
        except Exception as exc:
            logger.warning("测试用例 AI 提取失败: %s", exc)
            return None

    @staticmethod
    def _normalize_test_cases(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """规范化测试用例提取结果。"""
        if not result:
            return None
        cases = result.get("test_cases") or []
        normalized = []
        for case in cases:
            if not case.get("name"):
                continue
            tags = case.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
            normalized.append({
                "module_name": str(case.get("module_name", "未分类")).strip()[:100],
                "name": str(case.get("name", "")).strip()[:100],
                "objective": str(case.get("objective", "")).strip()[:500] or None,
                "precondition": str(case.get("precondition", "")).strip()[:500] or None,
                "steps": str(case.get("steps", "")).strip()[:2000] or None,
                "expected_result": str(case.get("expected_result", "")).strip()[:500] or None,
                "exec_type": str(case.get("exec_type", "adb_shell")).strip(),
                "exec_command": str(case.get("exec_command", "")).strip()[:1000] or None,
                "judgement_type": str(case.get("judgement_type", "assertion")).strip(),
                "conditional_rules": case.get("conditional_rules") if isinstance(case.get("conditional_rules"), list) else None,
                "timeout": int(case["timeout"]) if isinstance(case.get("timeout"), (int, float)) else 300,
                "tags": [str(t).strip() for t in tags if str(t).strip()][:20],
            })
        return {
            "test_cases": normalized,
            "summary": str(result.get("summary", "")).strip()[:500]
        }

    @staticmethod
    def _normalize(result: Dict[str, Any]) -> Dict[str, Any]:
        """规范化提取结果。"""
        if not result:
            return None
        tags = result.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        return {
            "title": str(result.get("title", "")).strip()[:200],
            "category": str(result.get("category", "")).strip()[:100],
            "tags": [str(t).strip() for t in tags if str(t).strip()][:20],
            "summary": str(result.get("summary", "")).strip()[:1000],
            "entry_type": str(result.get("entry_type", "document")).strip(),
            "suggested_item_ids": [int(x) for x in result.get("suggested_item_ids", []) if isinstance(x, int)]
        }


# 便捷函数
def get_extractor() -> KnowledgeExtractor:
    try:
        client = LLMClient.get_default_client()
        if client and client.api_key:
            return KnowledgeExtractor(client)
    except Exception:
        pass
    return KnowledgeExtractor(None)
