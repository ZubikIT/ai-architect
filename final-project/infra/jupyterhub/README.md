# JupyterHub on Proxmox — драфт для курса

> **Статус:** черновик на ревью, не применённый. После твоего OK файлы переезжают:
>
> | Файл черновика | Куда копировать | Что делает |
> |---|---|---|
> | `opentofu/239-jupyterhub.tf` | `artcloud/devops/opentofu/239-jupyterhub.tf` | ВМ 239 на Proxmox, IP `10.100.1.47/24` *(требует сверки!)* |
> | `cloud-init/239-jupyterhub.yaml` | `artcloud/devops/opentofu/cloud-init/239-jupyterhub.yaml` | bootstrap: Docker + клон compose-репо + `.env` |
> | `compose/*` | новый репо `artcloud/devops/jupyterhub` | JupyterHub-сервис: hub + DockerSpawner + Keycloak OAuth |

Паттерн **полностью повторяет** `238-qdrant.tf` (та же модель `modules/vms`, тот же IP-блок `10.100.1.0/24`, тот же `local.common`, тот же cloud-init с qemu-guest-agent / node_exporter / portainer-agent / клоном compose-репо).

## Назначение

1. **Course-infra** — преподаватель / коллеги логинятся своей Keycloak-учёткой → стартуется их персональный singleuser-контейнер на базе `jupyter/minimal-notebook` с предустановленными `langgraph` + `langchain` → могут открыть и **запустить** ДЗ-07 (и любые будущие ноутбуки курса).
2. **Демо-точка финального проекта** — пример живой реализации паттернов курса: SSO через Keycloak, изоляция через DockerSpawner, secrets через Vault, всё на on-prem Proxmox (та же логика, что у самого финального проекта; но эта ВМ **не** часть air-gapped-периметра — она для course-материалов и публичной демонстрации).

## Архитектурные решения

- **Аутентификация — Keycloak (219), а не PAM/LDAP.** Уже есть SSO для других сервисов (Open WebUI и пр.); нет смысла плодить ещё одну витрину паролей. Whitelist по email — критично, иначе любой Keycloak-юзер сможет логиниться (а Keycloak обслуживает несколько realm'ов).
- **Spawner — `DockerSpawner`, а не `SimpleLocalProcessSpawner`.** Каждая сессия — отдельный контейнер на хосте; пользовательский Python-код **не имеет** доступа к хост-FS вне volume'а. Это и есть «security by design» из урока 14 в миниатюре.
- **Singleuser-образ свой, не публичный.** Пинним версии `langgraph`/`langchain-core` (важно: 0.6 ломает 0.5-API), плюс склонирован read-only архитекторский репо с ДЗ. Так преподаватель не ловит unrelated breakage.
- **Ресурсы пер-юзер ограничены** (`Spawner.mem_limit = 2G`, `cpu_limit = 1.0`) — иначе один спавн может уронить хаб.
- **`configproxy_auth_token` через Vault**, как и client_secret Keycloak — никаких секретов в репо.
- **TLS — внешний reverse-proxy** (предположительно Traefik кластера; если его нет — добавляется `caddy` в тот же compose как side-car).

## Что нужно подготовить **перед** `tofu plan`

| Действие | Где | Зачем |
|---|---|---|
| Проверить, что `vm_id=239` и `10.100.1.47/24` свободны | Proxmox guest-agent | избежать коллизий с действующими ВМ |
| Создать репо `artcloud/devops/jupyterhub` | GitLab | cloud-init клонит compose оттуда (как qdrant из `devops/qdrant`) |
| Скопировать `compose/*` в этот репо | git | hub поднимается из этих файлов |
| В Keycloak realm `artcloud` создать client `jupyterhub` | Keycloak admin | `client_id`, `client_secret`, redirect URI `https://jupyterhub.<домен>/hub/oauth_callback` |
| Положить в Vault `secret/jupyterhub/keycloak-oauth` поля `client_id`, `client_secret`, `realm_base_url`, `whitelist` (CSV emails) | `vault kv put` | `.tf` тянет через `data "vault_kv_secret_v2"` |
| Добавить DNS-запись `jupyterhub.<домен>` → `10.100.1.47` | внутренний DNS / Pi-hole (203) | для Keycloak callback URL |
| Reverse-proxy для TLS | внешний (Traefik) или сайдкар в compose | OAuth требует HTTPS |

## Файлы черновика

- [`opentofu/239-jupyterhub.tf`](./opentofu/239-jupyterhub.tf) — описание ВМ.
- [`cloud-init/239-jupyterhub.yaml`](./cloud-init/239-jupyterhub.yaml) — bootstrap.
- [`compose/docker-compose.yml`](./compose/docker-compose.yml) — JupyterHub + DockerSpawner.
- [`compose/jupyterhub_config.py`](./compose/jupyterhub_config.py) — Hub config с OAuth + whitelist.
- [`compose/Dockerfile.singleuser`](./compose/Dockerfile.singleuser) — образ пользовательского окружения.

## Стоимость / ресурсы

- 1 ВМ: 2 vCPU / 4 ГБ RAM / 30 ГБ диск — для 1-5 одновременных юзеров.
- Singleuser-контейнеры: каждый ещё до 2 ГБ RAM / 1 vCPU (`Spawner.mem_limit`).
- При росте — масштабируется по памяти (на CPU singleuser-нагрузка нулевая когда юзер ничего не делает).
