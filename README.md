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
- [ ] Заполнить раздел «О себе» в ЛК OTUS

### Модуль 1. Стратегический фундамент
- [ ] [01. Пресейл, контракты и работа с требованиями](./01-strategy/webinars/01-presale-i-trebovaniya.md)
- [ ] [02. Проектирование и оценка: план, риски, смета](./01-strategy/webinars/02-proektirovanie-i-ocenka.md)
- [ ] [03. Стратегия поставки ценности: от PoC до Production](./01-strategy/webinars/03-strategiya-postavki-cennosti.md) — **ДЗ:** [`03-strategiya-postavki.md`](./01-strategy/homework/03-strategiya-postavki.md)

### Модуль 2. Проектирование архитектуры
- [ ] [04. HLD с использованием C4 Model](./02-architecture/webinars/04-hld-c4-model.md)
- [ ] [05. LLD: компоненты и взаимодействия](./02-architecture/webinars/05-lld-komponenty.md) — **ДЗ:** [`05-lld.md`](./02-architecture/homework/05-lld.md)
- [ ] [06. RAG и его продвинутые вариации](./02-architecture/webinars/06-rag-i-prodvinutye-variacii.md)
- [ ] [07. AI-агенты и Multi-Agent Systems](./02-architecture/webinars/07-ai-agents-i-multi-agent-systems.md) — **ДЗ:** [`07-ai-agents.md`](./02-architecture/homework/07-ai-agents.md)

> Следующие занятия добавлять сюда по мере открытия в ЛК.

## Лицензия и доступ

Материалы — для личного использования и обмена с коллегами в рамках корпоративного обучения. Не публиковать защищённый авторским правом контент OTUS (видеозаписи, оригинальные презентации преподавателей).
