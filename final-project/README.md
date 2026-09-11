# Финальный проект

> **Тема работы: «Мультиагентная платформа цифровых корпоративных сотрудников»**
> Источник ТЗ: занятие [32 «Выбор темы и организация проектной работы»](sessions/32-vybor-temy.md) (Андрей Носов, 28.08.2026). Предварительный бриф (Елена, чат курса) заменён уточнённым ТЗ из ЛК.

## Задача

Спроектировать и реализовать **MVP производственного конвейера (End-to-End Pipeline)** для извлечения знаний из **неструктурированных данных** (сканы, чертежи, сложные PDF) в закрытом контуре.

Роль — **Platform Engineer & AI Architect**. Система работает **полностью автономно (On-premise / Air-gapped)**, без внешних API (OpenAI / Anthropic). Две проблемы, которые обязана решить архитектура:

1. **Галлюцинации и потеря контекста** → **GraphRAG** (нейро-символический подход);
2. **Разграничение доступа** → **Security-by-Design** на уровне **чанков / узлов графа**.

Официальное название варианта в ЛК: *«Построение защищённой платформы мультимодального анализа корпоративных знаний с использованием графовых подходов»*. Моя реализация добавляет поверх графового ядра мультиагентный слой — **цифровые сотрудники** (роли-агенты с собственными правами и инструментами).

## Структура оценки

| Блок | Содержание | Вес |
|---|---|---|
| **1. Architecture & Design** | Полный пакет проектной документации + диаграммы (ADR с trade-off) | **40 %** |
| **2. Infrastructure & Stack** | Обоснованный выбор стека (актуальность 2026) | не указан |
| **3. Implementation (MVP)** | Реализация по одной из тем (Cognitive / Advanced RAG / Security) | не указан |

---

## Блок 1. Architecture & Design (40 %)

| Диаграмма | Обязательное содержание | Статус |
|---|---|---|
| **C4 L1 — Context** | интеграция в ландшафт: ERP, CRM, User Channels | [x] [`diagrams/c4.md`](diagrams/c4.md) |
| **C4 L2 — Container** | API Gateway, Vector DB, LLM Serving Engine, Orchestrator, Frontend | [x] — обновить: +Graph DB, Control/Data Plane |
| **C4 L3 — Component** | внутреннее устройство агента: Memory, Planner, Tools interface | [x] — обновить под MAS |
| **Deployment** | GPU-ресурсы, балансировка, сегментация сети (DMZ / Internal), секреты (Vault) | [x] — обновить |
| **Sequence** | `User → Guardrails → Rerank → Agent Loop → Tool Execution → Response` | [x] [`diagrams/sequence-er.md`](diagrams/sequence-er.md) |
| **ER** | векторы, чанки, история сессий, логи, права доступа (RBAC) | [x] — +схема графа |
| **Data Flow** | поток данных ingestion → граф → retrieval → ответ | [ ] **нет — критерий «Не принято»** |
| **ADR-пакет** | ключевые решения с trade-off анализом | [x] 13 ADR → [`docs/adr/`](docs/adr/), нужны +5 |

## Блок 2. Infrastructure & Stack (2026)

Выбор каждого компонента обосновывается в **ADR (trade-off analysis)**.

| Слой | Требование ТЗ | Решение | ADR |
|---|---|---|---|
| **LLM Serving** | vLLM / SGLang / TGI; квантование (AWQ/GGUF для Consumer GPU), KV-cache optimization | vLLM, FP8 на 2× H100 NVL | [0003](docs/adr/0003-llm-serving-engine.md), [0006](docs/adr/0006-kvantovanie-i-sizing-gpu.md) |
| **Models** | Open Source с RU: Qwen 2.5/3, DeepSeek-V3, T-lite/Saiga | Qwen3.5-27B + собственная Zubr-VL-32B (мультимодальный парсинг) | [0002](docs/adr/0002-vybor-modeli.md), +ADR |
| **Vector DB** | self-hosted: Qdrant / Milvus / Weaviate | Qdrant | [0004](docs/adr/0004-vector-db.md) |
| **Graph DB** | Neo4j (образ в материалах ЛК) | Neo4j Community 5.x + гибрид с Qdrant | [0012](docs/adr/0012-graph-db.md), [0013](docs/adr/0013-graphrag-strategiya.md) |
| **Orchestration** | **LangGraph** / LlamaIndex Workflows; **линейные цепочки запрещены** | LangGraph | [0005](docs/adr/0005-orchestration.md) |
| **Observability** | OpenTelemetry (трейсинг), Prometheus / Grafana (токены/сек, latency) | **не реализовано** | +ADR |

**Принято:** [Graph DB — Neo4j](docs/adr/0012-graph-db.md) · [стратегия GraphRAG и онтология](docs/adr/0013-graphrag-strategiya.md). **Планируется:** мультимодальный ingestion · топология MAS «цифровые сотрудники» · ACL на узлах графа · Observability · Security testing / red teaming (по [методике урока 33](sessions/33-konsultaciya.md)).

## Блок 3. Implementation (MVP)

- [x] **B. Advanced RAG** — **GraphRAG** (обязателен) + мультимодальный ingestion сканов/чертежей
- [x] **A. Cognitive Architecture** — Multi-Agent Collaboration: supervisor + роли-агенты (цифровые сотрудники) на LangGraph
- [x] **C. Security** — Input/Output Guardrails (PII, prompt injection) + ACL на уровне узлов графа

Дизайн ядра и доменная часть (корпус ЛПА, ingestion, hybrid search) — [`docs/mvp.md`](docs/mvp.md); «Суфлёр» становится одним из цифровых сотрудников платформы.

