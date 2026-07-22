---
module: 04-infrastructure
lesson: 20
date: 2026-07-10
lecturer: Николай Степанов
tags: [deployment, blue-green, canary, rolling, shadow, ab-testing, ml-cicd, feature-flags, model-routing, release-plan, rollback, readiness-checklist, sync-async-batch]
status: done
has_homework: true
---

# 20. Стратегии развёртывания и вывода в Production

> **Занятие** · 10 июля (пт), 20:00 · 90 мин · преподаватель **Николай Степанов**, Data Science Lead в Emerging Travel Group (`@nikolaistepanov`; в расписании ЛК значился Денис Лавров — по слайдам вёл Степанов). Блок 4 «Инфраструктура».
>
> **Цели (из ЛК):** выбирать и применять стратегии развёртывания (Blue-Green, Canary) для минимизации рисков при обновлении моделей; планировать вывод моделей в промышленную эксплуатацию с учётом A/B-тестирования и постепенного масштабирования.
> **Краткое содержание:** стратегии (Blue-Green, Canary, Rolling); планирование релиза; чек-лист готовности; план отката; практика — план релиза нового AI-сервиса по Canary-стратегии.
> **Компетенция:** разрабатывать планы релиза для AI-сервисов с использованием стратегии Canary.
> **Результаты:** конспект; **ДЗ-20 «Автоматизация поставки: IaC, CI/CD и MLOps-конвейеры»** — капстоун блока по урокам 18+19+20, **сдано 15.07.2026** (дедлайн 30.07.2026), ждём проверки → [`Zubik_DZ-20`](Zubik_DZ-20_delivery-pipeline.md).
>
> Артефакты: [слайды лекции](artifacts/lesson-20-deployment-strategies.pdf) (53 стр., появились в ЛК 22.07) — тезисы ниже по ним.
>
> Связь: третий элемент связки 18 → 19 → 20: урок 18 дал конвейер с гейтами, урок 19 — петлю drift→retrain и Blue-Green/Canary как шаг пайплайна переобучения ([[mlops-pipelines-genai]]), урок 20 раскрывает сам релиз: выбор стратегии, план, чек-лист готовности, план отката.

## TL;DR

ML CI/CD — это управление **тремя артефактами вместо одного**: код + данные + модель, у каждого свой контур версионирования, тестов и мониторинга. Стратегии релиза различаются по сигналу/риску/стоимости: **Rolling** и **Blue-Green** — механика замены инстансов, **Canary** — доля трафика с метриками-гейтами, **Shadow** — дублирование запросов без риска для пользователей. Центральный тезис лекции: **Deploy ≠ Release** — код уже в проде, а включение поведения управляется feature-флагами; безопасный стандарт для моделей — воронка **shadow (техника) → canary (контролируемый риск) → A/B (доказательство эффекта) → promote/rollback**. Решение о выкатке опирается на три группы сигналов: SLO (latency/errors), бизнес-KPI и ML-метрики. Паттерн деплоя инференса (sync / async / batch) выбирается требованиями бизнеса (задержка, критичность для UX, нагрузка, свежесть), а не типом модели.

## Контекст и проблема

Уроки 18–19 построили конвейер до ворот прода; урок 20 — про сами ворота. Особенность AI-сервисов: регрессия часто не видна в тестах (качество ответов субъективно, деградация статистическая), поэтому окончательная валидация происходит **на живом трафике** — а значит, стратегия выкатки и метрики отката являются частью системы качества, а не просто эксплуатационной гигиеной.

## Ключевые тезисы

### ML CI/CD: код + данные + модель

- В классическом CI/CD главный артефакт — код; в ML к нему добавляются **данные** и **модель**, каждый со своим контуром:
  - **Данные:** versioning & lineage (snapshots/hashes, raw → features → train/val/test; DVC, lakeFS, Delta/Iceberg/Hudi, MLflow metadata), data quality & contracts (schema + constraints, producer ↔ consumer; Great Expectations, Pandera, dbt tests, Soda), drift & monitoring (training-serving skew, data/concept drift; Evidently, WhyLabs, Arize + Prometheus/Grafana).
  - **Модель:** воспроизводимое окружение (pinned deps + lockfiles, контейнеры как артефакты, hermetic builds), тесты — software (unit + integration) **плюс** model quality gates (пороги метрик + регрессия vs baseline) **плюс** slicing & risk gates (сегменты, fairness, robustness, калибровка).
- Качество в ML — это **gates, а не pass/fail**: тест модели — статистический порог, а не бинарный assert. Основа всего — воспроизводимость и трассируемость.

### Стратегии релиза

