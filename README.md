# OTUS AI Architect — материалы курса

Репозиторий с конспектами, домашними заданиями, архитектурными артефактами и финальным проектом по курсу [AI Architect](https://otus.ru/lessons/ai-architect/) от OTUS.

## Структура

Каждый урок — **отдельная папка в корне** с префиксом-номером занятия (`NN-...`), внутри неё всё, что касается урока:

- конспект вебинара `NN-...md` (главный файл папки);
- домашнее задание (рядом с конспектом: `*.md` / `*.ipynb` / `Zubik_DZ-NN_*.pdf`);
- `artifacts/` — диаграммы, схемы, PDF-слайды, код-демо, рабочие файлы.

Уроки идут сквозной нумерацией `00`…`31`; группировка по тематическим блокам сохранена в разделе [Программа](#программа-по-мере-открытия-в-лк) ниже.

Не-урочные папки в корне:

| Папка | Назначение |
|---|---|
| [`final-project/`](./final-project/) | Финальный проект — пакет архитектурных документов (ADR, HLD, MVP) и экономическое обоснование |
| [`templates/`](./templates/) | Шаблоны: конспект вебинара, ДЗ, ADR, HLD, LLD |
| [`resources/`](./resources/) | Общие материалы — ссылки, книги, статьи, словарь терминов |

## Как пользоваться

1. На каждый вебинар — папка `NN-slug/` в корне; конспект из шаблона `templates/webinar-notes.md` кладётся как `NN-slug/NN-slug.md`.
2. ДЗ (`templates/homework.md`) — в ту же папку урока рядом с конспектом.
3. Архитектурные решения оформляются как ADR (`templates/adr.md`) — в `artifacts/` урока или в `final-project/docs/`.
4. Большие бинарники (видео, объёмные pdf, xlsx) **в репозиторий не коммитим** — храним в S3/облаке/локально, в репо — только ссылки.

## Соглашения по именованию

- Папки уроков и файлы: `kebab-case`, с префиксом-номером: `11-integratsii-klassika-ai/`.
- Диаграммы Mermaid — прямо в md-файлах. Сложные C4-диаграммы — в `NN-.../artifacts/` (`.dsl`, `.png` рядом).
- Даты в формате `YYYY-MM-DD`.

## Программа (по мере открытия в ЛК)

### Орг. задачи
- [ ] [Заполнить раздел «О себе»](./00-o-sebe/00-o-sebe.md) в ЛК OTUS

### Блок 1. Стратегический фундамент
- [ ] [01. Пресейл, контракты и работа с требованиями](./01-presale-i-trebovaniya/01-presale-i-trebovaniya.md)
- [ ] [02. Проектирование и оценка: план, риски, смета](./02-proektirovanie-i-ocenka/02-proektirovanie-i-ocenka.md)
- [ ] [03. Стратегия поставки ценности: от PoC до Production](./03-strategiya-postavki-cennosti/03-strategiya-postavki-cennosti.md) — **ДЗ:** [`Zubik_DZ-03`](./03-strategiya-postavki-cennosti/Zubik_DZ-03_strategiya-postavki.md) (задание + решение + PDF)

### Блок 2. Проектирование архитектуры
- [ ] [04. HLD с использованием C4 Model](./04-hld-c4-model/04-hld-c4-model.md)
- [ ] [05. LLD: компоненты и взаимодействия](./05-lld-komponenty/05-lld-komponenty.md) — **ДЗ:** [`Zubik_DZ-05`](./05-lld-komponenty/Zubik_DZ-05_lld-c4-api.md) (задание + решение)
- [ ] [06. RAG и его продвинутые вариации](./06-rag-i-prodvinutye-variacii/06-rag-i-prodvinutye-variacii.md)
- [ ] [07. AI-агенты и Multi-Agent Systems](./07-ai-agents-i-multi-agent-systems/07-ai-agents-i-multi-agent-systems.md) — **ДЗ:** [`Zubik_DZ-07`](./07-ai-agents-i-multi-agent-systems/Zubik_DZ-07_tripbuddy.md) (задание + решение + ipynb + PDF)
- [ ] [08. Документирование решений: ADR](./08-adr-documentation/08-adr-documentation.md)
- [ ] [09. Верификация архитектуры и «CTO Challenge»](./09-verifikaciya-cto-challenge/09-verifikaciya-cto-challenge.md) — **ДЗ:** [`Zubik_DZ-09`](./09-verifikaciya-cto-challenge/Zubik_DZ-09_adr-llm-hosting.pdf) (PDF)
- [ ] [10. Архитектурный надзор и управление техническим долгом](./10-arkhitekturnyy-nadzor-tekhdolg/10-arkhitekturnyy-nadzor-tekhdolg.md)

### Блок 3. Качество и безопасность
- [ ] [11. Проектирование интеграций: от классики до AI-стандартов](./11-integratsii-klassika-ai/11-integratsii-klassika-ai.md)
- [ ] [12. Архитектура данных для AI-систем](./12-arkhitektura-dannykh-ai/12-arkhitektura-dannykh-ai.md) — **ДЗ:** [`Zubik_DZ-12`](./12-arkhitektura-dannykh-ai/Zubik_DZ-12_data-pipeline.md) (задание + решение + PDF; [вариант 2 — БЗ из звонков КЦ](./12-arkhitektura-dannykh-ai/Zubik_DZ-12_callcenter-kb.md))
- [ ] [13. Оценка качества и тестирование GenAI-компонентов](./13-ocenka-kachestva-genai/13-ocenka-kachestva-genai.md)
- [ ] [14. Security by Design: архитектура для защиты AI-систем](./14-security-by-design/14-security-by-design.md)

### Блок 4. Инфраструктура
- [ ] [15. Архитектура наблюдаемости (Observability)](./15-observability/15-observability.md) — **ДЗ** _(после урока)_
- [ ] [16. Расчёт ресурсов (Sizing) для приложений и данных](./16-sizing-resursov/16-sizing-resursov.md)
- [ ] [17. Расчёт ресурсов и оптимизация инференса LLM](./17-optimizaciya-inferensa-llm/17-optimizaciya-inferensa-llm.md) — **ДЗ** _(после урока)_
- [ ] [18. Инфраструктура как код (IaC) и CI/CD](./18-iac-ci-cd/18-iac-ci-cd.md)
- [ ] [19. Архитектура MLOps-конвейеров](./19-mlops-konveyery/19-mlops-konveyery.md)
- [ ] [20. Стратегии развёртывания и вывода в Production](./20-deployment-strategii-prod/20-deployment-strategii-prod.md) — **ДЗ** _(после урока)_
- [ ] [21. Архитектура высокой доступности (HA) и восстановления (DR)](./21-ha-i-dr/21-ha-i-dr.md)

### Блок 5. Продвинутые паттерны
- [ ] [22. Serverless vs. Kubernetes для AI-ворклоадов](./22-serverless-vs-k8s/22-serverless-vs-k8s.md)
- [ ] [23. Событийно-ориентированная архитектура (EDA) для AI](./23-eda-dlya-ai/23-eda-dlya-ai.md)
- [ ] [24. Архитектура для High-Load и Low-Latency инференса](./24-high-load-low-latency/24-high-load-low-latency.md) — **ДЗ** _(после урока)_
- [ ] [25. Гибридная и мультиоблачная архитектура для AI](./25-gibridnaya-multioblachnaya/25-gibridnaya-multioblachnaya.md)
- [ ] [26. Архитектура для Multi-tenancy в AI SaaS](./26-multi-tenancy-ai-saas/26-multi-tenancy-ai-saas.md)
- [ ] [27. Federated Learning и Privacy-Preserving архитектура](./27-federated-learning-privacy/27-federated-learning-privacy.md)

### Блок 6. Стратегия и экономика
- [ ] [28. FinOps: архитектура, управляемая стоимостью](./28-finops/28-finops.md)
- [ ] [29. Технологический радар и эволюция архитектуры](./29-tehradar-evolyuciya/29-tehradar-evolyuciya.md)
- [ ] [30. Ethical AI by Design и архитектура для Governance](./30-ethical-ai-governance/30-ethical-ai-governance.md) — **ДЗ** _(после урока)_
- [ ] [31. API как продукт: проектирование и управление](./31-api-kak-produkt/31-api-kak-produkt.md)

### Финальный блок. Проектная работа
- [ ] [32. Выбор темы и организация проектной работы](./final-project/sessions/32-vybor-temy.md)
- [ ] [33. Консультация по проектам и домашним заданиям](./final-project/sessions/33-konsultaciya.md)
- [ ] [34. Защита проектных работ](./final-project/sessions/34-zashchita.md)
- [ ] [35. Подведение итогов курса](./final-project/sessions/35-podvedenie-itogov.md)
- [ ] [36. Итоговый опрос по курсу](./final-project/sessions/36-itogovyy-opros.md)

📦 Финальный проект: см. [`final-project/README.md`](./final-project/README.md) (полное ТЗ).

## Лицензия и доступ

Материалы — для личного использования и обмена с коллегами в рамках корпоративного обучения. Не публиковать защищённый авторским правом контент OTUS (видеозаписи, оригинальные презентации преподавателей).
