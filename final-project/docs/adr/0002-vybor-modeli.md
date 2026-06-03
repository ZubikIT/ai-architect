---
id: ADR-0002
title: Выбор LLM — Qwen3.5-27B (open-weight, dense)
date: 2026-06-03
status: proposed
deciders: [Зубик Александр]
tags: [llm, model, qwen3.5, qwen3.6, t-pro, deepseek, saiga, ru, tool-calling, license]
---

# ADR-0002. Выбор LLM — Qwen3.5-27B (open-weight, dense)

## Контекст
ADR-0001 зафиксировал self-hosted open-weight LLM, ADR-0003 — движок (vLLM). Теперь — **какую модель** запускать. Ограничения и силы давления:

- **Только open-weight:** для air-gapped нужны **скачиваемые веса** + разрешительная лицензия (self-host и хранение в контуре без phone-home). Проприетарные API-модели исключены by design (ADR-0001).
- **Sizing:** целевое железо — **2× H100 NVL 94 GB** (≈188 GB, NVLink). Это снимает жёсткий лимит: dense-модели до ~30B идут в BF16/FP8 на одной карте без потери качества, MoE-варианты — на двух. Квантование — инструмент throughput, а не условие «влезания» (см. [ADR-0006](0006-kvantovanie-i-sizing-gpu.md)). Гиганты 100B+ dense / 600B+ MoE (DeepSeek-V3 671B) всё равно не помещаются.
- **Русский язык:** база знаний и запросы — на русском; нужна сильная RU-генерация (целевые бенчи — MERA / ruMMLU).
- **Агентность:** LangGraph-агенты требуют надёжного **tool-calling / function-calling**.
- **Совместимость:** нативная поддержка в vLLM + готовые FP8/AWQ-веса (ADR-0003, ADR-0006).
- **Актуальность (проверено 2026-06, HuggingFace):** актуальные open-weight генерации Qwen — **Qwen3.5** (фев 2026, dense, включая **27B**) и **Qwen3.6** (апр 2026, выпущена **только как MoE** `Qwen3.6-35B-A3B`, мультимодальная). Dense-модели «27B» в линейке 3.6 **не существует** — в ранней редакции этого ADR ошибочно фигурировал несуществующий «Qwen3.6-27B dense»; исправлено на реально существующий dense `Qwen3.5-27B`.

## Рассмотренные варианты
1. **Qwen3.5-27B** (dense, Apache 2.0) + RU-fallback на базе Qwen2.5 (**T-pro-it ~32B**, **T-lite ~8B**)
   - **Хорошо:** новейший open-weight **dense** ~27B; нативный **tool-calling** (parser `qwen3_coder` в vLLM/SGLang) + гибридный режим размышления (toggle `enable_thinking`); контекст **262k** (до ~1M с YaRN); **Apache 2.0** (чистая лицензия для air-gapped); 27B тривиально влезает на одну H100 (BF16 ~54 GB, FP8 ~27 GB); first-class в vLLM/SGLang; сильный мультиязык (MMMLU ~85.9, MMLU-ProX ~82.2).
   - **Плохо:** RU-дообучек именно под Qwen3.5 может ещё не быть → RU-качество подтверждать eval'ом (есть проверенный fallback T-pro на Qwen2.5).
2. **Qwen3.6-35B-A3B** (MoE 35B / 3B активных, **мультимодальная**, Apache 2.0) — _как путь апгрейда_
   - **Хорошо:** самая новая (апр 2026); MoE → быстрый инференс при малом числе активных параметров; vision + agentic-coding; tool-calling; FP8 (~35 GB) влезает на 2× H100; контекст 262k→1M.
   - **Плохо:** MoE сложнее в эксплуатации; мультимодальность избыточна для **текстового** RU-RAG; на тексте **не превосходит** dense-27B (MMMLU 85.2 vs 85.9, MMLU-ProX 81.0 vs 82.2 — выигрыш только на vision/VQA). Берём как upgrade-path при появлении нужды в vision/максимуме агентности.
3. **DeepSeek-V3** — **Rejected**
   - **Плохо:** **671B MoE** не помещается даже на 2× H100 (нужно ~8+ карт) → нарушает sizing ADR-0006. (Дистилляты DeepSeek-R1 в 7–32B — отдельные кандидаты, фактически другая база.)
