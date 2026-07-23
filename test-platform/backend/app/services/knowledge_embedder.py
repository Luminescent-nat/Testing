"""知识库嵌入服务：生成、缓存、管理文本向量。"""
import hashlib
import json
import logging
import math
import random
import re
from typing import List, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class KnowledgeEmbedder:
    """文本嵌入生成器，支持 OpenAI 兼容接口、本地模型、Mock 回退。"""

    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER
        self.enabled = settings.EMBEDDING_ENABLED
        self.api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        self.base_url = (settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL).rstrip("/")
        self.model = settings.EMBEDDING_MODEL
        self.timeout = settings.EMBEDDING_TIMEOUT
        self.dimension = settings.EMBEDDING_DIMENSION
        self._local_model = None

    async def embed(self, text: str) -> Optional[List[float]]:
        """对单条文本生成嵌入向量。"""
        if not text or not text.strip():
            return None
        if not self.enabled:
            return None

        cleaned = self._clean_text(text)

        if self.provider == "openai":
            return await self._openai_embed(cleaned)
        if self.provider == "local":
            return self._local_embed(cleaned)
        if self.provider == "mock":
            return self._mock_embed(cleaned)

        # 默认使用 mock 避免阻塞
        return self._mock_embed(cleaned)

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """批量生成嵌入。当前按顺序调用单条，可后续优化为批量请求。"""
        results = []
        for text in texts:
            try:
                vec = await self.embed(text)
                results.append(vec)
            except Exception as exc:
                logger.warning("批量嵌入单条失败: %s", exc)
                results.append(None)
        return results

    async def _openai_embed(self, text: str) -> Optional[List[float]]:
        """调用 OpenAI 兼容 embeddings 接口。"""
        if not self.api_key:
            logger.warning("未配置 Embedding API Key，降级到 mock 嵌入")
            return self._mock_embed(text)

        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": text,
            "model": self.model,
            "encoding_format": "float"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                vec = data["data"][0]["embedding"]
                return self._normalize(vec)
        except Exception as exc:
            logger.warning("OpenAI Embedding 调用失败: %s，降级到 mock", exc)
            return self._mock_embed(text)

    def _local_embed(self, text: str) -> Optional[List[float]]:
        """本地 sentence-transformers 嵌入。"""
        try:
            from sentence_transformers import SentenceTransformer
            if self._local_model is None:
                model_name = self.model if self.model and self.model != "text-embedding-3-small" else "all-MiniLM-L6-v2"
                self._local_model = SentenceTransformer(model_name)
            vec = self._local_model.encode(text).tolist()
            return self._normalize(vec)
        except Exception as exc:
            logger.warning("本地嵌入模型失败: %s，降级到 mock", exc)
            return self._mock_embed(text)

    def _mock_embed(self, text: str) -> List[float]:
        """基于文本哈希的确定性 mock 向量，仅用于演示/无 embedding 时的占位。"""
        # 用文本哈希生成确定性随机向量
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        vec = [rng.uniform(-1, 1) for _ in range(self.dimension)]
        return self._normalize(vec)

    @staticmethod
    def _clean_text(text: str) -> str:
        """清洗文本，控制长度。"""
        if not text:
            return ""
        # 去除多余空白
        text = re.sub(r"\s+", " ", text)
        # 限制长度，避免 token 超限
        return text[:6000]

    @staticmethod
    def _normalize(vec: List[float]) -> List[float]:
        """L2 归一化，便于余弦相似度计算。"""
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]


def cosine_similarity(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    """计算两个 L2 归一化向量的余弦相似度。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    # 若已归一化，点积即余弦相似度
    return sum(x * y for x, y in zip(a, b))


# 全局默认 embedder
_default_embedder: Optional[KnowledgeEmbedder] = None


def get_embedder() -> KnowledgeEmbedder:
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = KnowledgeEmbedder()
    return _default_embedder
