# `/backend` — GraphRAG-ядро платформы цифровых сотрудников

Рабочая реализация к [`../docs/mvp.md`](../docs/mvp.md). Закрывает обязательное требование ТЗ — **GraphRAG** ([ADR-0012](../docs/adr/0012-graph-db.md), [ADR-0013](../docs/adr/0013-graphrag-strategiya.md)) — и критичный сценарий безопасности «User B не получает закрытый документ» ([ADR-0016](../docs/adr/0016-acl-na-uzlah-grafa.md)).

## Что делает граф, чего не делает плоский вектор

Вопрос «сколько дней основной отпуск?» векторным поиском находит пункт ЛПА-01: «28 календарных дней». Этот пункт **отменён** приказом ЛПА-04 («30 дней»), но текстуально отменяющий документ похож на десятки других — гарантии, что он попадёт в top-k, нет. Ребро `ОТМЕНЯЕТ` добавляет его в контекст **безусловно** и помечает исходный пункт как недействующий:

```
$ SUFLER_USE_LLM=0 python -m sufler.cli "Сколько дней основной ежегодный отпуск?"

⚠️ ЛПА-01 «1. Продолжительность отпуска» отменён документом ЛПА-04 · 1. Продолжительность отпуска.

Источники:
  - lpa-otpusk.md · 1. Продолжительность отпуска  ← ОТМЕНЁН
  - lpa-otpusk-izmeneniya.md · 1. Продолжительность отпуска  ← действующая редакция
```

Это и есть «потеря контекста» из формулировки ТЗ: без графа сотрудник получает отменённую норму без единой оговорки. Контрольный замер зафиксирован тестом `test_graph_disabled_loses_the_annotation` — с `SUFLER_GRAPH=0` пометка исчезает.

## Состав

| Модуль | Роль | Решение |
|---|---|---|
| [`ingest.py`](sufler/ingest.py) | загрузка ЛПА, чанкинг по разделам, ACL и провенанс на каждом чанке | [ADR-0014](../docs/adr/0014-multimodalnyy-ingestion.md) |
| [`links.py`](sufler/links.py) | экстракция связей **правилами** (номера, отмены, ссылки на пункты) | [ADR-0013](../docs/adr/0013-graphrag-strategiya.md) |
| [`graph.py`](sufler/graph.py) | онтология, построение графа, обход с ACL-предикатом; **весь Cypher только здесь** | [ADR-0012](../docs/adr/0012-graph-db.md), [ADR-0016](../docs/adr/0016-acl-na-uzlah-grafa.md) |
| [`graphrag.py`](sufler/graphrag.py) | vector-first → обход 1–2 хопа → rerank | [ADR-0013](../docs/adr/0013-graphrag-strategiya.md) |
| [`access.py`](sufler/access.py) | `RequestContext` и единая проверка прав (deny-by-default) | [ADR-0016](../docs/adr/0016-acl-na-uzlah-grafa.md) |
| [`retriever.py`](sufler/retriever.py) | hybrid dense (Qdrant) + BM25, RRF, cross-encoder rerank | [ADR-0004](../docs/adr/0004-vector-db.md) |
| [`guardrails.py`](sufler/guardrails.py) | input (prompt injection) + output (PII-маска) | [урок 14](../../14-security-by-design/14-security-by-design.md) |
| [`rag.py`](sufler/rag.py) | оркестрация, пометки об отменах, `request_id` для аудита | |
| [`api.py`](sufler/api.py) | `/ask`, `/graph/stats`, OpenAI-совместимый `/v1/chat/completions` | [ADR-0007](../docs/adr/0007-chat-interface.md) |

### Онтология (4 типа узлов, рекомендация занятия 32)

```
(:Документ)-[:СОДЕРЖИТ]->(:Чанк)
(:Чанк)-[:ОТМЕНЯЕТ]->(:Чанк)          отменяющая редакция → отменённый пункт
(:Чанк)-[:ССЫЛАЕТСЯ_НА {clause}]->(:Документ)
(:Чанк|:Документ)-[:ДОСТУПЕН_РОЛИ]->(:Роль)
```

