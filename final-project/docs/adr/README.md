# Architecture Decision Records (ADR)

Лог ключевых архитектурных решений финального проекта — on-premise/air-gapped корпоративной AI-платформы. Ведётся по принципу **Architecture as Code** (Markdown в Git, изменения — через PR/коммит). Решения **не удаляются**: устаревшие переводятся в статус `deprecated` / `superseded`.

Формат — по шаблону [`../../../templates/adr.md`](../../../templates/adr.md). Имя файла: `NNNN-краткое-описание.md`. Раздел **Compliance & Ethics** обязателен для AI-решений (урок 08).

## Целевая картина стека
Две пользовательские плоскости поверх **одного LLM**:
- **Персональная:** Open WebUI (ADR-0007) → личный ассистент / агентный чат (LangGraph, ADR-0005; RAG на Qdrant, ADR-0004).
- **Совместная:** Onyx (ADR-0008) → поиск по общим базам знаний (Confluence/Jira/SharePoint), permission-aware.
- **Общее ядро:** Qwen3.5 (ADR-0002) на vLLM/FP8 (ADR-0003/0006), 2× H100 NVL, on-prem/air-gapped (ADR-0001).
- **Знания:** гибрид **Qdrant** (dense+BM25, ADR-0004) + **Neo4j** (граф связей ЛПА, ADR-0012); retrieval — vector-first с обходом графа на 1–2 хопа и ACL-предикатом (ADR-0013).

## Статусы
`proposed` → `accepted` → (`deprecated` | `superseded by ADR-MMMM`) · либо `rejected` (с сохранением причины).

## Реестр

| ID | Решение | Статус | Дата |
|---|---|---|---|
| [ADR-0001](0001-on-premise-self-hosted-llm.md) | Self-hosted open-weight LLM вместо облачного API (on-premise / air-gapped) | accepted | 2026-05-26 |
| [ADR-0002](0002-vybor-modeli.md) | Выбор LLM — Qwen3.5-27B (open-weight, dense) | proposed | 2026-05-26 |
| [ADR-0003](0003-llm-serving-engine.md) | LLM Serving Engine — vLLM (vs SGLang, TGI) | proposed | 2026-05-26 |
| [ADR-0004](0004-vector-db.md) | Vector Database — Qdrant (vs Milvus, Weaviate) | proposed | 2026-05-26 |
| [ADR-0005](0005-orchestration.md) | Orchestration — LangGraph (vs LlamaIndex Workflows) | proposed | 2026-05-26 |
| [ADR-0006](0006-kvantovanie-i-sizing-gpu.md) | Квантование и sizing GPU — FP8 на 2× H100 NVL | proposed | 2026-05-26 |
| [ADR-0007](0007-chat-interface.md) | Чат-интерфейс — Open WebUI (SSO + Pipelines, мобайл Conduit) | accepted | 2026-05-26 |
| [ADR-0008](0008-knowledge-base-connectors.md) | Коннекторы к корпоративным БЗ — Onyx (Confluence/Jira/SharePoint) | accepted | 2026-05-26 |
| [ADR-0009](0009-mcp-integration-layer.md) | MCP как стандартный слой интеграции (Open WebUI + Onyx) | proposed | 2026-05-26 |
| [ADR-0010](0010-voice-stack.md) | Голосовой стек — self-hosted STT/TTS (faster-whisper/GigaAM + Silero) | proposed | 2026-05-27 |
| [ADR-0011](0011-sufler-pipeline-integration.md) | Интеграция Суфлёра как Open WebUI Pipeline + RBAC через Keycloak | proposed | 2026-05-27 |
| [ADR-0012](0012-graph-db.md) | Graph Database — Neo4j Community (vs ArangoDB, NebulaGraph, Memgraph) | proposed | 2026-09-11 |
| [ADR-0013](0013-graphrag-strategiya.md) | Стратегия GraphRAG — гибрид «вектор → обход графа» + онтология из 4 узлов | proposed | 2026-09-11 |

## Планируемые ADR (из брифа проекта)
- [x] **ADR-0002** — выбор модели (RU-поддержка, размер, лицензия) → [ADR-0002](0002-vybor-modeli.md): Qwen3.5-27B (proposed)
- [x] **ADR-0003** — LLM Serving Engine: vLLM vs SGLang vs TGI → [ADR-0003](0003-llm-serving-engine.md) (proposed)
- [x] **ADR-0004** — Vector Database → [ADR-0004](0004-vector-db.md): Qdrant (proposed)
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
- [ ] **ADR-0014** — мультимодальный ingestion (сканы, чертежи, сложные PDF): Zubr-VL-32B + layout-парсинг
- [ ] **ADR-0015** — топология MAS «цифровые сотрудники»: supervisor + роли-агенты на LangGraph
- [ ] **ADR-0016** — ACL на уровне узлов графа и чанков (Keycloak → role context → предикат в Cypher и payload-фильтр Qdrant)
- [ ] **ADR-0017** — Observability: OpenTelemetry → Jaeger, Langfuse, Prometheus/Grafana
- [ ] **ADR-0018** — security testing и red teaming по [методике занятия 33](../../sessions/33-konsultaciya.md): Garak + PyRIT, порог ASR в CI
