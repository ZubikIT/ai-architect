# `/infra` — развёртывание стека

Формат сдачи по ТЗ: «Helm charts или docker-compose для поднятия всего стека (DBs + Apps)». Здесь — **docker-compose** как dev/demo-развёртывание; прод-топология описана в [Deployment-диаграмме](../docs/diagrams/c4.md#deployment).

## Состав

| Сервис | Роль | Решение |
|---|---|---|
| `neo4j` | граф знаний, Neo4j Browser для визуализации | [ADR-0012](../docs/adr/0012-graph-db.md) |
| `qdrant` | dense-индекс (BM25 — в процессе), RBAC pre-filter по ролям; подключается через `QDRANT_URL` | [ADR-0004](../docs/adr/0004-vector-db.md) |
| `postgres` | checkpointer LangGraph, сессии, журнал доступа | [ADR-0015](../docs/adr/0015-topologiya-mas-cifrovye-sotrudniki.md), [ADR-0016](../docs/adr/0016-acl-na-uzlah-grafa.md) |
| `backend` | API, агенты, слой репозитория | [`../backend`](../backend/) |
| `otel-collector` | приём спанов и метрик | [ADR-0017](../docs/adr/0017-observability.md) |
| `jaeger` | трейсы (кадр для видео-демо) | ADR-0017 |
| `victoriametrics` | Prometheus-совместимое хранилище метрик | ADR-0017 |
| `grafana` | дашборды Golden Signals + GraphRAG | ADR-0017 |

**Вне compose:** `vLLM` живёт на GPU-ноде и подключается как внешний OpenAI-совместимый эндпоинт (`OPENAI_BASE_URL`); `Langfuse` развёрнут в контуре отдельно и получает трейсы от того же OTel-слоя; `Keycloak` — корпоративный, сюда приходит только его JWKS.

## Запуск

```bash
cp .env.example .env        # задать пароли; в контуре значения приходят из Vault
docker compose --profile core up -d              # знания + приложение
docker compose --profile core --profile obs up -d # + наблюдаемость
```

Проверка: Neo4j Browser — `http://localhost:7474`, Jaeger — `http://localhost:16686`, Grafana — `http://localhost:3000`, API — `http://localhost:8080/healthz`.

Оба профиля подняты и проверены. Профиль `core`: граф строится в живой Neo4j, вектор ложится в Qdrant (19 точек, dim 384), набор тестов проходит против стека целиком. Прогон вскрыл три расхождения боевого бэкенда с демо-режимом — разобраны в [`../backend/README.md`](../backend/README.md#живой-прогон-что-нашёл-боевой-бэкенд).

Профиль `obs` тоже прогнан, и прогон вскрыл **две молча сломанные конфигурации**:

| Что было | Чем это оборачивалось |
|---|---|
| `probabilistic_sampler` с `sampling_percentage: 20` | четыре трейса из пяти не доезжали до Jaeger: `request_id` из ответа не находился, и выглядело это как «трейсинга нет». ADR-0017 требует другого — **полные трейсы для ошибок и медленных запросов**, а это tail-based решение. Заменено на `tail_sampling` с политиками: ошибки, медленные (> 2 с), отказы по правам и блоки guardrail — всегда; остальное — процентом |
| `${VLLM_METRICS_TARGET:-...}` в `scrape.yml` | VictoriaMetrics **не разворачивает** синтаксис compose: job'ы `vllm-engine` и `gpu` молча пропускались («invalid port after host»), метрик vLLM и GPU не существовало вовсе. Правильный синтаксис — `%{ENV_VAR}`, значения по умолчанию подставляет compose в окружение контейнера |

Grafana больше не пустая: датасорс и дашборд «GraphRAG и цифровые сотрудники» подкладываются кодом ([`grafana/`](grafana/)) — Golden Signals, доля ответов со сработавшим ребром `ОТМЕНЯЕТ`, время обхода графа по бэкендам, маршрутизация и лимиты MAS, отказы ACL и отклонённые токены.

Запуск сервиса из исходников против поднятых БД (быстрее, чем собирать образ):

```bash
cd ../backend
export NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=... QDRANT_URL=http://localhost:6333
export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317      # трейсы в Jaeger
python -m sufler.cli --stats && uvicorn sufler.api:app --port 8080
```

`request_id` из ответа — это `trace_id`: `http://localhost:16686/trace/<request_id>` открывает разложение запроса по шагам (ADR-0017).

Офлайн-демо без GPU: `SUFLER_USE_LLM=0` — ответы собираются экстрактивно, retrieval и граф работают полностью.

## Эксплуатационные заметки

- **Теги образов** сейчас плавающие (`latest`) для удобства разработки — **перед сдачей и в контуре пинятся по digest** (воспроизводимость сборки, [урок 18](../../18-iac-ci-cd/18-iac-ci-cd.md)).
- **Телеметрия отключена** у Neo4j и Grafana — требование air-gapped ([ADR-0001](../docs/adr/0001-on-premise-self-hosted-llm.md)).
- **Секреты** не хранятся в compose: обязательные переменные без значения по умолчанию, запуск падает с внятным сообщением, если их нет.
- **Учётки БД** в проде разделяются: индексация пишет, runtime читает ([ADR-0016](../docs/adr/0016-acl-na-uzlah-grafa.md)); в dev-compose это одна учётка — расхождение осознанное.
- **Бэкапы Neo4j:** каталог `./backups/neo4j` смонтирован под `neo4j-admin dump`; граф остаётся производным артефактом и восстановим переиндексацией ([ADR-0012](../docs/adr/0012-graph-db.md)).
- **Ретеншн метрик** 3 суток (`--retentionPeriod=3`) — для демо; в контуре задаётся политикой хранения.

## Что ещё предстоит

- [ ] Профиль `test` с изолированным attacker-LLM для red teaming ([ADR-0018](../docs/adr/0018-security-testing.md))
- [x] Провижининг дашбордов Grafana как кода → [`grafana/`](grafana/) (в прод-контуре это сделано модулем OpenTofu)
- [ ] Алерты с runbook'ами (ADR-0017, правило 3: алертов без runbook не заводим)
- [ ] Экспорт трейсов в Langfuse — LLM-семантика и скоринг качества
- [ ] Пины образов по digest и offline-зеркало для air-gapped
