---
id: ADR-0003
title: LLM Serving Engine — vLLM (vs SGLang, TGI)
date: 2026-05-26
status: proposed
deciders: [Зубик Александр]
tags: [llm, serving, inference, vllm, sglang, tgi, throughput]
---

# ADR-0003. LLM Serving Engine — vLLM (vs SGLang, TGI)

## Контекст
Решение ADR-0001 зафиксировало self-hosted LLM в изолированном контуре. Нужен **движок инференса**, который поднимет open-weight модель как сервис. Ограничения и силы давления:

- **Железо:** **2× H100 NVL 94 GB** (Hopper) — поддержка **FP8** и tensor parallelism; нужен эффективный **KV-cache** (PagedAttention). Квантование/precision — [ADR-0006](0006-kvantovanie-i-sizing-gpu.md).
- **Профиль нагрузки:** агентный + RAG-флоу (LangGraph, stateful) с **общими системными промптами** на каждом шаге → выигрывает **prefix caching**; много параллельных коротких запросов → нужен **continuous batching**.
- **Модели:** RU-ориентированные open-weight (Qwen 2.5/3, DeepSeek, T-lite / Saiga) — движок должен их поддерживать «из коробки».
- **Интеграция:** оркестратор и guardrails проще всего цеплять через **OpenAI-совместимый API**.
- **Команда:** ML-компетенции начальные → критичны зрелость, документация и размер сообщества (низкий операционный риск).
- **Air-gapped:** движок должен работать **полностью офлайн** (предзагруженные веса, без телеметрии/phone-home).

## Рассмотренные варианты
1. **vLLM**
   - **Хорошо:** де-факто стандарт; PagedAttention + **automatic prefix caching** + continuous batching; AWQ/GPTQ/FP8, tensor parallelism; OpenAI-совместимый API; широчайшая поддержка моделей (Qwen/DeepSeek/Saiga — first-class); самое большое сообщество и документация; офлайн-режим.
   - **Плохо:** GGUF — экспериментально/ограниченно; пиковый throughput на prefix-heavy агентных нагрузках может уступать SGLang.
2. **SGLang**
   - **Хорошо:** **RadixAttention** — лучший prefix caching, заточен под агентов/structured output/мультитёрн с общими префиксами; высокий throughput; speculative decoding; OpenAI-совместимый API.
   - **Плохо:** моложе, сообщество и экосистема меньше vLLM → выше операционный риск для команды с начальным ML; быстрее меняется API.
3. **TGI (HuggingFace Text Generation Inference)**
   - **Хорошо:** production-ready, тесная интеграция с HF-экосистемой, простой Docker-деплой, OpenAI-совместимый API, AWQ/GPTQ.
   - **Плохо:** в ряде бенчмарков throughput ниже vLLM/SGLang; нет GGUF; меньший momentum; исторически были вопросы по лицензии (HFOIL → откат на Apache 2.0) — осадок для энтерпрайза.

## Решение
Берём **vLLM** как движок инференса по умолчанию. Критерии, которые перевесили: зрелость + крупнейшее сообщество (минимальный операционный риск для команды с начальными ML-навыками), полное покрытие требований брифа (AWQ + PagedAttention KV-cache + automatic prefix caching), OpenAI-совместимый API (простая интеграция с LangGraph и guardrails) и first-class поддержка целевых RU-моделей.

**Статус `proposed`:** это high-impact / трудно-обратимое решение — перед `accepted` прогнать бенчмарк (throughput, TTFT, tok/s) на целевом GPU на 2–3 кандидат-моделях. **SGLang** — задокументированный запасной вариант: если агентная prefix-heavy нагрузка покажет существенный выигрыш RadixAttention, ADR может быть заменён (`superseded by`). **TGI** — **Rejected**.

## Последствия
- **Положительные:**
  - Готовый OpenAI-совместимый эндпоинт → оркестратор/guardrails подключаются без адаптеров.
  - PagedAttention + prefix caching + continuous batching закрывают требование брифа по KV-cache на ограниченном железе.
  - Большое сообщество → быстрые ответы, много рецептов квантования и деплоя.
- **Отрицательные / риски:**
  - Если выберем распространение в GGUF (llama.cpp-экосистема) — vLLM здесь слабее; митигируется выбором AWQ (см. ADR-0006).
  - На чисто агентной prefix-heavy нагрузке возможен проигрыш SGLang по throughput → проверяется бенчмарком.
- **Что придётся изменить дальше:**
  - Прогнать бенчмарк и перевести ADR в `accepted` (или `superseded` на SGLang).
  - Согласовать с ADR-0002 (модель) и ADR-0006 (квантование/sizing): конкретный формат весов и tensor parallelism под выбранный GPU.

## Compliance & Ethics _(AI-специфичный раздел, урок 08)_
- **Air-gapped / № 99-З:** vLLM работает офлайн с предзагруженными весами, без обязательной телеметрии — соответствует контуру ADR-0001. На сетевом уровне исходящий трафик движка блокируется.
- **Безопасность модели:** ответственность за обновления весов и CVE движка — на нас (план: фиксировать версии образов, сканировать, обновлять по регламенту).
- Этические аспекты генерации (галлюцинации, toxicity) решаются на уровне guardrails и Model Card, а не движка — см. ADR-0001.

## Связи
- **Следует из:** [ADR-0001](0001-on-premise-self-hosted-llm.md) (self-hosted LLM).
- **Связан с:** ADR-0002 (выбор модели), ADR-0006 (квантование и sizing GPU).
- **Основано на:** требования стека из [`../../README.md`](../../README.md) (Блок 2: LLM Serving — vLLM/SGLang/TGI, AWQ/GGUF, KV-cache).
- **Шаблон:** [`../../../templates/adr.md`](../../../templates/adr.md).