4. **Saiga** (RU-finetune поверх Llama-3 / Mistral) — **Rejected**
   - **Плохо:** лицензии Llama Community с ограничениями (хуже для перераспространения в контуре); tool-calling слабее и менее стабилен, чем у Qwen; качество на сложных задачах ниже.

## Решение
**Baseline — `Qwen3.5-27B` (dense, Apache 2.0)**, precision FP8 на H100 (ADR-0006). Что перевесило: новейший open-weight **dense** (проще в эксплуатации при начальных MLOps-компетенциях), разрешительная лицензия для air-gapped, нативный tool-calling под агентов, длинный контекст под RAG, first-class в vLLM, комфортный sizing на одной H100, сильный мультиязык на тексте.

**Статус `proposed`:** перед `accepted` прогнать RU-eval (MERA / ruMMLU) + tool-calling-тест на golden set, сравнив **`Qwen3.5-27B`** с RU-проверенным **`T-pro-it`** (Qwen2.5-32B). Если RU-качество Qwen3.5 окажется ниже T-pro — берём T-pro как baseline до выхода RU-тюна на Qwen3.x. **Upgrade-path — `Qwen3.6-35B-A3B` (MoE)**. **DeepSeek-V3** и **Saiga** — **Rejected**.

### Почему dense-3.5-27B, а не самая новая Qwen3.6-35B-A3B
- **Самая новая open-weight — это MoE `Qwen3.6-35B-A3B`** (апр 2026, мультимодальная). Берём dense-`Qwen3.5-27B` baseline'ом, потому что: dense **проще в эксплуатации** (нач. MLOps), на **тексте не уступает** MoE-35B (см. бенчи выше), влезает на **одну** карту → вторая свободна под throughput/HA. MoE-3.6 зафиксирован как **upgrade path** (если понадобится vision или максимум агентности).
- **«Свежесть» — не критерий.** Допустимы только open-weight модели; среди них решает лицензия + sizing + RU + tool-calling. **Проприетарные API-only модели любой свежести исключены by design** (ADR-0001, air-gapped), независимо от качества. Если/когда выйдет open-weight dense следующего поколения подходящего размера — это может **заменить (`superseded by`)** данное решение.

## Последствия
- **Положительные:**
  - Актуальная dense-модель с длинным контекстом и tool-calling «из коробки»; Apache 2.0 снимает юридические риски air-gapped.
  - 27B dense комфортно влезает на одну H100 → вторая карта свободна под throughput/HA или MoE-апгрейд (Qwen3.6-35B-A3B).
- **Отрицательные / риски:**
  - RU-качество Qwen3.5 не подтверждено (нет RU-тюна) → риск, закрываемый eval'ом и fallback'ом на T-pro.
  - Привязка к весам Qwen (Alibaba); план B — RU-дообучка или совместимая модель той же лиги.
- **Что придётся изменить дальше:**
  - ADR-0006: финальная precision (FP8) и sizing под выбранный размер.
  - **Model Card** на финальный чекпойнт (Intended Use / Out-of-scope / Training Data / Metrics — урок 08).

## Compliance & Ethics _(AI-специфичный раздел, урок 08)_
- **Лицензия:** Apache 2.0 (Qwen3.5 / Qwen3.6 / Qwen2.5 / T-pro) разрешает коммерческий self-host и хранение весов в air-gapped без обращения наружу — соответствует ADR-0001.
- **Bias:** instruction-tuned модель → риск культурной/языковой предвзятости; план — eval на MERA + ручная проверка чувствительных доменов.
- **Галлюцинации / safety:** обязательны RU output-guardrails и RAG-grounding (ADR-0001).
- **Происхождение весов (РБ):** HuggingFace из РБ может быть ограничен → качать с **ModelScope** (Alibaba-зеркало, доступно) или поднять внутреннее зеркало; фиксировать checksum и версию, хранить офлайн.

## Связи
- **Следует из:** [ADR-0001](0001-on-premise-self-hosted-llm.md) (self-hosted LLM), [ADR-0003](0003-llm-serving-engine.md) (vLLM).
- **Предшествует:** ADR-0005 (orchestration / агенты — зависят от tool-calling), [ADR-0006](0006-kvantovanie-i-sizing-gpu.md) (квантование и sizing GPU).
- **Основано на:** требования стека из [`../../README.md`](../../README.md) (Блок 2: Models — Qwen, DeepSeek, T-lite / Saiga; Open Source + RU) + проверка актуальности на HuggingFace (2026-06).
- **Шаблон:** [`../../../templates/adr.md`](../../../templates/adr.md).
