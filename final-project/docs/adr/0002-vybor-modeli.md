---
id: ADR-0002
title: Выбор LLM — Qwen3.6-27B (open-weight, dense)
date: 2026-05-26
status: proposed
deciders: [Зубик Александр]
tags: [llm, model, qwen3.6, t-pro, deepseek, saiga, ru, tool-calling, license]
---

# ADR-0002. Выбор LLM — Qwen3.6-27B (open-weight, dense)

## Контекст
ADR-0001 зафиксировал self-hosted open-weight LLM, ADR-0003 — движок (vLLM). Теперь — **какую модель** запускать. Ограничения и силы давления:

- **Только open-weight:** для air-gapped нужны **скачиваемые веса** + разрешительная лицензия (self-host и хранение в контуре без phone-home). Проприетарные API-модели исключены by design (ADR-0001).
- **Sizing:** целевое железо — **2× H100 80 GB** (160 GB, NVLink). Это снимает жёсткий лимит: dense-модели до ~30B идут в BF16/FP8 на одной карте без потери качества, MoE-варианты — на двух. Квантование — инструмент throughput, а не условие «влезания» (см. [ADR-0006](0006-kvantovanie-i-sizing-gpu.md)). Гиганты 100B+ dense / 600B+ MoE (DeepSeek-V3 671B) всё равно не помещаются.
- **Русский язык:** база знаний и запросы — на русском; нужна сильная RU-генерация (целевые бенчи — MERA / ruMMLU).
- **Агентность:** LangGraph-агенты требуют надёжного **tool-calling / function-calling**.
- **Совместимость:** нативная поддержка в vLLM + готовые FP8/AWQ-веса (ADR-0003, ADR-0006).
- **Актуальность:** на 2026-05 актуальная open-weight генерация Qwen — **Qwen3.6** (Apache 2.0), подтверждено на HF.

## Рассмотренные варианты
1. **Qwen3.6-27B** (dense, Apache 2.0) + RU-fallback на базе Qwen2.5 (**T-pro-it ~32B**, **T-lite ~8B**)
   - **Хорошо:** актуальный open-weight dense-флагман; нативный tool-calling; контекст **256k** (до 1M с YaRN); **Apache 2.0** (чистая лицензия для air-gapped); 27B тривиально влезает на одну H100 (BF16 ~54 GB, FP8 ~27 GB); first-class в vLLM/SGLang; есть FP8/AWQ/GPTQ-сборки; сильный мультиязык.
   - **Плохо:** RU-дообучек именно под Qwen3.6 может ещё не быть → RU-качество подтверждать eval'ом (есть проверенный fallback T-pro на Qwen2.5).
2. **MoE-варианты Qwen** (Qwen3.5-122B-A10B, Qwen3.6-35B-A3B) — _как апгрейд качества_
   - **Хорошо:** выше качество при малом числе активных параметров (быстрый инференс); 122B-A10B в FP8 (~122 GB) влезает на 2× H100.
   - **Плохо:** сложнее эксплуатация MoE; для baseline избыточно — рассматриваем как путь апгрейда.
3. **DeepSeek-V3** — **Rejected**
   - **Плохо:** **671B MoE** не помещается даже на 2× H100 (нужно ~8+ карт) → нарушает sizing ADR-0006. (Дистилляты DeepSeek-R1 в 7–32B — отдельные кандидаты, фактически другая база.)
4. **Saiga** (RU-finetune поверх Llama-3 / Mistral) — **Rejected**
   - **Плохо:** лицензии Llama Community с ограничениями (хуже для перераспространения в контуре); tool-calling слабее и менее стабилен, чем у Qwen; качество на сложных задачах ниже.

## Решение
**Baseline — `Qwen3.6-27B` (dense, Apache 2.0)**, precision FP8 на H100 (ADR-0006). Что перевесило: актуальная open-weight генерация, разрешительная лицензия для air-gapped, нативный tool-calling под агентов, длинный контекст под RAG, first-class в vLLM, комфортный sizing на одной H100.

**Статус `proposed`:** перед `accepted` прогнать RU-eval (MERA / ruMMLU) + tool-calling-тест на golden set, сравнив **`Qwen3.6-27B`** с RU-проверенным **`T-pro-it`** (Qwen2.5-32B). Если RU-качество Qwen3.6 окажется ниже T-pro — берём T-pro как baseline до выхода RU-тюна на Qwen3.x. Путь апгрейда — MoE (122B-A10B). **DeepSeek-V3** и **Saiga** — **Rejected**.

### Почему не самая новая (Qwen3.7-Max)
- **Qwen3.7-Max — проприетарная, API-only** (запуск 20.05.2026, Alibaba Cloud Model Studio). **Открытых весов нет** (подтверждено на 2026-05) → использовать = звать внешний API → **прямое нарушение ADR-0001** (air-gapped). Снимается на первом фильтре, независимо от качества.
- **«Свежесть» — не критерий.** Допустимы только open-weight модели; среди них решает лицензия + sizing + RU + tool-calling. Если/когда Alibaba выпустит **open-weight Qwen3.7**, это может **заменить (`superseded by`)** данное решение — но это эволюция open-weight линейки, а не повод брать проприетарный Max.

## Последствия
- **Положительные:**
  - Актуальная модель с длинным контекстом и tool-calling «из коробки»; Apache 2.0 снимает юридические риски air-gapped.
  - 27B dense комфортно влезает на одну H100 → вторая карта свободна под throughput/HA или MoE-апгрейд.
- **Отрицательные / риски:**
  - RU-качество Qwen3.6 не подтверждено (нет RU-тюна) → риск, закрываемый eval'ом и fallback'ом на T-pro.
  - Привязка к весам Qwen (Alibaba); план B — RU-дообучка или совместимая модель той же лиги.
- **Что придётся изменить дальше:**
  - ADR-0006: финальная precision (FP8) и sizing под выбранный размер.
  - **Model Card** на финальный чекпойнт (Intended Use / Out-of-scope / Training Data / Metrics — урок 08).

## Compliance & Ethics _(AI-специфичный раздел, урок 08)_
- **Лицензия:** Apache 2.0 (Qwen3.6 / Qwen2.5 / T-pro) разрешает коммерческий self-host и хранение весов в air-gapped без обращения наружу — соответствует ADR-0001.
- **Bias:** instruction-tuned модель → риск культурной/языковой предвзятости; план — eval на MERA + ручная проверка чувствительных доменов.
- **Галлюцинации / safety:** обязательны RU output-guardrails и RAG-grounding (ADR-0001).
- **Происхождение весов:** фиксировать checksum и версию, скачивать из доверенного зеркала, хранить офлайн.

## Связи
- **Следует из:** [ADR-0001](0001-on-premise-self-hosted-llm.md) (self-hosted LLM), [ADR-0003](0003-llm-serving-engine.md) (vLLM).
- **Предшествует:** ADR-0005 (orchestration / агенты — зависят от tool-calling), [ADR-0006](0006-kvantovanie-i-sizing-gpu.md) (квантование и sizing GPU).
- **Основано на:** требования стека из [`../../README.md`](../../README.md) (Блок 2: Models — Qwen, DeepSeek, T-lite / Saiga; Open Source + RU) + проверка актуальности на HuggingFace (2026-05).
- **Шаблон:** [`../../../templates/adr.md`](../../../templates/adr.md).
