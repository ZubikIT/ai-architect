"""Конфигурация Суфлёра (через переменные окружения)."""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    # данные
    data_dir: str = os.getenv("SUFLER_DATA_DIR", "data/lpa")
    collection: str = os.getenv("SUFLER_COLLECTION", "lpa")

    # модели (для air-gapped — заранее скачать, см. ADR-0002/0004)
    embed_model: str = os.getenv("SUFLER_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    rerank_model: str = os.getenv("SUFLER_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    # параметры retrieval (урок 06)
    top_k_retrieve: int = int(os.getenv("SUFLER_TOP_K", "20"))
    top_k_context: int = int(os.getenv("SUFLER_TOP_CTX", "5"))

    # LLM — OpenAI-совместимый эндпоинт (в проде vLLM + Qwen3.6, ADR-0002/0003)
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "not-needed")
    llm_model: str = os.getenv("SUFLER_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    # 0 → офлайн-демо без LLM (extractive fallback)
    use_llm: bool = os.getenv("SUFLER_USE_LLM", "1") == "1"


settings = Settings()