Два бэкенда за одним интерфейсом: `Neo4jGraphStore` (боевой путь, `NEO4J_URI`) и `InMemoryGraphStore` (офлайн-демо и тесты, без инфраструктуры). Семантика ACL у них одна.

## Безопасность доступа

ACL-предикат применяется **на каждом узле пути обхода**, а не к финальной выдаче: иначе закрытый документ утекает через структуру связей — существование, название, соседей. Отдельное следствие, зафиксированное тестом: **факт отмены не раскрывается**, если отменяющий документ недоступен субъекту.

```bash
# User B (роль all) — закрытого ЛПА-03 нет ни в ответе, ни в контексте LLM
SUFLER_USE_LLM=0 python -m sufler.cli "Как обрабатываются персональные данные командированного?"
# User A (роль legal) — тот же документ приходит по ребру ССЫЛАЕТСЯ_НА
SUFLER_USE_LLM=0 python -m sufler.cli --roles legal "Как обрабатываются персональные данные командированного?"
```

> Роли в CLI и в теле `/ask` — **только для локальной отладки**. Целевой путь ([ADR-0016](../docs/adr/0016-acl-na-uzlah-grafa.md)): роли берутся из проверенного по JWKS токена Keycloak, тело запроса на доступ не влияет. Это расхождение с целевой архитектурой на сегодня не закрыто.

## Запуск

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# офлайн, без LLM и без инфраструктуры (граф — in-memory)
SUFLER_USE_LLM=0 python -m sufler.cli "Сколько дней основной ежегодный отпуск?"

# с Neo4j и vLLM
export NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=...
export OPENAI_BASE_URL=http://<vllm-host>:8000/v1 SUFLER_USE_LLM=1
python -m sufler.cli --stats          # проверить, что граф построен
uvicorn sufler.api:app --port 8080
```

Весь стек разом — [`../infra/docker-compose.yml`](../infra/README.md).

## Тесты

```bash
pytest -q      # 11 тестов; при первом запуске тянет модели эмбеддера и реранкера
```

Покрыто: эффект графа и контрольный замер без него, «User B», доступ роли `legal` через граф, deny-by-default, сокрытие отмены закрытым документом, блокировка prompt injection.

## Ограничения текущей реализации

- **Qdrant `:memory:`** вместо self-hosted сервера; эмбеддер и реранкер — лёгкие CPU-модели вместо `bge-reranker-v2-m3`. Шаги pipeline при этом те же, что в ADR.
- **Мультимодальный ingestion не реализован**: работает первая ступень каскада (текстовый слой), layout-парсер и VL-разбор сканов/чертежей — по [ADR-0014](../docs/adr/0014-multimodalnyy-ingestion.md). Поля `extracted_by` и `confidence` уже есть в контракте чанка.
- **Мультиагентный слой не реализован**: сейчас это один RAG-пайплайн, а не supervisor с ролями ([ADR-0015](../docs/adr/0015-topologiya-mas-cifrovye-sotrudniki.md)) — «Суфлёр» станет первым цифровым сотрудником.
- **JWT-валидация не подключена** (см. выше), **streaming (SSE) не сделан**, OTel-инструментирование — только метрики Prometheus, трейсов пока нет ([ADR-0017](../docs/adr/0017-observability.md)).
- Экстракция связей — правилами; LLM-экстрактор сущностей ([ADR-0013](../docs/adr/0013-graphrag-strategiya.md)) не подключён.

## Структура

```
backend/
├── sufler/        access · ingest · links · graph · graphrag · retriever · guardrails · rag · api · cli
├── data/lpa/      демо-корпус: отпуск, изменения к нему (отмена), командировки, доступ к ПДн (ACL)
├── tests/         GraphRAG, безопасность, смоук
├── requirements.txt · Dockerfile · .env.example
```
