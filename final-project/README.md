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
| **C4 L1 — Context** | интеграция в ландшафт: ERP, CRM, User Channels | [x] [`docs/diagrams/c4.md`](docs/diagrams/c4.md) |
| **C4 L2 — Container** | API Gateway, Vector DB, LLM Serving Engine, Orchestrator, Frontend | [x] +Neo4j, Control/Data Plane, Observability |
| **C4 L3 — Component** | внутреннее устройство агента: Memory, Planner, Tools interface | [x] под MAS: RequestContext, supervisor, роли, Repository |
| **Deployment** | GPU-ресурсы, балансировка, сегментация сети (DMZ / Internal), секреты (Vault) | [x] Internal разделён на Control/Data Plane |
| **Sequence** | `User → Guardrails → Rerank → Agent Loop → Tool Execution → Response` | [x] [`docs/diagrams/sequence-er.md`](docs/diagrams/sequence-er.md) |
| **ER** | векторы, чанки, история сессий, логи, права доступа (RBAC) | [x] _(дополнить схемой графа и полями провенанса)_ |
| **Data Flow** | поток данных ingestion → граф → retrieval → ответ | [x] [`docs/diagrams/data-flow.md`](docs/diagrams/data-flow.md) |
| **ADR-пакет** | ключевые решения с trade-off анализом | [x] **18 ADR** → [`docs/adr/`](docs/adr/) — пакет закрыт |

## Блок 2. Infrastructure & Stack (2026)

Выбор каждого компонента обосновывается в **ADR (trade-off analysis)**.

| Слой | Требование ТЗ | Решение | ADR |
|---|---|---|---|
| **LLM Serving** | vLLM / SGLang / TGI; квантование (AWQ/GGUF для Consumer GPU), KV-cache optimization | vLLM, FP8 на 2× H100 NVL | [0003](docs/adr/0003-llm-serving-engine.md), [0006](docs/adr/0006-kvantovanie-i-sizing-gpu.md) |
| **Models** | Open Source с RU: Qwen 2.5/3, DeepSeek-V3, T-lite/Saiga | Qwen3.5-27B (текст) + Qwen3-VL с адаптером Zubr (разбор страниц-исключений) | [0002](docs/adr/0002-vybor-modeli.md), [0014](docs/adr/0014-multimodalnyy-ingestion.md) |
| **Vector DB** | self-hosted: Qdrant / Milvus / Weaviate | Qdrant | [0004](docs/adr/0004-vector-db.md) |
| **Graph DB** | Neo4j (образ в материалах ЛК) | Neo4j Community 5.x + гибрид с Qdrant | [0012](docs/adr/0012-graph-db.md), [0013](docs/adr/0013-graphrag-strategiya.md) |
| **Orchestration** | **LangGraph** / LlamaIndex Workflows; **линейные цепочки запрещены** | LangGraph — реализовано ([`mas.py`](backend/sufler/mas.py)) | [0005](docs/adr/0005-orchestration.md), [0015](docs/adr/0015-topologiya-mas-cifrovye-sotrudniki.md) |
| **Observability** | OpenTelemetry (трейсинг), Prometheus / Grafana (токены/сек, latency) | OTel → Jaeger + Langfuse, VictoriaMetrics + Grafana | [0017](docs/adr/0017-observability.md) |

**Принято:** [Graph DB — Neo4j](docs/adr/0012-graph-db.md) · [стратегия GraphRAG и онтология](docs/adr/0013-graphrag-strategiya.md). [ACL на узлах графа](docs/adr/0016-acl-na-uzlah-grafa.md) · [мультимодальный ingestion](docs/adr/0014-multimodalnyy-ingestion.md) · [топология MAS](docs/adr/0015-topologiya-mas-cifrovye-sotrudniki.md) · [Observability](docs/adr/0017-observability.md) · [security testing](docs/adr/0018-security-testing.md) — **ADR-пакет закрыт** (18 решений).

## Блок 3. Implementation (MVP)

