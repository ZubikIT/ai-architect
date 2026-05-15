---
module: 02-architecture
lesson: 5
date_assigned: 2026-05-15
date_due: 2026-05-21
date_submitted:
status: todo
grade:
---

# ДЗ 05. Многоуровневое проектирование: от C4 Model до спецификации API

## Задание

**Цель:** спроектировать многоуровневую архитектуру AI-сервиса с использованием диаграмм C4 и спецификации API для согласования интеграции.

**Контекст:** продолжаем работу над проектом из первого ДЗ (или выбрать свой кейс).

### Шаги

1. **C2 Container Diagram** — диаграмма контейнеров всей системы. Выделить: Frontend, Backend, AI Service, Vector DB, SQL DB.
2. **C3 Component Diagram** — «провалиться» внутрь контейнера AI Service. Показать внутренние компоненты (например: Controller, RAG Manager, LLM Client, Prompt Template Factory).
3. **Sequence Diagram** — диаграмма последовательности для сценария «Пользователь запрашивает рекомендацию».
4. **API Spec** — спецификация API в формате YAML/Swagger для взаимодействия Backend ↔ AI Service (эндпоинт `/get_recommendation`).

### Формат сдачи
- Ссылка на диаграммы (Draw.io / Structurizr / Holst) — с открытым доступом.
- Файл или ссылка на Gist с OpenAPI-спецификацией (YAML/JSON).

### Критерии приёмки
- [ ] **Соответствие нотации:** диаграммы читаемы, связи направлены верно.
- [ ] **Связность:** компоненты на C3 соответствуют шагам Sequence Diagram.
- [ ] **Качество API:** спецификация содержит типы данных, примеры запросов/ответов, коды ошибок.

### Полезные материалы
- C4 Model: https://c4model.com/
- Swagger Editor: https://editor.swagger.io/
- Пример Petstore: https://petstore.swagger.io/

## Решение

### Подход

### Артефакты
- [ ] C2 Container Diagram (Structurizr / Draw.io)
- [ ] C3 Component Diagram для контейнера AI Service
- [ ] Sequence Diagram «Запрос рекомендации»
- [ ] OpenAPI 3.x спецификация эндпоинта `/get_recommendation`
- [ ] Публичные ссылки на диаграммы и Gist

### Реализация

## Сложности и решения

## Обратная связь от преподавателя
