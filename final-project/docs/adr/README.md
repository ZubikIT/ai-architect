# Architecture Decision Records (ADR)

Лог ключевых архитектурных решений. Ведётся по принципу **Architecture as Code** (Markdown в Git, изменения — через коммит). Решения **не удаляются**: устаревшие переводятся в статус `deprecated` / `superseded`.

> **Пакет переведён на реальную платформу.** Выпускной проект описывает не вымышленный контур, а работающую платформу **ZubrIQ** ([описание as-is](../../../zubriq-platform/README.md)). Решения 0019–0026 приняты в проде и зафиксированы задним числом; ранние ADR сверены с реальностью — карта расхождений в [`adr-audit.md`](../adr-audit.md).
>
> Предмет проекта — **закрытый контур платформы** (свои модели, нулевой egress). Внешнее плечо существует как отдельный коммерческий режим и отсекается правами ключа ([ADR-0020](0020-dva-rezhima-dostupa.md)).

Формат — по шаблону [`../../../templates/adr.md`](../../../templates/adr.md). Имя файла: `NNNN-краткое-описание.md`. Раздел **Compliance & Ethics** обязателен для AI-решений (урок 08).

## Картина стека — как есть

- **Вход:** обратный прокси, wildcard-сертификат (ADR-0026) → продукты и OpenAI-совместимый API.
- **Центр:** шлюз моделей — ключи, бюджеты, учёт потребления, каталог (ADR-0019). Через него проходит **каждый** вызов модели.
- **Граница контура:** права ключа, проверка до вызова (ADR-0020). Закрытый режим — свой инференс; внешний — вне периметра проекта.
- **Инференс:** vLLM нативно на GPU-боксе (ADR-0003), MoE-модель в AWQ на 4× V100 (ADR-0002/0006 — с поправкой на реальное железо).
- **Знания:** хранилище векторов (ADR-0004 → [ADR-0027](0027-konveyer-ranzhirovaniya.md)); ранжирование — сервис платформы `bge-reranker-v2-m3`, и именно оно определяет качество. Граф связей и GraphRAG (ADR-0012/0013) **спроектированы, в платформу не встроены** — код в [`../../backend/`](../../backend/).
- **Агенты:** иерархия supervisor + роли-агенты (ADR-0015) — там же, встраивание предстоит.
- **Доступ:** Keycloak с федерацией каталога, группы в токене (ADR-0021) → материализованные метки на чанках и узлах (ADR-0016).
- **Состояние:** ключи и потребление в HA-кластере PostgreSQL (ADR-0022); биллинг читает его напрямую (ADR-0023).
- **Доставка:** кластер Talos с GitOps после инцидента с простоем шлюза (ADR-0024).
- **Продукты:** собственный чат вместо доработки открытого (ADR-0025).
- **Наблюдаемость:** трассировка LLM и метрики есть, сквозного трейсинга нет (ADR-0017).

## Статусы
`proposed` → `accepted` → (`deprecated` | `superseded by ADR-MMMM`) · либо `rejected` (с сохранением причины).

## Реестр

| ID | Решение | Статус | Дата |
|---|---|---|---|
| [ADR-0001](0001-on-premise-self-hosted-llm.md) | Self-hosted open-weight LLM вместо облачного API (on-premise / air-gapped) | accepted | 2026-05-26 |
| [ADR-0002](0002-vybor-modeli.md) | Выбор LLM — Qwen3.5-27B (open-weight, dense) | accepted | 2026-05-26 |
| [ADR-0003](0003-llm-serving-engine.md) | LLM Serving Engine — vLLM (vs SGLang, TGI) | proposed | 2026-05-26 |
| [ADR-0004](0004-vector-db.md) | Vector Database — Qdrant (vs Milvus, Weaviate) | superseded by ADR-0027 | 2026-05-26 |
| [ADR-0005](0005-orchestration.md) | Orchestration — LangGraph (vs LlamaIndex Workflows) | proposed | 2026-05-26 |
| [ADR-0006](0006-kvantovanie-i-sizing-gpu.md) | Квантование и sizing GPU — FP8 на 2× H100 NVL | accepted | 2026-05-26 |
| [ADR-0007](0007-chat-interface.md) | Чат-интерфейс — Open WebUI (SSO + Pipelines, мобайл Conduit) | superseded by ADR-0025 | 2026-05-26 |
| [ADR-0008](0008-knowledge-base-connectors.md) | Коннекторы к корпоративным БЗ — Onyx (Confluence/Jira/SharePoint) | proposed | 2026-05-26 |
| [ADR-0009](0009-mcp-integration-layer.md) | MCP как стандартный слой интеграции (Open WebUI + Onyx) | proposed | 2026-05-26 |
| [ADR-0010](0010-voice-stack.md) | Голосовой стек — self-hosted STT/TTS (faster-whisper/GigaAM + Silero) | proposed | 2026-05-27 |
| [ADR-0011](0011-sufler-pipeline-integration.md) | Интеграция Суфлёра как Open WebUI Pipeline + RBAC через Keycloak | superseded by ADR-0019 | 2026-05-27 |
| [ADR-0012](0012-graph-db.md) | Graph Database — Neo4j Community (vs ArangoDB, NebulaGraph, Memgraph) | proposed | 2026-09-11 |
| [ADR-0013](0013-graphrag-strategiya.md) | Стратегия GraphRAG — гибрид «вектор → обход графа» + онтология из 4 узлов | proposed | 2026-09-11 |
| [ADR-0014](0014-multimodalnyy-ingestion.md) | Мультимодальный ingestion — каскад «текстовый слой → layout → VL» с понижением доверия | proposed | 2026-09-11 |
| [ADR-0015](0015-topologiya-mas-cifrovye-sotrudniki.md) | Топология MAS «цифровые сотрудники» — supervisor + роли-агенты на LangGraph | proposed | 2026-09-11 |
| [ADR-0016](0016-acl-na-uzlah-grafa.md) | ACL на уровне узлов графа и чанков — материализованные метки + предикат в каждом запросе | proposed | 2026-09-11 |
| [ADR-0017](0017-observability.md) | Observability — единый OTel-слой → Jaeger + Langfuse, метрики в Prometheus-совместимое хранилище | proposed | 2026-09-11 |
| [ADR-0018](0018-security-testing.md) | Security testing и red teaming — вендор-нейтральный стек с ASR-гейтом в CI | proposed | 2026-09-11 |
| [ADR-0019](0019-shlyuz-modeley-kak-centr-platformy.md) | Шлюз моделей как центр платформы — ключи, бюджеты, учёт, маршрутизация | accepted | 2026-09-12 |
| [ADR-0020](0020-dva-rezhima-dostupa.md) | Два режима доступа и граница контура — разрешение на уровне ключа | accepted | 2026-09-12 |
| [ADR-0021](0021-identifikaciya-keycloak-federaciya.md) | Идентификация — Keycloak с федерацией каталога, права группами в токене | accepted | 2026-09-12 |
| [ADR-0022](0022-ha-postgresql-dlya-klyuchey-i-spenda.md) | Ключи и потребление — в общий HA-кластер PostgreSQL | accepted | 2026-09-12 |
| [ADR-0023](0023-billing-chitaet-shemu-shlyuza.md) | Биллинг читает базу шлюза напрямую — осознанный размен | accepted | 2026-09-12 |
| [ADR-0024](0024-klaster-i-gitops.md) | Переезд в кластер Talos с GitOps — выкат без простоя | accepted | 2026-09-12 |
| [ADR-0025](0025-svoy-chat-vmesto-dorabotki-chuzhogo.md) | Свой чат вместо доработки открытого | accepted | 2026-09-12 |
| [ADR-0026](0026-perimetr-i-sertifikaty.md) | Периметр — обратный прокси и wildcard через DNS-01 | accepted | 2026-09-12 |
| [ADR-0027](0027-konveyer-ranzhirovaniya.md) | Конвейер ранжирования вместо собственной модели реранка | accepted | 2026-09-12 |

