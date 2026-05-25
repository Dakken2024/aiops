import logging
from typing import List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self._client = None
        self._model = 'text-embedding-3-small'

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            api_key = getattr(settings, 'AI_OPS_CONFIG', {}).get('api_key', '')
            base_url = getattr(settings, 'AI_OPS_CONFIG', {}).get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
            if not api_key:
                ai_ops_objs = __import__('ai_ops.models', fromlist=['AiOpsConfig'])
                config = ai_ops_objs.AiOpsConfig.objects.filter(is_active=True).first()
                if config:
                    api_key = config.api_key
                    base_url = config.base_url or base_url
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        return self._client

    def embed_text(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        try:
            client = self._get_client()
            response = client.embeddings.create(
                model=self._model,
                input=text[:8000],
            )
            return response.data[0].embedding
        except Exception as e:
            logger.debug(f"[EmbeddingService] 嵌入失败: {e}")
            return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        if not texts:
            return []
        try:
            client = self._get_client()
            valid_texts = [t[:8000] if t else '' for t in texts]
            response = client.embeddings.create(
                model=self._model,
                input=valid_texts,
            )
            result_map = {d.index: d.embedding for d in response.data}
            return [result_map.get(i) for i in range(len(texts))]
        except Exception as e:
            logger.debug(f"[EmbeddingService] 批量嵌入失败: {e}")
            return [None] * len(texts)
