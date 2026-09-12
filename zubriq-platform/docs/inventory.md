# Инвентарь: что где живёт

Снимок на 12.09.2026. Источник — `devops/opentofu/*.tf` (инфраструктура кодом), README репозиториев продуктов и живые ответы сервисов.

> Документ существует ровно потому, что описание архитектуры без адресации отвечает на вопрос «как устроено» и не отвечает на вопрос «куда идти, когда сломалось».

## Гипервизор и кластеры

| Уровень | Что |
|---|---|
| Proxmox VE | узлы `pve1`–`pve4`, кластерный endpoint — `pve2` (`10.110.0.12`) |
| Сеть площадки | `10.100.1.0/24`, шлюз `10.100.1.1` |
| Kubernetes | Talos Linux, кластер `talos`, узлы `10.100.1.80–.90`, LB-пул Cilium `10.100.1.91–.99`, домен приложений `*.talos.acl.by` |
| GPU | LXC 100 «llama» на `pve4`, 4× NVIDIA Tesla V100 SXM2 16 ГБ |

## Инференс и шлюз моделей

| Сервис | Адрес | Где | Примечание |
|---|---|---|---|
| vLLM (текст) | `10.100.1.200:80` | LXC 100 «llama», pve4 | `Qwen3.6-35B-A3B-AWQ`, TP=4, `--max-model-len 65536`, systemd `vllm.service`, веса из MinIO (бакет `models`) |
| vLLM (VL) | `10.100.1.200:8001` | там же | `qwen3-vl-4b`, `vllm-vl.service` |
| llama.cpp (пилот) | `10.100.1.200:8080` | там же | `Qwen3-Coder-Next-80B-A3B`, алиас LiteLLM `zubr-coder`; юнит объявляет `Conflicts=vllm.service` — VRAM эксклюзивна |
| LiteLLM (прод) | кластер Talos, за ingress `10.100.1.91` | ns из `devops/argocd/talos/apps/litellm` | публичные имена `llm.acl.by`, `api.zubriq.by` |
| LiteLLM (откат) | `10.100.1.201:4000` | LXC 101, pve4 | оставлен живым; та же БД Pigsty, состояния нет |

Секреты шлюза: `secret/litellm` (master key), `secret/mistral`, `secret/openrouter`. Каталог моделей и цен — `devops/argocd/talos/apps/litellm` (прод) и `devops/opentofu/prices.tf` (`local.model_prices`) для биллинга.

## Продукты ZubrIQ

| Домен | Сервис | Где |
|---|---|---|
| `zubriq.by` | лендинг + чат | кластер (`apps/zubriq`) |
| `console.zubriq.by` | консоль, Laravel 13 + Filament 5 + FrankenPHP; здесь же API чата | кластер, за NPM → ingress `10.100.1.91:80` |
| `api.zubriq.by`, `llm.acl.by` | OpenAI-совместимый эндпоинт LiteLLM | кластер |
| `docs.zubriq.by` | документация | кластер |
| `drive.zubriq.by` | Nextcloud/OpenCloud + Collabora | ВМ 261, `10.100.1.63` |
| `academy.zubriq.by` | LMS Академии | ВМ 257, `10.100.1.77` |
| `builder.zubriq.by` | Dify — конструктор ассистентов | ВМ 246, `10.100.1.55` |
| `mcp.zubriq.by`, `inspector.zubriq.by` | MCP-шлюз ContextForge | ВМ 248, `10.100.1.58` (`cpu_type x86-64-v3`) |
| `code.zubriq.by`, `get.zubriq.by` | `zq` — форк Qwen Code, дистрибуция | кластер (`apps/zubriq-code`) |
| `code-app.zubriq.by` | code-app | ВМ 205, `10.100.1.42` — в кластер не переезжал |
| `stats.zubriq.by` | Matomo | ВМ 256, `10.100.1.56` |
| `status.zubriq.by` | Uptime Kuma | `10.100.1.16` |
| `langfuse.zubriq.by` | трассировка LLM (web/worker/redis/clickhouse) | ВМ 205, `10.100.1.42` |
| `id.zubriq.by` | Keycloak | ВМ 219, `10.100.1.19` |
| `owui.acl.by` | Open WebUI — **legacy, заморожен** | кластер, ns `openwebui` |
| `embeddings.zubriq.by` | сервис эмбеддингов | — |

## Платформенные сервисы