## Планируемые ADR (из брифа проекта)
- [x] **ADR-0002** — выбор модели (RU-поддержка, размер, лицензия) → [ADR-0002](0002-vybor-modeli.md): Qwen3.5-27B (proposed)
- [x] **ADR-0003** — LLM Serving Engine: vLLM vs SGLang vs TGI → [ADR-0003](0003-llm-serving-engine.md) (proposed)
- [x] **ADR-0004** — Vector Database → [ADR-0004](0004-vector-db.md): Qdrant (superseded by [ADR-0027](0027-konveyer-ranzhirovaniya.md) — предметом решения оказалось не хранилище, а конвейер ранжирования)
- [x] **ADR-0005** — Orchestration framework → [ADR-0005](0005-orchestration.md): LangGraph (proposed)
- [x] **ADR-0006** — стратегия квантования и sizing GPU → [ADR-0006](0006-kvantovanie-i-sizing-gpu.md): FP8 на 2× H100 NVL (proposed)

**Дополнительно (вне брифа):**
- [x] **ADR-0007** — чат-интерфейс → [ADR-0007](0007-chat-interface.md): Open WebUI (accepted)
- [x] **ADR-0008** — коннекторы к корпоративным БЗ → [ADR-0008](0008-knowledge-base-connectors.md): Onyx (accepted; роль: совместная работа/общий поиск, Open WebUI = персонально, общий LLM)
- [x] **ADR-0009** — слой интеграции → [ADR-0009](0009-mcp-integration-layer.md): MCP (proposed; Open WebUI + Onyx, оба нативно поддерживают)
- [x] **ADR-0010** — голосовой стек (MVP этап 3) → [ADR-0010](0010-voice-stack.md): self-hosted faster-whisper/GigaAM + Silero (proposed)
- [x] **ADR-0011** — интеграция в реальный деплой → [ADR-0011](0011-sufler-pipeline-integration.md): Суфлёр-Pipe + Keycloak RBAC (proposed)

## Планируемые ADR (из уточнённого ТЗ, занятие [32](../../sessions/32-vybor-temy.md))
- [x] **ADR-0012** — Graph Database → [ADR-0012](0012-graph-db.md): Neo4j Community (proposed)
- [x] **ADR-0013** — стратегия GraphRAG и онтология → [ADR-0013](0013-graphrag-strategiya.md): гибрид + 4 типа узлов (proposed)
- [x] **ADR-0014** — [мультимодальный ingestion](0014-multimodalnyy-ingestion.md): каскад «текстовый слой → layout-парсер → VL на исключениях», провенанс `extracted_by` (proposed)
- [x] **ADR-0015** — [топология MAS «цифровые сотрудники»](0015-topologiya-mas-cifrovye-sotrudniki.md): иерархия supervisor + 4 роли, checkpointer, лимиты, ReAct-trace (proposed)
- [x] **ADR-0016** — [ACL на уровне узлов графа и чанков](0016-acl-na-uzlah-grafa.md): материализованные метки + предикат в каждом запросе, контекст из JWT (proposed)
- [x] **ADR-0017** — [Observability](0017-observability.md): единый OTel-слой → Jaeger + Langfuse, Golden Signals + GraphRAG-метрики, threshold-алерты с runbook (proposed)
- [x] **ADR-0018** — [security testing и red teaming](0018-security-testing.md): три контура (PR / ночь / релиз), Garak + PyRIT + Giskard, гейт по верхней границе интервала Уилсона (proposed)
