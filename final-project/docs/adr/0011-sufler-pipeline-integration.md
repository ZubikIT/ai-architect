---
id: ADR-0011
title: Интеграция Суфлёра как Open WebUI Pipeline + RBAC через Keycloak-группы
date: 2026-05-27
version: 0.1
status: proposed
deciders: [Зубик Александр]
tags: [integration, open-webui, pipelines, keycloak, rbac, rag, deployment]
---

# ADR-0011. Интеграция Суфлёра как Open WebUI Pipeline + RBAC через Keycloak-группы

## Контекст
Курсовой проект — архитектурный слой над **реальным деплоем** Open WebUI (`zubriq.by`, публичная копия решения для ЗАО МТБанк). Деплой уже содержит: Open WebUI + контейнер **Pipelines** (`ghcr.io/open-webui/pipelines`, зарегистрирован как OpenAI-compat backend `http://pipelines:9099`), **Keycloak OIDC** с группами (`OAUTH_GROUPS_CLAIM=groups`, group management), подключённый STT, pipeline `speech_analytics_v1.py`, workspace-as-code через OpenTofu (`ncecere/openwebui`).

Нужно решить, **как встроить Суфлёр RAG** (этапы 1-2 MVP) в этот деплой, не ломая его конвенций.

## Рассмотренные варианты
1. **Тонкий Pipe + отдельный RAG-сервис** _(выбран)_
   - Pipe в `pipelines/sufler_rag_v1.py` — тонкий клиент: достаёт вопрос, берёт роли из `body.user` (группы Keycloak), зовёт сервис «Суфлёр» (`POST /ask`), форматирует ответ + цитаты.
   - RAG-логика (Qdrant + эмбеддинг + rerank + LLM) — в отдельном сервисе (наш `final-project/mvp`, контейнер-sidecar).
   - **Хорошо:** контейнер pipelines остаётся лёгким (без torch/qdrant); RAG масштабируется/обновляется независимо; переиспользуем готовый OpenAI-совместимый сервис; один паттерн с `speech_analytics_v1.py`.
   - **Плохо:** ещё один сервис в развёртывании.
2. **Вся логика внутри Pipe**
   - **Плохо:** тянет тяжёлые зависимости (torch, qdrant-client, модели) в контейнер pipelines; раздувает образ; плохо масштабируется.
3. **Встроенный Knowledge-RAG Open WebUI**
   - **Хорошо:** ноль кода.
   - **Плохо:** базовый RAG без hybrid+rerank и без нашей permission-aware логики; не закрывает требования урока 06.

## Решение
**Суфлёр = тонкий Pipe (`sufler_rag_v1.py`) + RAG-сервис.** RBAC: Pipe извлекает **группы пользователя из Keycloak** (`body.user.groups`, иначе `role`, иначе дефолт) и передаёт как `roles` в `/ask` → permission-aware фильтр в Qdrant (№ 99-З).

**Конвенции деплоя соблюсти:**
- Регистрацию модели/пайплайна и **права групп** делать через **OpenTofu-модуль** (`ncecere/openwebui`), не через UI/curl.
- RAG-сервис в air-gapped проде ходит в **self-hosted vLLM+Qwen** и **локальный Qdrant** (ADR-0001..0006) — никаких внешних API.

**Статус `proposed`** — подтвердить на PoC: проброс групп Keycloak в `body.user` пайплайна (возможно, нужен `ENABLE_FORWARD_USER_INFO_HEADERS` / маппинг групп); сетевой доступ pipelines → RAG-сервис.

## Последствия
- **Положительные:**
  - Суфлёр появляется как модель в Open WebUI без форка; RBAC завязан на существующий Keycloak.
  - Лёгкий pipelines-контейнер; RAG обновляется отдельно.
  - Единый паттерн с уже работающим `speech_analytics_v1.py`.
- **Отрицательные / риски:**
  - Зависимость от проброса групп Keycloak в Pipe — если групп нет в `body.user`, RBAC деградирует до OWUI-role (грубее) → проверить на PoC, при необходимости тянуть группы из OWUI API.
  - Доп. сервис в инфраструктуре (sizing, мониторинг).
- **Что придётся изменить дальше:**
  - Завести RAG-сервис в OpenTofu/compose; зарегистрировать модель «Суфлёр» через TF-модуль.
  - Перевести zubriq.by-PoC с облачного LLM (Mistral) на self-hosted (прод-таргет, ADR-0001).

## Compliance & Ethics _(AI-специфичный раздел, урок 08)_
- **RBAC/№ 99-З:** группы Keycloak → permission-aware retrieval; пользователь не получает документы вне прав; аудит доступа.
- **Air-gapped:** RAG-сервис и LLM — в контуре; внешние API запрещены (ADR-0001) — в отличие от текущего публичного PoC на Mistral.
- **Guardrails:** prompt-injection (in) и PII-маска (out) — на стороне RAG-сервиса; в проде усилить через Open WebUI Pipelines.

## Связи
- **Следует из:** [ADR-0007](0007-chat-interface.md) (Open WebUI), [ADR-0009](0009-mcp-integration-layer.md) (интеграции), [mvp.md](../mvp.md) (Суфлёр).
- **Реализация:** `open-webui/pipelines/sufler_rag_v1.py` (Pipe), `final-project/mvp/` (RAG-сервис).
- **Зависит от:** [ADR-0001..0006] (self-hosted прод-таргет), Keycloak/OpenTofu деплоя zubriq.by.
- **Шаблон:** [`../../../templates/adr.md`](../../../templates/adr.md).
