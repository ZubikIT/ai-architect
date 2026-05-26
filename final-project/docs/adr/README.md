# Architecture Decision Records (ADR)

Лог ключевых архитектурных решений финального проекта — on-premise/air-gapped корпоративной AI-платформы. Ведётся по принципу **Architecture as Code** (Markdown в Git, изменения — через PR/коммит). Решения **не удаляются**: устаревшие переводятся в статус `deprecated` / `superseded`.

Формат — по шаблону [`../../../templates/adr.md`](../../../templates/adr.md). Имя файла: `NNNN-краткое-описание.md`. Раздел **Compliance & Ethics** обязателен для AI-решений (урок 08).

## Статусы
`proposed` → `accepted` → (`deprecated` | `superseded by ADR-MMMM`) · либо `rejected` (с сохранением причины).

## Реестр

| ID | Решение | Статус | Дата |
|---|---|---|---|
| [ADR-0001](0001-on-premise-self-hosted-llm.md) | Self-hosted open-weight LLM вместо облачного API (on-premise / air-gapped) | accepted | 2026-05-26 |
| [ADR-0003](0003-llm-serving-engine.md) | LLM Serving Engine — vLLM (vs SGLang, TGI) | proposed | 2026-05-26 |

## Планируемые ADR (из брифа проекта)
- [ ] **ADR-0002** — выбор модели (RU-поддержка, размер, лицензия): Qwen 2.5/3, DeepSeek, T-lite / Saiga
- [x] **ADR-0003** — LLM Serving Engine: vLLM vs SGLang vs TGI → [ADR-0003](0003-llm-serving-engine.md) (proposed)
- [ ] **ADR-0004** — Vector Database: Qdrant vs Milvus vs Weaviate (self-hosted)
- [ ] **ADR-0005** — Orchestration framework: LangGraph vs LlamaIndex Workflows
- [ ] **ADR-0006** — стратегия квантования (AWQ / GGUF) и sizing GPU
