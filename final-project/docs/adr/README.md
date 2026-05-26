# Architecture Decision Records (ADR)

Лог ключевых архитектурных решений финального проекта — on-premise/air-gapped корпоративной AI-платформы. Ведётся по принципу **Architecture as Code** (Markdown в Git, изменения — через PR/коммит). Решения **не удаляются**: устаревшие переводятся в статус `deprecated` / `superseded`.

Формат — по шаблону [`../../../templates/adr.md`](../../../templates/adr.md). Имя файла: `NNNN-краткое-описание.md`. Раздел **Compliance & Ethics** обязателен для AI-решений (урок 08).

## Целевая картина стека
Две пользовательские плоскости поверх **одного LLM**:
- **Персональная:** Open WebUI (ADR-0007) → личный ассистент / агентный чат (LangGraph, ADR-0005; RAG на Qdrant, ADR-0004).
- **Совместная:** Onyx (ADR-0008) → поиск по общим базам знаний (Confluence/Jira/SharePoint), permission-aware.
- **Общее ядро:** Qwen3.6 (ADR-0002) на vLLM/FP8 (ADR-0003/0006), 2× H100 NVL, on-prem/air-gapped (ADR-0001).

## Статусы
`proposed` → `accepted` → (`deprecated` | `superseded by ADR-MMMM`) · либо `rejected` (с сохранением причины).

## Реестр

| ID | Решение | Статус | Дата |
|---|---|---|---|
| [ADR-0001](0001-on-premise-self-hosted-llm.md) | Self-hosted open-weight LLM вместо облачного API (on-premise / air-gapped) | accepted | 2026-05-26 |
| [ADR-0002](0002-vybor-modeli.md) | Выбор LLM — Qwen3.6-27B (open-weight, dense) | proposed | 2026-05-26 |
| [ADR-0003](0003-llm-serving-engine.md) | LLM Serving Engine — vLLM (vs SGLang, TGI) | proposed | 2026-05-26 |
| [ADR-0004](0004-vector-db.md) | Vector Database — Qdrant (vs Milvus, Weaviate) | proposed | 2026-05-26 |
| [ADR-0005](0005-orchestration.md) | Orchestration — LangGraph (vs LlamaIndex Workflows) | proposed | 2026-05-26 |
| [ADR-0006](0006-kvantovanie-i-sizing-gpu.md) | Квантование и sizing GPU — FP8 на 2× H100 NVL | proposed | 2026-05-26 |
| [ADR-0007](0007-chat-interface.md) | Чат-интерфейс — Open WebUI (SSO + Pipelines, мобайл Conduit) | accepted | 2026-05-26 |
| [ADR-0008](0008-knowledge-base-connectors.md) | Коннекторы к корпоративным БЗ — Onyx (Confluence/Jira/SharePoint) | accepted | 2026-05-26 |
| [ADR-0009](0009-mcp-integration-layer.md) | MCP как стандартный слой интеграции (Open WebUI + Onyx) | proposed | 2026-05-26 |

## Планируемые ADR (из брифа проекта)
- [x] **ADR-0002** — выбор модели (RU-поддержка, размер, лицензия) → [ADR-0002](0002-vybor-modeli.md): Qwen3.6-27B (proposed)
- [x] **ADR-0003** — LLM Serving Engine: vLLM vs SGLang vs TGI → [ADR-0003](0003-llm-serving-engine.md) (proposed)
- [x] **ADR-0004** — Vector Database → [ADR-0004](0004-vector-db.md): Qdrant (proposed)
- [x] **ADR-0005** — Orchestration framework → [ADR-0005](0005-orchestration.md): LangGraph (proposed)
- [x] **ADR-0006** — стратегия квантования и sizing GPU → [ADR-0006](0006-kvantovanie-i-sizing-gpu.md): FP8 на 2× H100 NVL (proposed)

**Дополнительно (вне брифа):**
- [x] **ADR-0007** — чат-интерфейс → [ADR-0007](0007-chat-interface.md): Open WebUI (accepted)
- [x] **ADR-0008** — коннекторы к корпоративным БЗ → [ADR-0008](0008-knowledge-base-connectors.md): Onyx (accepted; роль: совместная работа/общий поиск, Open WebUI = персонально, общий LLM)
- [x] **ADR-0009** — слой интеграции → [ADR-0009](0009-mcp-integration-layer.md): MCP (proposed; Open WebUI + Onyx, оба нативно поддерживают)