- [x] **B. Advanced RAG** — **GraphRAG** (обязателен) + мультимодальный ingestion сканов/чертежей
- [x] **A. Cognitive Architecture** — Multi-Agent Collaboration: supervisor + роли-агенты (цифровые сотрудники) на LangGraph — реализовано, [`backend/sufler/mas.py`](backend/sufler/mas.py)
- [x] **C. Security** — Input/Output Guardrails (PII, prompt injection) + ACL на уровне узлов графа

Дизайн ядра и доменная часть (корпус ЛПА, ingestion, hybrid search) — [`docs/mvp.md`](docs/mvp.md); «Суфлёр» становится одним из цифровых сотрудников платформы.

**Рекомендации ТЗ:** модель не обучать (брать pre-trained); онтологию начинать с 3–4 типов узлов; при нехватке VRAM — offloading на CPU или аренда GPU (Yandex DataSphere / Cloud.ru) на пару часов для записи демо.

---

## Критерии оценки

**«Не принято», если:**
- [ ] используются облачные API (OpenAI / Anthropic) — ✅ исключено ([ADR-0001](docs/adr/0001-on-premise-self-hosted-llm.md))
- [x] отсутствует диаграмма **Deployment** или **Data Flow** — ✅ обе есть ([Deployment](docs/diagrams/c4.md#deployment), [Data Flow](docs/diagrams/data-flow.md))
- [x] **нет реализации GraphRAG** (простой векторный поиск не принимается) — ✅ реализовано: [`backend/sufler/graph.py`](backend/sufler/graph.py), [`graphrag.py`](backend/sufler/graphrag.py); эффект доказан тестом с контрольным замером

**Критично:**
- [x] **Security** — User B не получает ответ по секретному документу — ✅ автотест [`test_graphrag.py`](backend/tests/test_graphrag.py) (проверяется и контекст LLM, не только ответ); роли берутся из подписанного токена, а не из тела запроса — [`test_auth.py`](backend/tests/test_auth.py)
- [x] **Architecture** — явное разделение **Control Plane** / **Data Plane** ✅ в [C4 L2](docs/diagrams/c4.md#c2--containers), [C3](docs/diagrams/c4.md#c3--components-agent-internals--langgraph), [Deployment](docs/diagrams/c4.md#deployment) и [Data Flow](docs/diagrams/data-flow.md) — осталось подтвердить реализацией
- [x] **Stack** — LangGraph / state machine, а не линейные скрипты — ✅ супервизор ⇄ роли-агенты с циклом, ветвлением, лимитами и checkpointer: [`backend/sufler/mas.py`](backend/sufler/mas.py); структура графа выполнения проверяется тестом `test_execution_graph_has_branch_and_cycle`

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
- [x] C4 L1 / L2 / L3 + Deployment → [`docs/diagrams/c4.md`](docs/diagrams/c4.md) _(обновлены под граф, MAS, Control/Data Plane)_
- [x] Sequence + ER → [`docs/diagrams/sequence-er.md`](docs/diagrams/sequence-er.md) _(дополнить схемой графа и провенансом)_
- [x] **Data Flow диаграмма** (ingestion, query, границы доверия, классификация данных) → [`docs/diagrams/data-flow.md`](docs/diagrams/data-flow.md)
- [x] ADR-пакет (**18 решений**, включая [Graph DB](docs/adr/0012-graph-db.md), [GraphRAG](docs/adr/0013-graphrag-strategiya.md), [ingestion](docs/adr/0014-multimodalnyy-ingestion.md), [MAS](docs/adr/0015-topologiya-mas-cifrovye-sotrudniki.md), [ACL](docs/adr/0016-acl-na-uzlah-grafa.md), [Observability](docs/adr/0017-observability.md), [security testing](docs/adr/0018-security-testing.md)) → [`docs/adr/`](docs/adr)
- [x] Экономическое обоснование (TCO, GPU-часы, лицензии) → [`docs/economics/tco.md`](docs/economics/tco.md)
- [x] MVP: домен, ingestion ЛПА, hybrid RAG (этапы 1–2) → [`backend/`](backend/)
- [x] **GraphRAG-ядро** (онтология, построение графа, graph-augmented retrieval) → [`backend/`](backend/) — **прогнан на живой Neo4j**: паритет с in-memory проверен тестом по всему корпусу для трёх наборов ролей; прогон вскрыл и закрыл 3 расхождения боевого бэкенда
- [ ] **Мультимодальный ingestion** (сканы, чертежи, сложные PDF) — _спроектирован в [ADR-0014](docs/adr/0014-multimodalnyy-ingestion.md), не реализован_
- [x] **Мультиагентный слой** (supervisor + роли-агенты на LangGraph) → [`mas.py`](backend/sufler/mas.py), [`roles.py`](backend/sufler/roles.py), [`tools.py`](backend/sufler/tools.py) — 4 роли, детерминированная маршрутизация, least privilege на инструменте, лимиты и ReAct-trace _(замеры на golden set не сделаны → [ADR-0015](docs/adr/0015-topologiya-mas-cifrovye-sotrudniki.md) остаётся `proposed`)_
- [x] **ACL на уровне узлов графа + тест «User B»** → [`access.py`](backend/sufler/access.py), [`test_graphrag.py`](backend/tests/test_graphrag.py)
- [x] **Граница доверия: роли из проверенного JWT, а не из тела запроса** → [`auth.py`](backend/sufler/auth.py), [`test_auth.py`](backend/tests/test_auth.py) — подпись по JWKS, фиксированный список алгоритмов, негативные случаи (подмена `RS256→HS256`, `alg: none`, чужой `aud`/`iss`) _(против живого Keycloak не прогонялось)_
- [ ] Observability: OTel → Jaeger + Langfuse, Prometheus/Grafana, примеры трейсов и дашбордов — _спроектировано в [ADR-0017](docs/adr/0017-observability.md); дашборд Суфлёра уже в коде_
- [x] Monorepo-раскладка `/infra`, `/backend`, `/docs` + [`docker-compose`](infra/docker-compose.yml) всего стека — профиль `core` поднят и проверен (Neo4j + Qdrant + PostgreSQL) _(пины образов по digest и профиль red teaming — TODO)_
- [ ] Streaming (SSE) и LLM-as-a-Judge тесты промптов — _методика в [ADR-0018](docs/adr/0018-security-testing.md)_
- [ ] Нагрузочный отчёт (RPS / latency)
- [ ] Видео-демо 5–7 мин
- [ ] Презентация для защиты
- [ ] Голос (STT/TTS) — [ADR-0010](docs/adr/0010-voice-stack.md), опциональное расширение вне требований ТЗ

## Структура (monorepo по формату сдачи)

```
final-project/
├── infra/        docker-compose всего стека (DBs + Apps + observability)
├── backend/      код сервиса и агентов (Python, FastAPI)
├── docs/         архитектурная документация: ADR, диаграммы, требования, экономика
└── sessions/     конспекты занятий проектного блока (32–36) и материалы ЛК
```

- [`infra/`](infra/) — [состав стека и запуск](infra/README.md)
- [`backend/`](backend/) — RAG-сервис «Суфлёр» (этапы 1–2); станет одним из цифровых сотрудников платформы
- [`docs/adr/`](docs/adr/) — 18 ADR · [`docs/diagrams/`](docs/diagrams/) — C4, Deployment, Data Flow, Sequence, ER · [`docs/economics/`](docs/economics/) — TCO · [`docs/mvp.md`](docs/mvp.md) — дизайн MVP

## Открытые вопросы

- [ ] Дедлайн сдачи (в ЛК не проставлен) и дата защиты (занятие 34).
- [ ] Веса блоков 2 и 3 в общей оценке.
- [ ] Обязательны ли датасеты из материалов ТЗ при наличии собственного корпуса ЛПА.
- [ ] Достаточно ли `docker-compose` вместо Helm в `/infra`.
- [ ] Глубина GraphRAG: гибрид «граф + вектор» с обходом 1–2 хопа vs community detection/summarization (Microsoft GraphRAG).
- [ ] Формат и минимальный объём нагрузочного отчёта.

**Закрыто уточнённым ТЗ:** ограничения по GPU (Consumer допустим при квантовании; offloading или аренда GPU для демо) · допустимость облака (для демо — да; облачные LLM-API — запрещены) · какие ERP/CRM на L1 (любые, в объёме контекста).
