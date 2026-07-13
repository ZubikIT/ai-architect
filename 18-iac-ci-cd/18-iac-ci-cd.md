---
module: 04-infrastructure
lesson: 18
date: 2026-07-03
lecturer: Илья Ящук
tags: [IaC, terraform, opentofu, provider, state, plan-apply, ci-cd, quality-gates, gitlab-ci, vpc, kubernetes, s3, container-registry, yandex-cloud]
status: done
has_homework: true
---

# 18. Инфраструктура как код (IaC) и CI/CD

> **Занятие** · 3 июля (пт), 20:00 · 90 мин · преподаватель **Илья Ящук**, Data Scientist (5 лет в Reliability Engineering / Condition Monitoring, к.т.н. по предиктивной аналитике, MLOps в **RenMoney** (FinTech); `@ilia_iashchuk`) — тот же лектор, что и на уроке 13 ([[eval-test-plan-genai]]), его репо `Ilia2704/llm-app` снова в материалах. Блок 4 «Инфраструктура».
>
> **Цели (из ЛК):** автоматизировать развёртывание и управление инфраструктурой инструментами IaC (Terraform); проектировать CI/CD-пайплайны для сборки, тестирования и доставки AI-приложений.
> **Маршрут (со слайда):** Знакомство → IaC → CI/CD → Практика → Заключение.
> **Компетенция:** писать Terraform-конфигурации для базовой инфраструктуры (VPC, Kubernetes-кластер, S3).
> **Результаты:** практическое задание (ДЗ-18: Terraform-конфигурация VPC + K8s + S3 — детали в ЛК), конспект, шаблон настройки.
>
> Артефакты: [слайды лекции](artifacts/lesson-18-iac-cicd.pdf) (31 стр.) · практика: [снапшот otus-mlops-terraform-nov](artifacts/otus-mlops-terraform-nov/PROVENANCE.md) (live-деплой VM + VPC + SA + S3 в Yandex Cloud) · [llm-app — общий снапшот в уроке 13](../13-ocenka-kachestva-genai/artifacts/llm-app/PROVENANCE.md) (приложение-объект CI/CD; обновлён до актуального коммита `3c6d4bc`: пакеты `testing/`, `rag/`, `agent/`).
>
> Связь: инженерное продолжение блока — уроки 13–15 дали *содержание* гейтов (eval-метрики, security-сканы, observability), урок 18 даёт *конвейер*, который эти гейты исполняет. Для нас ([[prefer-iac-over-ui]], [[zubriq-openwebui-deployment]]) это скорее валидация уже принятой практики: весь zubriq.by ведётся как OpenTofu workspace-as-code, а [[yandex-yc-opentofu]] — живой пример provider/state/plan/apply из лекции.

## TL;DR

**IaC = инфраструктура описана декларативными файлами и живёт в Git.** Проблема без IaC: инфраструктура создаётся вручную (невоспроизводимо), нет версионирования (непонятно, что и когда изменилось), а для AI это критично — **эксперимент должен быть воспроизводим вместе с инфраструктурой**. Что даёт IaC: инфраструктура в Git с ревью и историей; один конфиг разворачивает окружение dev/staging/prod; откат так же прост, как git revert.

**Terraform** (HashiCorp, Go, декларативный HCL) — стандарт де-факто. Три ключевые концепции: **Provider** — драйвер к облаку (для YC: `yandex-cloud/yandex`), **Resource** — любой объект инфраструктуры (сеть, кластер, бакет), **State** — файл, в котором Terraform хранит, что уже создано и чем он управляет. Цикл: `init` (скачать провайдер) → `plan` (показать, что изменится) → `apply` (применить) → `destroy` (удалить всё). Схема работы: Terraform ↔ Provider ↔ Target API облака.

**Типовой AI-стек в конфигах:** VPC + подсети (изоляция окружений), Managed Kubernetes (контейнеры inference/training/preprocessing), Object Storage (датасеты, чекпоинты, артефакты моделей), Container Registry (версионирование образов), Managed PostgreSQL (метаданные экспериментов, feature store), IAM + сервисные аккаунты (разграничение прав).

