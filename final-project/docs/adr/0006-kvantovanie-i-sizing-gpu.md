---
id: ADR-0006
title: Квантование и sizing GPU — FP8 на 2× H100
date: 2026-05-26
status: proposed
deciders: [Зубик Александр]
tags: [quantization, fp8, awq, gpu, sizing, h100, vllm, kv-cache]
---

# ADR-0006. Квантование и sizing GPU — FP8 на 2× H100

## Контекст
ADR-0002 выбрал baseline `Qwen3.6-27B` (dense), ADR-0003 — движок vLLM. Нужно зафиксировать **precision/квантование**, распределение по GPU (tensor parallelism) и бюджет VRAM (веса + KV-cache).

- **Железо (фиксировано):** **Lenovo ThinkSystem SR675 V3, 2× NVIDIA H100 NVL 94 GB** (≈188 GB, NVLink-bridge). On-prem, в контуре (ADR-0001).
- **Hopper → FP8 «из коробки»:** H100 имеет аппаратный FP8 (e4m3/e5m2). Это меняет дефолт относительно брифа (он писался под consumer GPU и предлагал AWQ/GGUF).
- **Профиль:** RAG + агенты, длинный контекст (Qwen3.6 — 256k), параллельные запросы → важен запас под **KV-cache** и batch.
- **Требование брифа «KV-cache optimization»** закрывается PagedAttention (vLLM) + FP8 KV-cache.

## Рассмотренные варианты
1. **BF16/FP16 (без квантования)** — 27B ≈ 54 GB (1 GPU). **Хорошо:** эталонное качество. **Плохо:** меньше VRAM под KV-cache/batch, ниже throughput, чем FP8.
2. **FP8 (Hopper-native)** — 27B ≈ 27 GB. **Хорошо:** качество ≈ BF16 (near-lossless), **~2× throughput**, FP8 KV-cache → огромный запас под 256k-контекст и большой batch на одной карте. **Плохо:** нужен свежий vLLM, иногда калибровка; проверить деградацию на RU.
3. **AWQ / GPTQ 4-bit** — 27B ≈ 15 GB. **Хорошо:** минимальный VRAM. **Плохо:** на H100 «жмём ради VRAM, которого не дефицит», теряя качество сильнее, чем FP8.
4. **GGUF (llama.cpp)** — **Плохо:** ориентирован на CPU/llama.cpp, слабая поддержка в vLLM (ADR-0003).

## Решение
Рабочая precision — **FP8** на 2× H100.

- **Baseline:** `Qwen3.6-27B` в **FP8 на одной H100 NVL (TP=1)** — ~27 GB на веса, **~67 GB свободно** под KV-cache (длинный контекст + высокий batch). Вторая карта — под **throughput-реплику / HA-резерв**.
- **Апгрейд качества:** MoE `Qwen3.5-122B-A10B` в FP8 (~122 GB) на **2× H100 (TP=2)** — решается eval'ом (ADR-0002).
- **AWQ-4bit** — задокументированный **fallback** для max-density сценариев или если нет FP8-весов нужного чекпойнта.
- **GGUF** — **Rejected** (не для vLLM).

Бриф предлагал AWQ/GGUF «для consumer GPU»; у нас Hopper, поэтому осознанно выбираем **FP8** как строго лучшее по качеству/throughput, оставив AWQ как запасной путь.

**Статус `proposed`:** перед `accepted` — бенчмарк FP8 vs BF16 на RU golden set (faithfulness/quality + tok/s, TTFT) и финализация модели (27B dense vs MoE) совместно с ADR-0002.

## Sizing (ориентир, H100 NVL 94 GB; без KV-cache/overhead)
| Модель | BF16 | FP8 | AWQ-4bit | Размещение |
|---|---|---|---|---|
| Qwen3.6-27B (dense, baseline) | ~54 GB | ~27 GB | ~15 GB | 1 GPU, большой запас под KV-cache |
| Qwen3.5-35B-A3B (MoE) | ~70 GB | ~35 GB | ~20 GB | 1 GPU |
| Qwen3.5-122B-A10B (MoE, апгрейд) | ~244 GB | ~122 GB | ~65 GB | FP8 — TP=2 (2× H100) |
| DeepSeek-V3 671B | ~1.3 TB | ~671 GB | ~350 GB | **не помещается** (нужно ~8+ H100) |

## Последствия
- **Положительные:**
  - Качество ≈ BF16 при ~2× throughput; FP8 KV-cache → длинный контекст и большой batch на одной карте.
  - 27B занимает одну H100 → вторая свободна под HA-реплику **или** MoE-апгрейд (TP=2).
- **Отрицательные / риски:**
  - FP8 требует свежего vLLM и иногда калибровки; подтвердить отсутствие деградации на RU golden set.
  - Конфиг NVLink/TP и тюнинг `gpu-memory-utilization` / `max-model-len`.
- **Что придётся изменить дальше:**
  - Прогнать бенчмарк → перевести в `accepted`; зафиксировать в ADR-0002 финальную модель.
  - Записать precision и метрики в **Model Card** (урок 08).

## Compliance & Ethics _(AI-специфичный раздел, урок 08)_
- Квантование может слегка просаживать качество → риск роста галлюцинаций; обязателен eval на RU golden set, чтобы FP8-модель проходила порог **faithfulness** (RAGAS) до релиза.
- Precision и результаты eval фиксируются в **Model Card** (часть Metrics).

## Связи
- **Следует из:** [ADR-0001](0001-on-premise-self-hosted-llm.md), [ADR-0002](0002-vybor-modeli.md), [ADR-0003](0003-llm-serving-engine.md).
- **Основано на:** требования стека из [`../../README.md`](../../README.md) (Блок 2: квантование, KV-cache optimization).
- **Шаблон:** [`../../../templates/adr.md`](../../../templates/adr.md).