| Сервис | Адрес | Назначение |
|---|---|---|
| Nginx Proxy Manager | `10.100.1.12` | периметр, TLS, маршрутизация по именам |
| Keycloak | `10.100.1.19` (ВМ 219) | SSO, realm `zubriq` |
| FreeIPA | `10.100.1.15` | каталог, федерация в Keycloak |
| Pigsty PostgreSQL | ВМ `10.100.1.72–.74`, RW-VIP **`10.100.1.75`** | HA-кластер: БД LiteLLM, консоли, Grafana, Coder |
| Vault | кластер `10.100.1.52–.54` (raft HA, auto-unseal через transit) | секреты |
| MinIO | `10.100.1.21–.24` | S3: веса моделей, артефакты, файлы |
| **pgvector** | в Pigsty, таблица `kb_chunks` | **продуктовый retrieval чата** (bge-m3 → bge-reranker-v2-m3, hybrid + FTS + RRF) |
| Qdrant | `10.100.1.46:6333` | Суфлёр и Shield-сканер; из продуктового пути выведен 01.08.2026 |
| Redis | `10.100.1.11` | кэш, очереди |
| GitLab | `10.100.1.20` (`git.artcloud.by`) | репозитории, CI |
| GitLab Runner | `10.100.1.41` | сборки |
| Nexus | `10.100.1.43` | кэш артефактов npm/Go/Docker |
| Grafana / Portainer | `10.100.1.16` | метрики и дашборды |
| GlitchTip | `10.100.1.29` | ошибки приложений |
| Wazuh | `10.100.1.25` | SIEM |
| n8n | `10.100.1.59` | внутренняя автоматизация |
| Песочница кода | ВМ 259, `10.100.1.61` | исполнение Python агентом чата |

## ВМ 205 (`10.100.1.42`) — самая нагруженная ролями

Бывшая `open-webui`, переименована в `zubriq-stage` 28.08.2026, потому что по имени ВМ читают, что на ней живёт. Сейчас на ней одновременно:

- **стейдж ZubrIQ** — `/opt/zubriq-stage`: console `:8093`, chat `:8096`, site `:8095` со своей БД; сюда катится `main` перед прод-тегом;
- **`mcpo` (`:8787`) и `jupyter` (`:8888`)** — от них зависит **кластерный** Open WebUI: он ходит на них по прежним именам через Service без селектора с EndpointSlice на `10.100.1.42`; у моделей в БД записаны `tool_ids` вида `http://mcpo:8000/...`, поэтому сервисы нельзя переименовывать — только держать живыми;
- **Langfuse** — web/worker/redis/clickhouse;
- **`zubriq-code-app`** — `code-app.zubriq.by`;
- **`k8s-mcp`, `mcp-inspector`, `mcp-grafana`**.

**ВМ не одноразовая, гасить нельзя.** Контейнеры уехавшего чата (`open-webui`, `pipelines`, `cf-images-shim`) остановлены и лишены restart-policy: одного `profiles: [legacy]` мало — он держит только `compose up -d`, а контейнер с `restart=always` демон поднимает сам. 28.08.2026 после ребута так заработали **две копии чата на одну БД**.

## Суфлёр

ВМ 237; векторная база — общий Qdrant `10.100.1.46:6333`, коллекция `lpa`; ключ API в Vault `secret/qdrant/api`.

⚠️ Ключ Qdrant **один на инстанс** и даёт доступ в том числе к коллекциям Shield-сканера (`secret/shield/qdrant` — отдельный путь в Vault, но тот же ключ). Разделение сегодня только по соглашению об именах коллекций; изоляция потребует включения JWT RBAC в Qdrant и scope-токенов.

## Пути Vault

| Путь | Что |
|---|---|
| `secret/litellm` | master key шлюза |
| `secret/openrouter`, `secret/mistral` | ключи внешних провайдеров |
| `secret/zubriq-console` | пароль роли `zubriq_console` в Pigsty, `app_key` Laravel |
| `secret/zubriq-chat/twa-keystore` | ключ подписи мобильного приложения чата |
| `secret/openwebui` | админ-токен API OWUI (создаётся вручную в UI) |
| `secret/qdrant/api`, `secret/shield/qdrant` | доступ к векторной базе |
| `secret/dify`, `secret/minio`, `secret/shield/agent-api-token` | прочее |
| `cloudflare_craftsman → npm_dns_challenge_token` | account-wide токен CF для DNS-01 |

## Что в инвентаре не проверено

- **Бэкапы**: PBS присутствует (`1000-vs-backup-01.tf`, `backup_jobs.tf`, `backup_retention_pbs.tf`), но охват и восстановимость не проверял.
- **Сетевая сегментация** между `10.100.1.0/24` и кластером — правила на Mikrotik (`devops/microtik`) не разбирал.
- **Порядок подъёма площадки** после полного обесточивания — нигде не описан.