**CI/CD для AI ≠ CI/CD для классического ПО.** Главная сложность: **модель может сломаться не из-за бага в коде, а из-за изменения данных или гиперпараметров**. Отличия по этапам: артефакт — не просто Docker-образ, а образ + веса модели + конфиг; тестирование — unit/integration **плюс качество модели по метрикам**; откат — предыдущий образ **плюс предыдущая версия модели**; триггер — не только push, но и **новые данные / дрейф модели**. Пайплайн (GitLab): START (push) → BUILD (образ → CR) → TEST (unit + интеграционные API) → SECURITY (SAST, скан контейнеров) → VALIDATE (веса из S3, прогон на validation dataset, проверка метрик) → DEPLOY (Helm-чарт в k8s) → MONITORING (реальный запрос к inference, проверка ответа и latency).

**Quality gates — автоматические стоп-краны пайплайна:** линтеры кода (ruff/black/isort — любая ошибка), линтеры IaC (`terraform validate`, tflint, helm lint — любая ошибка), unit-тесты (pytest — coverage ниже порога), безопасность (semgrep, trivy — критические уязвимости и секреты), качество модели (custom script — метрика ниже порога), smoke-тесты (curl — статусы и latency).

## Контекст и проблема

Уроки 16–17 отвечали «сколько железа и как его выжать», урок 18 — «как это железо и всё над ним *воспроизводимо* создавать и обновлять». Для AI-систем ручная инфраструктура ломает главное — воспроизводимость эксперимента: код версионируется, а окружение, в котором он давал метрику, — нет. Вторая половина — доставка: у AI-приложения три независимых источника поломки (код, данные, модель), значит пайплайн обязан проверять все три, а не только код. Ответ лекции: Terraform для инфраструктуры + CI/CD с quality gates, где среди гейтов появляется специфичный для ML «качество модели ниже порога — стоп».

## Ключевые тезисы

- **State — центральная и самая недооценённая концепция Terraform:** это единственный источник знания «чем управляет tf»; ручные правки в облаке мимо state (= мимо Git) создают дрейф, который `plan` покажет как «лишние» изменения. Отсюда практическое правило [[prefer-iac-over-ui]]: UI/curl — только как временный обход с черновиком `.tf`.
- **`plan` перед `apply` — это code review для инфраструктуры:** diff того, что изменится, до того как оно изменилось. В CI шаг `terraform plan` в MR — обязательный quality gate (tf validate/tflint из таблицы гейтов).
- **Один конфиг — три окружения (dev/staging/prod):** параметризация через `variables.tf` + `terraform.tfvars`; секреты и персональные ID — только в tfvars/окружении, не в коде (в практике лектора: `terraform.tfvars.example` в репо, реальный tfvars в .gitignore).
- **Артефакт AI-релиза трёхчастный (образ + веса + конфиг)** → и откат трёхчастный: вернуть образ без отката весов — не откат. Реестр моделей/весов (S3-версии) так же обязателен, как Container Registry для образов.
- **Триггер пайплайна для AI — не только push:** новые данные и дрейф модели (алерты урока 15, [[observability-genai]]) легитимно запускают re-validate/re-deploy без изменения кода.
- **VALIDATE-этап — это урок 13, встроенный в конвейер:** прогон на validation dataset и порог по метрике = eval-гейты ([[eval-test-plan-genai]]) как код; SECURITY-этап (semgrep, trivy) — чек-лист урока 14 ([[security-by-design-genai]]) как код.
- **Практика на YC минимальна, но полна:** disk + compute instance (nat, ssh-keys через metadata) + `yandex_vpc_network`/`subnet` + SA с ролью `storage.admin` + static access key + `yandex_storage_bucket` — весь словарь provider/resource/state/variables на одном экране `main.tf`.

## Диаграммы / таблицы

**Цикл Terraform:**

```
terraform init      # скачать провайдер
terraform plan      # показать, что изменится
terraform apply     # применить изменения
terraform destroy   # удалить всё
```

**Типичная AI-инфраструктура в конфигах (слайд):**

| Компонент | Зачем в AI-системе |
|---|---|
| VPC + подсети | изоляция окружений, безопасность, зоны доступности |
| Managed Kubernetes | запуск контейнеров: inference, training, preprocessing |
| Object Storage | хранение датасетов, чекпоинтов, артефактов моделей |
| Container Registry | версионирование Docker-образов сервисов |
| Managed PostgreSQL | метаданные экспериментов, feature store |
| IAM + сервисные аккаунты | разграничение прав между компонентами |

