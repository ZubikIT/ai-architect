"""LLM-клиент — OpenAI-совместимый (в проде vLLM + Qwen3.6, ADR-0002/0003)."""
from openai import OpenAI

from .config import settings


class LLM:
    def __init__(self):
        self.client = OpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key)
        self.model = settings.llm_model

    def chat(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        return resp.choices[0].message.content
