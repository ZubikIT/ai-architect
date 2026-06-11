---
module: 03-quality
lesson: 12
date_assigned: 2026-06-09
date_submitted:
deadline: 2026-06-22
status: ready-to-submit
grade:
---

# ДЗ 12. Проектирование Data Pipelines и интеграционных шлюзов

## Задание
_Из ЛК (дословно)._

**Цель:** спроектировать data pipeline и выбрать хранилища для обеспечения консистентности данных при обучении и инференсе AI-системы.

**Задача:** для системы рекомендаций нужно регулярно обновлять данные о товарах и поведении пользователей.

**Шаги выполнения:**
1. **Data Sources:** определите источники (клики пользователей — стриминг, каталог товаров — батч из ERP).
2. **Pipeline Design:** нарисуйте схему ETL/ELT. Где происходит очистка? Где генерация эмбеддингов?
3. **Storage Selection:** выберите хранилища для разных этапов (Data Lake, Feature Store, Vector DB). Обоснуйте выбор конкретных технологий (напр., Kafka → Spark → S3 → Pinecone).
4. **Data Governance:** опишите, как будет обеспечена консистентность данных между Feature Store (для обучения) и онлайн-инференсом.

**Формат сдачи:** схема архитектуры данных (Diagram) + текстовое описание (1–2 стр).

**Вспомогательный материал:** пример архитектуры Lambda/Kappa.

**Рекомендуем сдать до:** 22.06.2026.

## Цели
- Спроектировать end-to-end data pipeline: от сбора сырых данных (stream + batch) до датасета для обучения и данных для онлайн-инференса.
- Осознанно выбрать хранилища под этапы (Data Lake / Feature Store / Vector DB) с обоснованием технологий.
- Показать механизм защиты от training-serving skew (роль Feature Store) — см. конспект [[12-arkhitektura-dannykh-ai]].

## Критерии приёмки
Статус «Принято», если:
- [ ] **Выбор технологий:** инструменты соответствуют задачам (Stream vs Batch).
- [ ] **Полнота потока:** данные прослеживаются от источника до модели.
- [ ] **Feature Store:** понимание роли Feature Store для предотвращения Training-Serving Skew.

Компетенции (из ЛК): проектировать отказоустойчивые интеграции с унаследованными системами через брокеры сообщений; проектировать сквозные (end-to-end) data pipelines для AI-систем, от сбора до подготовки данных для обучения моделей.

## Решение

### Подход
Кейс продолжает **ДЗ-03 (TechnoMart)** — тот же ритейлер, теперь data-слой его системы рекомендаций. Три осевых решения:
1. **Lambda-light на одном движке:** клики — stream (Kafka → Spark Structured Streaming), каталог из ERP — ночной batch (Airflow + ACL, урок 11); оба контура на Spark, определения фич — в Feature Store, что снимает боль «двух кодовых баз» классической Lambda.
2. **ELT + Lakehouse:** сырьё навсегда в MinIO + Iceberg (ACID, time travel = версионирование датасетов), очистка/DQ (Great Expectations, quarantine) — в transform-слое.
3. **On-prem стек вместо референса** `Kafka → Spark → S3 → Pinecone`: Pinecone (SaaS) заменён на **Qdrant**, S3 — на MinIO; PII не покидает контур (РБ №99-З).

Консистентность train/serve (критерий про **training-serving skew**): единые определения фич в **Feast** registry (offline = Iceberg → датасет с point-in-time joins; online = Redis через материализацию); версии «модель ↔ feature views ↔ эмбеддер» связаны в MLflow; коллекции Qdrant именованы версией эмбеддера (blue/green через alias).

### Артефакты
- **Сдача:** [`Zubik_DZ-12_data-pipeline.pdf`](Zubik_DZ-12_data-pipeline.pdf) (4 стр.: источники → схема → таблица хранилищ → governance).
- Источник: [`Zubik_DZ-12_data-pipeline.md`](Zubik_DZ-12_data-pipeline.md) (mermaid-схема внутри).
- Диаграмма: [`artifacts/dz-12-diagram-1.png`](artifacts/dz-12-diagram-1.png).

### Реализация
PDF собран путём B из [[md-to-pdf-toolchain]]: mermaid.ink (PNG, `?type=png&width=1400&scale=2`, диаграмма в ориентации TB — LR не читается на A4) → подмена блока на картинку → `scripts/md-to-pdf.sh` (pandoc + typst).

## Сложности и решения
- `mermaid.ink` отдаёт 403 на python-urllib (режет UA) — качать через curl с браузерным User-Agent; `?scale=` работает только вместе с `?width=`.
- Широкая LR-диаграмма ужимается в нечитаемую полосу на A4 — для PDF строить вертикально (TB).

## Обратная связь от преподавателя