**Отличие CI/CD для AI от классического software (слайд):**

| Этап | Software | AI |
|---|---|---|
| Артефакт | Docker-образ | образ + веса модели + конфиг |
| Тестирование | unit / integration | unit / integration + качество модели, метрики |
| Откат | предыдущий образ | предыдущий образ + предыдущая версия модели |
| Триггер | push в репозиторий | push + новые данные, дрейф модели |

**Пайплайн CI/CD в GitLab (слайд):**

| Этап | Содержание |
|---|---|
| START | push в GitLab — старт пайплайна |
| BUILD | сборка образа; push образа в Container Registry |
| TEST | unit-тесты; интеграционные тесты API |
| SECURITY | SAST, проверка контейнеров |
| VALIDATE | загрузка весов из S3; прогон на validation dataset; проверка метрик |
| DEPLOY | обновление Helm-чарта в k8s |
| MONITORING | реальный запрос к inference; проверка ответа и времени отклика |

**Quality gates (слайд):**

| Gate | Инструменты | Критерий остановки |
|---|---|---|
| Линтеры | ruff, black, isort | любая ошибка |
| Линтеры Terraform, k8s | tf validate, tflint, helm lint | любая ошибка |
| Unit-тесты | pytest | coverage < порога % |
| Безопасность | semgrep, trivy | критические уязвимости, секреты |
| Качество модели | custom script | метрика < порога |
| Smoke-тесты | curl | статусы, latency |

## Вопросы и ответы

_(в слайдах Q&A-блока нет; мои вопросы к практике)_
1. Где хранить remote state для команды (S3 backend + lock) — в практике лектора state локальный; для прода это первый же шаг после «hello world».
2. Terraform vs OpenTofu после смены лицензии HashiCorp (BUSL): для нового проекта в 2026 — почему бы сразу не OpenTofu (как у нас)?
3. Кто выпускает и ротирует OAuth-токен YC для CI-раннера — в практике токен в tfvars, в проде нужен SA + короткоживущие IAM-токены (наш паттерн [[yandex-yc-opentofu]]).

## Что почитать / посмотреть
- [ ] [NickOsipov/otus-mlops-terraform-nov](https://github.com/NickOsipov/otus-mlops-terraform-nov) — практика лекции: VM + VPC + SA + bucket в YC, variables/tfvars
- [ ] [Ilia2704/llm-app](https://github.com/Ilia2704/llm-app) — приложение-объект пайплайна (RAGAS+MLflow из урока 13)
- [ ] [Terraform docs — yandex provider](https://terraform-provider.yandexcloud.net/) — справочник ресурсов `yandex_*`
- [ ] [OpenTofu](https://opentofu.org/) — open-source форк Terraform (наш рабочий инструмент)
- [ ] Книга: Y. Brikman, «Terraform: Up & Running» — state, модули, тестирование IaC

## Мои выводы

1. **Лекция валидирует нашу практику, а не открывает новую:** zubriq.by ([[zubriq-openwebui-deployment]]) уже ведётся как OpenTofu workspace-as-code, module.yc ([[yandex-yc-opentofu]]) — ровно provider/resource/state из слайдов, причём с решённой «взрослой» проблемой (SA `tofu-admin` + Vault вместо OAuth-токена в tfvars). В конспект финала это идёт как готовый ответ на компетенцию урока.
2. **Мой пробел — не IaC, а CI/CD-гейты поверх него:** `tofu plan` я запускаю руками; следующий шаг — GitLab/GitHub-пайплайн с гейтами tflint → plan-в-MR → apply-по-approve. Для финального проекта достаточно описать это в ADR + один рабочий workflow.
3. **VALIDATE-этап — мостик к моему RAGAS-скорингу:** `/ask` финального MVP уже возвращает contexts для RAGAS — оформить прогон как job с порогом (faithfulness < 0.8 → стоп) и получится «качество модели» quality gate из таблицы, собранный из уроков 13+18.
4. **Трёхчастный артефакт (образ + веса + конфиг) для on-prem финала** ([[final-project-hardware]]): у нас веса моделей vLLM — это тоже артефакт с версией и откатом, а не «то, что лежит на диске сервера»; минимум — зафиксировать реестр моделей (S3/MinIO + манифест версий) в ADR-пакете.
