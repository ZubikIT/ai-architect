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

Профиль `core` поднят и проверен: граф строится в живой Neo4j, вектор ложится в Qdrant (19 точек, dim 384), набор тестов проходит против стека целиком. Прогон вскрыл три расхождения боевого бэкенда с демо-режимом — разобраны в [`../backend/README.md`](../backend/README.md#живой-прогон-что-нашёл-боевой-бэкенд).

Запуск сервиса из исходников против поднятых БД (быстрее, чем собирать образ):

```bash
cd ../backend
export NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=... QDRANT_URL=http://localhost:6333
python -m sufler.cli --stats && uvicorn sufler.api:app --port 8080
```

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
- [ ] Провижининг дашбордов Grafana как кода (в прод-контуре это уже сделано модулем OpenTofu)
- [ ] Пины образов по digest и offline-зеркало для air-gapped
