# Architecture Decision Records (ADR)

Лог ключевых архитектурных решений финального проекта — on-premise/air-gapped корпоративной AI-платформы. Ведётся по принципу **Architecture as Code** (Markdown в Git, изменения — через PR/коммит). Решения **не удаляются**: устаревшие переводятся в статус `deprecated` / `superseded`.

Формат — по шаблону [`../../../templates/adr.md`](../../../templates/adr.md). Имя файла: `NNNN-краткое-описание.md`. Раздел **Compliance & Ethics** обязателен для AI-решений (урок 08).

## Статусы
`proposed` → `accepted` → (`deprecated` | `superseded by ADR-MMMM`) · либо `rejected` (с сохранением причины).

## Реестр

| ID | Решение | Статус | Дата |
|---|---|---|---|
| [ADR-0001](0001-on-premise-self-hosted-llm.md) | Self-hosted open-weight LLM вместо облачного API (on-premise / air-gapped) | accepted | 2026-05-26 |
| [ADR-0002](0002-vybor-modeli.md) | Выбор LLM — Qwen3.6-27B (open-weight, dense) | proposed | 2026-05-26 |
| [ADR-0003](0003-llm-serving-engine.md) | LLM Serving Engine — vLLM (vs SGLang, TGI) | proposed | 2026-05-26 |
| [ADR-0006](0006-kvantovanie-i-sizing-gpu.md) | Квантование и sizing GPU — FP8 на 2× H100 | proposed | 2026-05-26 |

## Планируемые ADR (из брифа проекта)
- [x] **ADR-0002** — выбор модели (RU-поддержка, размер, лицензия) → [ADR-0002](0002-vybor-modeli.md): Qwen3.6-27B (proposed)
- [x] **ADR-0003** — LLM Serving Engine: vLLM vs SGLang vs TGI → [ADR-0003](0003-llm-serving-engine.md) (proposed)
- [ ] **ADR-0004** — Vector Database: Qdrant vs Milvus vs Weaviate (self-hosted)
- [ ] **ADR-0005** — Orchestration framework: LangGraph vs LlamaIndex Workflows
- [x] **ADR-0006** — стратегия квантования и sizing GPU → [ADR-0006](0006-kvantovanie-i-sizing-gpu.md): FP8 на 2× H100 (proposed)
