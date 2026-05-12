---
module: 02-architecture
lesson: 5
date:
lecturer:
tags: [LLD, компоненты, API, sequence]
status: todo
has_homework: true
---

# 05. Низкоуровневое проектирование (LLD): компоненты и взаимодействия

## TL;DR

## Контекст и проблема
_Что должен содержать LLD AI-компонента, как описывать взаимодействия и контракты._

## Состав LLD
- [ ] Назначение и место в HLD
- [ ] Внешние интерфейсы (API, события)
- [ ] Внутренняя структура
- [ ] Модель данных
- [ ] Алгоритмы / sequence-диаграммы
- [ ] Обработка ошибок
- [ ] НФТ
- [ ] Безопасность
- [ ] Наблюдаемость
- [ ] Тестирование

## Ключевые тезисы
-
-
-

## Диаграммы

```mermaid
sequenceDiagram
  participant C as Client
  participant API
  participant LLM
  C->>API: request
  API->>LLM: prompt
  LLM-->>API: response
  API-->>C: result
```

## Примеры / кейсы

## Вопросы и ответы

## Что почитать / посмотреть

## Мои выводы

## Связанное ДЗ
- [`../homework/05-lld.md`](../homework/05-lld.md)
