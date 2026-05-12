---
project: Название проекта
version: 0.1
date: YYYY-MM-DD
authors: [Имя Фамилия]
status: draft  # draft | review | approved
---

# HLD. Название проекта

## 1. Цели и не-цели
**Цели:**
- ...

**Не-цели (out of scope):**
- ...

## 2. Бизнес-контекст
Кто заказчик, какие KPI, как измеряем успех.

## 3. Требования

### 3.1 Функциональные
- FR-1 ...

### 3.2 Нефункциональные
| Атрибут | Цель | Обоснование |
|---|---|---|
| Latency p95 |  |  |
| Throughput |  |  |
| Доступность |  |  |
| Стоимость |  |  |

## 4. Контекстная диаграмма (C4 L1)

```mermaid
C4Context
  title System Context
  Person(user, "Пользователь")
  System(sut, "AI System", "Описание")
  System_Ext(ext, "External", "Описание")
  Rel(user, sut, "использует")
  Rel(sut, ext, "вызывает")
```

## 5. Контейнерная диаграмма (C4 L2)

```mermaid
flowchart LR
  UI[Web UI] --> API[API Gateway]
  API --> ORCH[Orchestrator]
  ORCH --> LLM[LLM Service]
  ORCH --> VS[(Vector Store)]
  ORCH --> DB[(RDBMS)]
```

## 6. Ключевые сценарии
- Сценарий 1: ...
- Сценарий 2: ...

## 7. Архитектурные решения
Ссылки на ADR.

## 8. Риски и допущения
| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
|  |  |  |  |

## 9. Roadmap
Фазы внедрения.
