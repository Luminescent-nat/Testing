import json
import logging
from typing import List, Dict, Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMClient:
    """大模型 API 客户端，支持 OpenAI 兼容接口。"""

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None
    ):
        self.provider = provider or settings.LLM_PROVIDER
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL
        self.temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        self.max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        self.timeout = timeout or settings.LLM_TIMEOUT

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None
    ) -> str:
        """调用聊天补全接口，返回模型生成的文本。"""
        if not self.api_key:
            raise ValueError("LLM API Key 未配置")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens
        }

        if response_format:
            payload["response_format"] = response_format

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        logger.debug("LLM 响应: %s", content)
        return content

    async def chat_completion_structured(
        self,
        messages: List[Dict[str, str]],
        schema: Dict[str, Any],
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """调用聊天补全接口，要求返回结构化 JSON。"""
        # 在 system 消息中注入 JSON Schema 要求
        schema_instruction = (
            "你必须严格按以下 JSON Schema 返回结果，不要包含任何额外说明文字，"
            "只输出合法 JSON 对象:\n" + json.dumps(schema, ensure_ascii=False, indent=2)
        )

        # 查找或追加 system 消息
        has_system = False
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = msg["content"] + "\n\n" + schema_instruction
                has_system = True
                break

        if not has_system:
            messages.insert(0, {"role": "system", "content": schema_instruction})

        content = await self.chat_completion(
            messages,
            temperature=temperature,
            response_format={"type": "json_object"}
        )

        # 清理可能包裹的 ```json 代码块
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("LLM 返回非 JSON 内容: %s", content)
            raise ValueError(f"LLM 返回解析失败: {exc}") from exc

    @classmethod
    def get_default_client(cls) -> "LLMClient":
        """获取默认配置的客户端。"""
        return cls()


# 测试用例判定结果 Schema
JUDGEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["pass", "fail", "skip", "unknown"]
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
        },
        "score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 4,
            "description": "Rubrics 评分时使用，1-4 分"
        },
        "metrics": {
            "type": "object",
            "description": "提取的关键指标，如 {bandwidth_mbps: 2400}"
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "判定依据"
        },
        "fail_reason": {
            "type": "string"
        },
        "suggestions": {
            "type": "string"
        }
    },
    "required": ["status", "confidence", "evidence", "fail_reason", "suggestions"]
}


# 自然语言任务规划结果 Schema
TASK_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "device_serial": {
            "type": "string",
            "description": "目标设备序列号"
        },
        "intent": {
            "type": "string",
            "description": "测试意图摘要"
        },
        "selected_modules": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要测试的模块名称列表"
        },
        "test_type": {
            "type": "string",
            "description": "测试类型：functional/performance/stability/stress/all"
        },
        "notes": {
            "type": "string"
        }
    },
    "required": ["device_serial", "intent", "selected_modules", "test_type"]
}
