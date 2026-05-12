# OTUS AI Architect — материалы курса

Репозиторий с конспектами, домашними заданиями, архитектурными артефактами и финальным проектом по курсу [AI Architect](https://otus.ru/lessons/ai-architect/) от OTUS.

## Структура

| Папка | Модуль |
|---|---|
| [`01-strategy/`](./01-strategy/) | Стратегический фундамент: анализ требований, планирование, оценка рисков |
| [`02-architecture/`](./02-architecture/) | Проектирование архитектуры: HLD, LLD, RAG, AI-агенты, Multi-Agent Systems |
| [`03-quality/`](./03-quality/) | Качество и безопасность: тестирование GenAI, интеграции, архитектура данных |
| [`04-infrastructure/`](./04-infrastructure/) | Инфраструктура: sizing, MLOps, CI/CD, высокая доступность |
| [`05-patterns/`](./05-patterns/) | Продвинутые паттерны: Serverless, Kubernetes, High-Load, Multi-tenancy |
| [`06-economics/`](./06-economics/) | Стратегия и экономика: FinOps, governance, API-дизайн |
| [`final-project/`](./final-project/) | Финальный проект — пакет архитектурных документов и экономическое обоснование |
| [`templates/`](./templates/) | Шаблоны: конспект вебинара, ДЗ, ADR, HLD, LLD |
| [`resources/`](./resources/) | Общие материалы — ссылки, книги, статьи, словарь терминов |

Внутри каждого модуля:

- `webinars/` — конспекты вебинаров (по одному файлу на занятие)
- `homework/` — домашние задания и решения
- `artifacts/` — диаграммы, схемы, ADR, документы, которые накопились по модулю

## Как пользоваться

1. На каждый вебинар — копия шаблона из `templates/webinar-notes.md` в `NN-module/webinars/`.
2. На каждое ДЗ — копия `templates/homework.md` в `NN-module/homework/`.
3. Архитектурные решения оформляются как ADR (`templates/adr.md`), складываются в `artifacts/` модуля или в `final-project/docs/`.
4. Большие бинарники (видео, объёмные pdf) **в репозиторий не коммитим** — храним в S3/облаке, в репо — только ссылки.

## Соглашения по именованию

- Файлы: `kebab-case`, с префиксом-номером занятия: `01-trebovaniya-k-ai-sisteme.md`.
- Диаграммы Mermaid — прямо в md-файлах. Сложные C4-диаграммы — отдельно в `artifacts/` (`.drawio`, `.png` рядом).
- Даты в формате `YYYY-MM-DD`.

## Программа (по мере открытия в ЛК)

### Орг. задачи
- [ ] [Заполнить раздел «О себе»](./01-strategy/homework/00-o-sebe.md) в ЛК OTUS

### Модуль 1. Стратегический фундамент
- [ ] [01. Пресейл, контракты и работа с требованиями](./01-strategy/webinars/01-presale-i-trebovaniya.md)
- [ ] [02. Проектирование и оценка: план, риски, смета](./01-strategy/webinars/02-proektirovanie-i-ocenka.md)
- [ ] [03. Стратегия поставки ценности: от PoC до Production](./01-strategy/webinars/03-strategiya-postavki-cennosti.md) — **ДЗ:** [`03-strategiya-postavki.md`](./01-strategy/homework/03-strategiya-postavki.md)

### Модуль 2. Проектирование архитектуры
- [ ] [04. HLD с использованием C4 Model](./02-architecture/webinars/04-hld-c4-model.md)
- [ ] [05. LLD: компоненты и взаимодействия](./02-architecture/webinars/05-lld-komponenty.md) — **ДЗ:** [`05-lld.md`](./02-architecture/homework/05-lld.md)
- [ ] [06. RAG и его продвинутые вариации](./02-architecture/webinars/06-rag-i-prodvinutye-variacii.md)
- [ ] [07. AI-агенты и Multi-Agent Systems](./02-architecture/webinars/07-ai-agents-i-multi-agent-systems.md) — **ДЗ:** [`07-ai-agents.md`](./02-architecture/homework/07-ai-agents.md)
- [ ] [08. Документирование решений: ADR](./02-architecture/webinars/08-adr-documentation.md)
- [ ] [09. Верификация архитектуры и «CTO Challenge»](./02-architecture/webinars/09-verifikaciya-cto-challenge.md) — **ДЗ:** [`09-verifikaciya.md`](./02-architecture/homework/09-verifikaciya.md)
- [ ] [10. Архитектурный надзор и управление техническим долгом](./02-architecture/webinars/10-arkhitekturnyy-nadzor-tekhdolg.md)

### Модуль 3. Качество и безопасность
- [ ] [11. Проектирование интеграций: от классики до AI-стандартов](./03-quality/webinars/11-integratsii-klassika-ai.md)
- [ ] [12. Архитектура данных для AI-систем](./03-quality/webinars/12-arkhitektura-dannykh-ai.md) — **ДЗ:** [`12-arkhitektura-dannykh.md`](./03-quality/homework/12-arkhitektura-dannykh.md)
- [ ] [13. Оценка качества и тестирование GenAI-компонентов](./03-quality/webinars/13-ocenka-kachestva-genai.md)
- [ ] [14. Security by Design: архитектура для защиты AI-систем](./03-quality/webinars/14-security-by-design.md)

### Модуль 4. Инфраструктура
- [ ] [15. Архитектура наблюдаемости (Observability)](./04-infrastructure/webinars/15-observability.md) — **ДЗ:** [`15-observability.md`](./04-infrastructure/homework/15-observability.md)
- [ ] [16. Расчёт ресурсов (Sizing) для приложений и данных](./04-infrastructure/webinars/16-sizing-resursov.md)
- [ ] [17. Расчёт ресурсов и оптимизация инференса LLM](./04-infrastructure/webinars/17-optimizaciya-inferensa-llm.md) — **ДЗ:** [`17-optimizaciya-inferensa.md`](./04-infrastructure/homework/17-optimizaciya-inferensa.md)
- [ ] [18. Инфраструктура как код (IaC) и CI/CD](./04-infrastructure/webinars/18-iac-ci-cd.md)
- [ ] [19. Архитектура MLOps-конвейеров](./04-infrastructure/webinars/19-mlops-konveyery.md)
- [ ] [20. Стратегии развёртывания и вывода в Production](./04-infrastructure/webinars/20-deployment-strategii-prod.md) — **ДЗ:** [`20-deployment.md`](./04-infrastructure/homework/20-deployment.md)
- [ ] [21. Архитектура высокой доступности (HA) и восстановления (DR)](./04-infrastructure/webinars/21-ha-i-dr.md)

### Модуль 5. Продвинутые паттерны
- [ ] [22. Serverless vs. Kubernetes для AI-ворклоадов](./05-patterns/webinars/22-serverless-vs-k8s.md)
- [ ] [23. Событийно-ориентированная архитектура (EDA) для AI](./05-patterns/webinars/23-eda-dlya-ai.md)
- [ ] [24. Архитектура для High-Load и Low-Latency инференса](./05-patterns/webinars/24-high-load-low-latency.md) — **ДЗ:** [`24-high-load.md`](./05-patterns/homework/24-high-load.md)
- [ ] [25. Гибридная и мультиоблачная архитектура для AI](./05-patterns/webinars/25-gibridnaya-multioblachnaya.md)
- [ ] [26. Архитектура для Multi-tenancy в AI SaaS](./05-patterns/webinars/26-multi-tenancy-ai-saas.md)
- [ ] [27. Federated Learning и Privacy-Preserving архитектура](./05-patterns/webinars/27-federated-learning-privacy.md)

### Модуль 6. Стратегия и экономика
- [ ] [28. FinOps: архитектура, управляемая стоимостью](./06-economics/webinars/28-finops.md)
- [ ] [29. Технологический радар и эволюция архитектуры](./06-economics/webinars/29-tehradar-evolyuciya.md)
- [ ] [30. Ethical AI by Design и архитектура для Governance](./06-economics/webinars/30-ethical-ai-governance.md) — **ДЗ:** [`30-ethical-governance.md`](./06-economics/homework/30-ethical-governance.md)
- [ ] [31. API как продукт: проектирование и управление](./06-economics/webinars/31-api-kak-produkt.md)

### Финальный блок. Проектная работа
- [ ] [32. Выбор темы и организация проектной работы](./final-project/sessions/32-vybor-temy.md)
- [ ] [33. Консультация по проектам и домашним заданиям](./final-project/sessions/33-konsultaciya.md)
- [ ] [34. Защита проектных работ](./final-project/sessions/34-zashchita.md)
- [ ] [35. Подведение итогов курса](./final-project/sessions/35-podvedenie-itogov.md)
- [ ] [36. Итоговый опрос по курсу](./final-project/sessions/36-itogovyy-opros.md)

📦 Финальный проект: см. [`final-project/README.md`](./final-project/README.md) (полное ТЗ).

## Лицензия и доступ

Материалы — для личного использования и обмена с коллегами в рамках корпоративного обучения. Не публиковать защищённый авторским правом контент OTUS (видеозаписи, оригинальные презентации преподавателей).