- **Blue/Green** — два окружения, переключение трафика «рубильником», мгновенный rollback; **Rolling** — постепенная замена инстансов в одном окружении, откат медленнее. Подходят сервисам с предсказуемым поведением.
- **Canary** — X% трафика на новую версию, доля растёт по шагам; гейты — SLO (latency/errors) + KPI + ML-метрики; rollback = 0% на canary за минуты. Механика — ingress/service mesh: nginx-ingress аннотация `canary-weight: "5"` или Istio VirtualService с `weight: 95/5`.
- **Shadow / dark launch** — запросы дублируются на новую версию, но пользователю отвечает стабильная: проверяем ошибки, latency, совместимость, распределение предсказаний при **нулевом риске**; ограничение — не измеряет бизнес-эффект.
- **Model routing поверх стратегий:** A/B-тест (сравнение по KPI), Champion/Challenger (stable vs candidate в registry + промоут), online learning / bandits (динамическое перераспределение трафика). Полная воронка: **Shadow → Canary → A/B → Promote**.

### Feature flags: Deploy ≠ Release

- Флаг отделяет deploy (код выложен) от release (поведение включено): progressive rollout 1% → 5% → 25% → 100%, сегментация (geo/tenant/cohort/internal), kill switch при деградации SLO/KPI, основа для A/B-групп.
- Реализация от простого к управляемому: детерминированный бакетинг `hash(user_id) % 100` с fail-safe fallback на стабильную модель при таймауте → Unleash с контекстом (userId для percentage rollout, properties для сегментации по tenant/country).

### Архитектуры DS-сервисов: sync / async / batch

- Три паттерна деплоя инференса; выбор — **по требованиям, а не по типу модели**: задержка (ms / sec–min / hours), критичность для UX (блокирует или нет), нагрузка и стоимость (QPS, пики, GPU/CPU), свежесть результата, надёжность (retries, backpressure, деградация), где живут фичи (online store/cache vs DWH snapshot).
- Кейсы с разбора: ночной пересчёт риск-скоров страховых полисов → **batch**; draft reply оператору в support-чате по истории диалога и базе знаний → **sync** (LLM+RAG); аномалии в IoT-телеметрии с остановкой линии → **async/streaming**.

## Диаграммы

Схемы сравнения стратегий (canary/shadow/rollout/blue-green), model routing и трёх архитектур (sync/async/batch) — в [слайдах](artifacts/lesson-20-deployment-strategies.pdf).

## Вопросы и ответы

1. A/B-тест vs Canary: где граница — валидация надёжности (canary) против валидации продуктовой гипотезы (A/B)? Для LLM-модели новая версия — это почти всегда ещё и продуктовое изменение.
2. Sticky-sessions для чат-бота при canary: пользователь посреди диалога не должен прыгать между версиями модели — session affinity по user_id?

## Что почитать / посмотреть
- [ ] Запись вебинара в ЛК
- [x] [Слайды лекции](artifacts/lesson-20-deployment-strategies.pdf)
- [ ] [Canary Release (martinfowler.com)](https://martinfowler.com/bliki/CanaryRelease.html) — из вспомогательных материалов ДЗ
- [ ] [Argo Rollouts](https://argoproj.github.io/rollouts/) — canary/blue-green как CRD в K8s
- [ ] [Argo CD · Architectural Overview](https://argo-cd.readthedocs.io/en/stable/operator-manual/architecture/) — GitOps-слой под Rollouts: API server / repo server / application controller, git как источник истины (то, чем «git revert values.yaml» из плана отката ДЗ-20 становится фактическим откатом)
- [ ] Из списка материалов лектора: статья «Continuous Training», [Unleash docs](https://docs.getunleash.io/), [Istio · Canary Deployments](https://istio.io/latest/blog/2017/0.1-canary/), MLflow Model Registry workflows

## Мои выводы

1. **ДЗ-20 — капстоун блока 18–20** и по сути черновик релизного контура финального проекта: IaC + CI/CD + MLOps-петля + Canary-план в одном документе → [`Zubik_DZ-20`](Zubik_DZ-20_delivery-pipeline.md).
2. Для on-prem финала ([[final-project-hardware]]) canary на уровне GPU-реплик дорог (карт мало) — реалистичный вариант: canary по трафику между двумя vLLM-инстансами на одной паре карт (MIG/вторая карта) либо shadow-режим для новой модели до переключения. Слайды это подтверждают: shadow — первый шаг стандартной воронки (нулевой риск, не требует раздачи живого трафика), т.е. для дефицита GPU это не компромисс, а канонический старт.
3. Feature-флаги как слой model routing — недостающее звено моего плана отката в ДЗ-20: kill switch на уровне флага (секунды) быстрее, чем `git revert` + sync через Argo CD (минуты), и они не заменяют, а дополняют друг друга.