**Рекомендации ТЗ:** модель не обучать (брать pre-trained); онтологию начинать с 3–4 типов узлов; при нехватке VRAM — offloading на CPU или аренда GPU (Yandex DataSphere / Cloud.ru) на пару часов для записи демо.

---

## Критерии оценки

**«Не принято», если:**
- [ ] используются облачные API (OpenAI / Anthropic) — ✅ исключено ([ADR-0001](docs/adr/0001-on-premise-self-hosted-llm.md))
- [ ] отсутствует диаграмма **Deployment** или **Data Flow** — ⚠️ Data Flow нет
- [ ] **нет реализации GraphRAG** (простой векторный поиск не принимается) — ⚠️ **главный блокер**

**Критично:**
- [ ] **Security** — User B не получает ответ по секретному документу (демонстрируемый тест)
- [ ] **Architecture** — явное разделение **Control Plane** (агенты) и **Data Plane** (БД / модели)
- [ ] **Stack** — LangGraph / state machine, а не линейные скрипты

**Желательно:**
- [ ] потоковый ответ (Streaming)
- [ ] unit-тесты на промпты (**LLM-as-a-Judge**)

## Формат сдачи

```
/infra      Helm charts или docker-compose — весь стек (DBs + Apps)
/backend    код агентов (Python) + API
/docs       архитектурная документация (ADD) в Markdown/PDF
```

- **Видео-демо (Deep Dive) 5–7 мин** — «под капотом»: трейсы Jaeger/Langfuse, логи vLLM, визуализация графа в браузере Neo4j.
- **Нагрузочный отчёт** — RPS и латентность на своём железе (методика — [ДЗ-24](../24-high-load-low-latency/Zubik_DZ-24_highload-realtime.md)).
- **Презентация защиты** — по [шаблону OTUS](sessions/artifacts/otus-shablon-prezentacii-zashchity.pdf) (структура — в [конспекте занятия 33](sessions/33-konsultaciya.md)).

---

## Сводный чек-лист артефактов

- [x] Vision & Goals → [`docs/vision-goals.md`](docs/vision-goals.md)
- [x] Functional & Non-functional requirements → [`docs/requirements.md`](docs/requirements.md)
- [x] C4 L1 / L2 / L3 + Deployment → [`diagrams/c4.md`](diagrams/c4.md) _(обновить под граф, MAS, Control/Data Plane)_
- [x] Sequence + ER → [`diagrams/sequence-er.md`](diagrams/sequence-er.md) _(обновить: схема графа)_
- [ ] **Data Flow диаграмма** — обязательна
- [x] ADR-пакет (13 решений, включая [Graph DB](docs/adr/0012-graph-db.md) и [стратегию GraphRAG](docs/adr/0013-graphrag-strategiya.md)) → [`docs/adr/`](docs/adr/) _(+5 планируемых)_
- [x] Экономическое обоснование (TCO, GPU-часы, лицензии) → [`economics/tco.md`](economics/tco.md)
- [x] MVP: домен, ingestion ЛПА, hybrid RAG (этапы 1–2) → [`mvp/`](mvp/)
- [ ] **GraphRAG-ядро** (Neo4j: онтология, построение графа, graph-augmented retrieval) — _спроектировано в [ADR-0013](docs/adr/0013-graphrag-strategiya.md), не реализовано_
- [ ] **Мультимодальный ingestion** (сканы, чертежи, сложные PDF)
- [ ] **Мультиагентный слой** (supervisor + роли-агенты на LangGraph)
- [ ] **ACL на уровне узлов графа + тест «User B»**
- [ ] Observability: OTel → Jaeger + Langfuse, Prometheus/Grafana, примеры трейсов и дашбордов
- [ ] Monorepo-раскладка `/infra`, `/backend`, `/docs` + `docker-compose` всего стека
- [ ] Streaming (SSE) и LLM-as-a-Judge тесты промптов
- [ ] Нагрузочный отчёт (RPS / latency)
- [ ] Видео-демо 5–7 мин
- [ ] Презентация для защиты
- [ ] Голос (STT/TTS) — [ADR-0010](docs/adr/0010-voice-stack.md), опциональное расширение вне требований ТЗ

## Структура

- [`sessions/`](./sessions/) — конспекты занятий проектного блока (32–36) и материалы ЛК
- [`docs/`](./docs/) — Vision, требования, дизайн MVP, ADR
- [`diagrams/`](./diagrams/) — C4 (L1–L3), Deployment, Sequence, ER
- [`economics/`](./economics/) — расчёты, обоснования, TCO
- [`mvp/`](./mvp/) — код MVP (переедет в `/backend` при переходе на monorepo-раскладку)

## Открытые вопросы

- [ ] Дедлайн сдачи (в ЛК не проставлен) и дата защиты (занятие 34).
- [ ] Веса блоков 2 и 3 в общей оценке.
- [ ] Обязательны ли датасеты из материалов ТЗ при наличии собственного корпуса ЛПА.
- [ ] Достаточно ли `docker-compose` вместо Helm в `/infra`.
- [ ] Глубина GraphRAG: гибрид «граф + вектор» с обходом 1–2 хопа vs community detection/summarization (Microsoft GraphRAG).
- [ ] Формат и минимальный объём нагрузочного отчёта.

**Закрыто уточнённым ТЗ:** ограничения по GPU (Consumer допустим при квантовании; offloading или аренда GPU для демо) · допустимость облака (для демо — да; облачные LLM-API — запрещены) · какие ERP/CRM на L1 (любые, в объёме контекста).
