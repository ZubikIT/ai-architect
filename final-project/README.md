# Финальный проект

> Источник ТЗ: Елена (Комьюнити-Менеджер), чат курса.

## Задача

Разработать **архитектуру и MVP ядра корпоративной интеллектуальной системы**.

Система должна работать **полностью автономно (On-premise / Air-gapped)**, без доступа к внешним API (OpenAI / Anthropic).

## Структура оценки

| Блок | Содержание | Вес |
|---|---|---|
| **1. Architecture & Design** | Полный пакет проектной документации + диаграммы | **40 %** |
| **2. Infrastructure & Stack** | Обоснованный выбор стека (актуально для 2026 / РФ) | ? |
| **3. Implementation (MVP)** | Реализация одной из тем (Cognitive / Advanced RAG / Security) | ? |

> Веса блоков 2 и 3 в брифе не указаны — уточнить у Елены / Андрея.

---

## Блок 1. Architecture & Design (40 %)

Полный пакет проектной документации с обоснованием через **ADR (Architecture Decision Records)**. Требуется представить **4 уровня детализации (C4 Model) + специализированные диаграммы**:

- [ ] **C4 Level 1 — Context**
      Интеграция AI-платформы в ландшафт (ERP, CRM, User Channels).
- [ ] **C4 Level 2 — Container**
      Микросервисная архитектура: API Gateway, Vector DB, LLM Serving Engine, Orchestrator, Frontend.
- [ ] **C4 Level 3 — Component**
      Внутреннее устройство Агента: Memory module, Planner, Tools interface.
- [ ] **Deployment Diagram**
      Физическое размещение. GPU-ресурсы, балансировка нагрузки, сегментация сети (DMZ, Internal), управление секретами (Vault).
- [ ] **Sequence Diagram**
      Флоу обработки сложного запроса:
      `User → Guardrails → Rerank → Agent Loop → Tool Execution → Response`.
- [ ] **ER Diagram**
      Модель данных: хранение векторов, чанков, истории сессий, логов, прав доступа (RBAC).
- [ ] **ADR-пакет** — ключевые архитектурные решения с trade-off анализом.

## Блок 2. Infrastructure & Stack

Выбор каждого компонента должен быть **обоснован в ADR (trade-off analysis)**.

| Слой | Кандидаты | Обязательные требования |
|---|---|---|
| **LLM Serving** | vLLM, SGLang, TGI | Квантование **AWQ / GGUF** для Consumer GPU, **KV-cache optimization** |
| **Models** | Qwen 2.5 / 3, DeepSeek-V3, T-lite / Saiga | Open Source + поддержка русского языка |
| **Vector Database** | Qdrant, Milvus, Weaviate | Self-hosted |
| **Orchestration** | **LangGraph** (Stateful Agents) или **LlamaIndex Workflows** | Линейные цепочки **запрещены** — нужна stateful-оркестрация |
| **Observability** | OpenTelemetry + Prometheus / Grafana | Трейсинг запросов; метрики токенов/сек, latency |

ADR на каждый слой:
- [ ] ADR: выбор LLM Serving Engine
- [ ] ADR: выбор модели (RU-поддержка, размер, лицензия)
- [ ] ADR: выбор Vector DB
- [ ] ADR: выбор Orchestration framework
- [ ] ADR: стратегия квантования и sizing GPU

## Блок 3. Implementation (MVP)

Реализовать функционал по **одной из тем** (выбор обосновать):

- [ ] **A. Cognitive Architecture** — реализация паттернов **ReAct**, **Plan-and-Solve** или **Multi-Agent Collaboration**
- [ ] **B. Advanced RAG** — **GraphRAG** (Knowledge Graphs) или **Multimodal RAG** (работа с изображениями / таблицами)
- [ ] **C. Security** — **Input/Output Guardrails** (фильтрация PII, защита от prompt injection)

> **Моя тема:** _не выбрана_

---

## Сводный чек-лист артефактов

- [x] Vision & Goals → [`docs/vision-goals.md`](docs/vision-goals.md)
- [x] Functional & Non-functional requirements → [`docs/requirements.md`](docs/requirements.md)
- [x] C4 L1 Context → [`diagrams/c4.md`](diagrams/c4.md)
- [x] C4 L2 Container → [`diagrams/c4.md`](diagrams/c4.md)
- [x] C4 L3 Component (Agent internals) → [`diagrams/c4.md`](diagrams/c4.md)
- [x] Deployment Diagram (GPU, DMZ, Vault) → [`diagrams/c4.md`](diagrams/c4.md)
- [x] Sequence Diagram (Guardrails → Rerank → Agent Loop → Tools) → [`diagrams/sequence-er.md`](diagrams/sequence-er.md)
- [x] ER Diagram (vectors, chunks, sessions, logs, RBAC) → [`diagrams/sequence-er.md`](diagrams/sequence-er.md)
- [x] ADR-пакет (serving, model, vector DB, orchestration, sizing + UI/connectors/MCP) → [`docs/adr/`](docs/adr/)
- [ ] MVP: код выбранной темы (A/B/C) с инструкцией запуска
- [ ] Observability: примеры трейсов и дашбордов
- [ ] Экономическое обоснование (TCO, GPU-часы, лицензии)
- [ ] Презентация для защиты

## Структура

- [`docs/`](./docs/) — Vision, HLD/LLD, ADR, Security model, Roadmap
- [`diagrams/`](./diagrams/) — C4 (L1–L3), Deployment, Sequence, ER
- [`economics/`](./economics/) — расчёты, обоснования, TCO

## Открытые вопросы

- [ ] Какие конкретно ERP / CRM нужно интегрировать на C4 L1 (любые / конкретные продукты)?
- [ ] Каков целевой профиль нагрузки (RPS, длина контекста, размер базы документов)?
- [ ] Есть ли ограничения по GPU (V100 / A100 / H100 / Consumer)?
- [ ] Веса блоков 2 и 3 в общей оценке.
- [ ] Допустима ли облачная инфраструктура (Yandex Cloud / Cloud.ru) для деплоя, или строго bare-metal on-prem?
