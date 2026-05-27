# MVP «Суфлёр» — Advanced RAG по ЛПА (этапы 1–2)

Рабочий минимальный пример к [`../docs/mvp.md`](../docs/mvp.md). Реализует **этап 1** (формирование БЗ по ЛПА) и **этап 2** (текстовый Суфлёр: ответ по ЛПА с цитатами). Голос (этап 3) — отдельно ([ADR-0010](../docs/adr/0010-voice-stack.md)).

## Что внутри (= принятый стек, ADR)
- **Ingestion** ([ingest.py](sufler/ingest.py)) — загрузка ЛПА, recursive-чанкинг по разделам, метаданные + ACL (RBAC).
- **Hybrid retrieval + rerank** ([retriever.py](sufler/retriever.py)) — dense (Qdrant) + BM25, объединение **RRF**, **cross-encoder rerank**, **RBAC pre-filter** (урок 06, [ADR-0004](../docs/adr/0004-vector-db.md)).
- **LLM** ([llm.py](sufler/llm.py)) — OpenAI-совместимый клиент (в проде vLLM + Qwen3.6, [ADR-0002/0003](../docs/adr/)).
- **Guardrails** ([guardrails.py](sufler/guardrails.py)) — input (prompt-injection) + output (PII-маска).
- **API** ([api.py](sufler/api.py)) — `/ask` + OpenAI-совместимый `/v1/chat/completions` (для Open WebUI, [ADR-0007](../docs/adr/0007-chat-interface.md)).

> Демо-упрощения (отмечено в коде): Qdrant `:memory:` вместо self-hosted сервера; эмбеддер/реранкер — лёгкие CPU-модели вместо `bge-reranker-v2-m3`. Архитектура (шаги pipeline) — как в ADR.

## Запуск

### Вариант A — офлайн, без LLM (быстрый smoke)
Проверяет весь pipeline (ингест → hybrid → rerank → RBAC), ответ — extractive (топ-пункт).
```bash
cd final-project/mvp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
SUFLER_USE_LLM=0 python -m sufler.cli "Сколько дней основной отпуск?"
```

### Вариант B — с LLM (vLLM/Qwen или любой OpenAI-совместимый)
```bash
export OPENAI_BASE_URL=http://<vllm-host>:8000/v1
export SUFLER_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct   # в проде Qwen3.6-27B
export SUFLER_USE_LLM=1
python -m sufler.cli "Какие суточные в командировке по стране?"
```

### API-сервер
```bash
uvicorn sufler.api:app --port 8080
curl -s localhost:8080/ask -H 'content-type: application/json' \
  -d '{"question":"Сколько дней отпуск?","roles":["all"]}'
```
Подключение в Open WebUI: добавить OpenAI-коннектор на `http://<host>:8080/v1` (модель `sufler`).

## RBAC-демо
ЛПА-03 (доступ к ПДн) помечен `<!-- acl: legal, security -->`:
```bash
SUFLER_USE_LLM=0 python -m sufler.cli "Порядок доступа к персональным данным?"        # роль all → не найдёт
# через API с roles=["legal"] → найдёт
```

## Тесты
```bash
pytest -q     # ингест, RBAC-фильтр, блок prompt-injection (нужен интернет для скачивания моделей)
```

## Docker (air-gapped-ready)
Образ запекает модели эмбеддера/реранкера на сборке → стартует без интернета.
```bash
cd final-project/mvp
docker build -t sufler-rag:local .
docker run --rm -p 8080:8080 \
  -e OPENAI_BASE_URL=http://<vllm-host>:8000/v1 \
  -e SUFLER_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct \
  sufler-rag:local
```
В деплое Open WebUI подключается как сервис `sufler` (см. `open-webui/docker-compose.yml`); Pipe `sufler_rag_v1.py` зовёт `http://sufler:8080`. Публикация в реестр: тег `registry.gitlab.com/artcloud/ai/sufler:latest`.
Прод: смонтировать реальные ЛПА и переключить на Qdrant-сервер (ADR-0004) вместо in-memory.

## Структура
```
mvp/
├── sufler/        ingest · retriever · llm · guardrails · rag · api · cli
├── data/lpa/      примеры ЛПА (отпуск, командировки, доступ к ПДн[RBAC])
├── tests/         smoke-тесты
├── requirements.txt · .env.example
```

## Что дальше (не в минимальном MVP)
- Этап 3: голос (STT/TTS) — [ADR-0010](../docs/adr/0010-voice-stack.md).
- Прод: Qdrant-сервер, `bge-reranker-v2-m3`, guardrails в Open WebUI Pipelines, коннекторы Onyx ([ADR-0008](../docs/adr/0008-knowledge-base-connectors.md)), observability (трейсы/метрики).
