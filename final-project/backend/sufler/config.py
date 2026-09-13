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

    # Ранжирование сервисом платформы (Infinity, Jina-совместимый /rerank).
    # Без SUFLER_RERANK_URL работает локальный cross-encoder — офлайн-демо и тесты.
    # С ним реранк уходит на GPU-сервис: 82 мс на набор против 664–708 мс на CPU,
    # и оценки становятся калиброванными (ADR-0004, новая редакция).
    rerank_url: str = os.getenv("SUFLER_RERANK_URL", "")
    rerank_api_key: str = os.getenv("SUFLER_RERANK_API_KEY", "")
    rerank_model_remote: str = os.getenv("SUFLER_RERANK_MODEL_REMOTE", "BAAI/bge-reranker-v2-m3")

    # параметры retrieval (урок 06)
    top_k_retrieve: int = int(os.getenv("SUFLER_TOP_K", "20"))
    top_k_context: int = int(os.getenv("SUFLER_TOP_CTX", "5"))

    # вектор: self-hosted Qdrant (ADR-0004). Без QDRANT_URL — встроенный :memory:
    # (офлайн-демо и тесты): стек поднимать не нужно, шаги pipeline те же.
    qdrant_url: str = os.getenv("QDRANT_URL", "")

    # Порог отказа от ответа. Косинус нормированных эмбеддингов, а НЕ оценка
    # cross-encoder: логиты ms-marco не калиброваны на русском корпусе и не
    # разделяют вопросы в корпусе и вне его (замер — docs/eval-report.md).
    # Косинус разделяет: 0.585 минимум по корпусу против 0.369 максимума вне,
    # порог посередине со смещением в сторону «лучше ответить».
    min_relevance: float = float(os.getenv("SUFLER_MIN_RELEVANCE", "0.45"))

    # Второй порог — на оценке реранкера, и он применяется ТОЛЬКО если реранкер
    # калиброван (bge-reranker-v2-m3 — да, ms-marco — нет). Косинус остаётся
    # дешёвым ранним выходом: он отсекает заведомо чужой вопрос ещё до похода в
    # сервис. Решает же релевантность: 0.9919 худший свой против 0.0004 лучшего
    # чужого — порог сильно ниже зазора, чтобы не резать пограничные вопросы.
    min_rerank_score: float = float(os.getenv("SUFLER_MIN_RERANK_SCORE", "0.10"))

    # граф знаний (ADR-0012/0013). Без NEO4J_URI — in-memory режим (офлайн-демо, тесты)
    neo4j_uri: str = os.getenv("NEO4J_URI", "")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "")
    # Третий бэкенд графа — рекурсивные CTE в той же СУБД, где уже живёт
    # векторная часть платформы. Выбор делается замером, а не умолчанием
    # (ADR-0028): SUFLER_GRAPH_BACKEND = auto | neo4j | postgres | memory.
    graph_backend: str = os.getenv("SUFLER_GRAPH_BACKEND", "auto")
    graph_dsn: str = os.getenv("SUFLER_GRAPH_DSN", "")
    graph_enabled: bool = os.getenv("SUFLER_GRAPH", "1") == "1"
    graph_hops: int = int(os.getenv("SUFLER_GRAPH_HOPS", "2"))
    graph_limit: int = int(os.getenv("SUFLER_GRAPH_LIMIT", "10"))
    graph_slots: int = int(os.getenv("SUFLER_GRAPH_SLOTS", "3"))  # резерв мест под связанные пункты

    # Наблюдаемость (ADR-0017). Без OTEL_EXPORTER_OTLP_ENDPOINT спаны создаются,
    # но никуда не уходят — офлайн-демо и тесты не требуют коллектора.
    otel_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    otel_service_name: str = os.getenv("OTEL_SERVICE_NAME", "platform-backend")
    # Содержимое запроса и ответа в трейсах — выключено: трейс доступен шире,
    # чем сами документы. Включённое — проходит через PII-маску.
    otel_capture_content: bool = os.getenv("SUFLER_OTEL_CONTENT", "0") == "1"

    # Граница доверия (ADR-0016): роли берутся из проверенного по JWKS токена
    # Keycloak. Без OIDC_JWKS_URL сервис остаётся в dev-режиме (роли из тела
    # запроса) — допустимо только в доверенном контуре и видно в /healthz.
    oidc_jwks_url: str = os.getenv("OIDC_JWKS_URL", "")
    oidc_audience: str = os.getenv("OIDC_AUDIENCE", "")
    oidc_issuer: str = os.getenv("OIDC_ISSUER", "")
    oidc_roles_claim: str = os.getenv("OIDC_ROLES_CLAIM", "groups")   # ADR-0016: claims.groups
    oidc_jwks_ttl: int = int(os.getenv("OIDC_JWKS_TTL", "300"))

    # Мультиагентный слой — «цифровые сотрудники» (ADR-0015).
    # Лимиты не декоративные: без потолка шагов и вызовов инструментов цикл
    # рассуждений — это LLM06 Unbounded Consumption и каскадный отказ ASI08.
    mas_enabled: bool = os.getenv("SUFLER_MAS", "1") == "1"
    mas_max_steps: int = int(os.getenv("SUFLER_MAS_MAX_STEPS", "6"))
    mas_max_tool_calls: int = int(os.getenv("SUFLER_MAS_MAX_TOOLS", "4"))
    mas_token_budget: int = int(os.getenv("SUFLER_MAS_TOKEN_BUDGET", "6000"))
    mas_fanout: int = int(os.getenv("SUFLER_MAS_FANOUT", "2"))
    # checkpointer состояния: PostgreSQL в проде, in-memory без DATABASE_URL
    database_url: str = os.getenv("DATABASE_URL", "")

    # LLM — OpenAI-совместимый эндпоинт (в проде vLLM + Qwen3.5, ADR-0002/0003)
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "not-needed")
    llm_model: str = os.getenv("SUFLER_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    # 0 → офлайн-демо без LLM (extractive fallback)
    use_llm: bool = os.getenv("SUFLER_USE_LLM", "1") == "1"


settings = Settings()
