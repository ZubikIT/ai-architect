"""Нагрузочный замер платформы: RPS и латентность по ступеням параллелизма.

Методика — [ДЗ-24](../../../24-high-load-low-latency/Zubik_DZ-24_highload-realtime.md),
адаптированная под то, что реально можно измерить на одном хосте без GPU.

**Закрытая петля, а не фиксированный поток запросов.** N воркеров шлют запрос,
дожидаются ответа и шлют следующий; параллелизм растёт ступенями. Открытая петля
(фиксированный arrival rate) моделирует реальный трафик точнее, но на ступени
выше насыщения она вырождается в бесконечную очередь и меряет уже не сервис, а
терпение генератора. Закрытая петля честно показывает, где RPS перестаёт расти, —
а это и есть то, что нужно от отчёта: **точка насыщения и её причина**.

Следствие, которое обязано быть названо: закрытая петля **не воспроизводит
coordinated omission**, но и не даёт латентность «под нагрузкой X RPS» — она даёт
латентность при X одновременных клиентах. Для вывода о SLO этого достаточно,
для capacity planning под заданный поток — нет.

Прогрев отбрасывается: первые запросы после старта прогревают пулы соединений и
кэши аллокатора, и их включение завышает хвосты на порядок.

    python -m tools.loadtest --base-url http://localhost:8080 --out ../docs/load/raw.json
"""
import argparse
import asyncio
import json
import statistics
import time

import httpx

# Сценарии: каждый бьёт в свой участок системы.
SCENARIOS = {
    # Пустой путь: сколько стоит сам сервис — ASGI, middleware, метрики.
    # Нужен как база отсчёта, иначе непонятно, что из latency принадлежит пайплайну.
    "healthz": {"method": "GET", "path": "/healthz", "body": None},
    # Одиночный GraphRAG: эмбеддинг → гибридный поиск → обход графа → сборка.
    "ask": {"method": "POST", "path": "/ask",
            "body": {"question": "Сколько дней основной ежегодный отпуск?", "roles": ["all"]}},
    # Тот же путь на вопросе, где графовое ребро ведёт в закрытый документ.
    "ask-acl": {"method": "POST", "path": "/ask",
                "body": {"question": "Как обрабатываются персональные данные командированного работника?",
                         "roles": ["legal"]}},
    # Мультиагентный путь: веер из двух ролей, то есть два прохода retrieval.
    "agents": {"method": "POST", "path": "/agents/ask",
               "body": {"question": "Как обрабатываются персональные данные командированного работника?",
                        "roles": ["legal"]}},
}


def percentile(values, q: float) -> float:
    """p-квантиль по ближайшему рангу: на сотнях замеров интерполяция создаёт
    видимость точности, которой в данных нет."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * len(ordered) + 0.5)) - 1))
    return ordered[index]


async def _worker(client, scenario, deadline, samples, errors):
    spec = SCENARIOS[scenario]
    while time.perf_counter() < deadline:
        start = time.perf_counter()
        try:
            if spec["method"] == "GET":
                r = await client.get(spec["path"])
            else:
                r = await client.post(spec["path"], json=spec["body"])
            elapsed = time.perf_counter() - start
            if r.status_code == 200:
                samples.append(elapsed)
            else:
                errors[str(r.status_code)] = errors.get(str(r.status_code), 0) + 1
        except Exception as e:                      # таймаут, обрыв, отказ в соединении
            errors[type(e).__name__] = errors.get(type(e).__name__, 0) + 1


async def run_step(base_url: str, scenario: str, concurrency: int,
                   duration: float, warmup: float, timeout: float) -> dict:
    """Одна ступень: `concurrency` клиентов в течение `duration` секунд."""
    limits = httpx.Limits(max_connections=concurrency + 4, max_keepalive_connections=concurrency + 4)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, limits=limits) as client:
        # Прогрев идёт тем же сценарием и тем же параллелизмом — прогревать
        # другим профилем значит прогреть не то.
        await _drain(client, scenario, warmup, concurrency)

        samples, errors = [], {}
        started = time.perf_counter()
        deadline = started + duration
        await asyncio.gather(*[
            _worker(client, scenario, deadline, samples, errors) for _ in range(concurrency)
        ])
        wall = time.perf_counter() - started

    total = len(samples) + sum(errors.values())
    return {
        "scenario": scenario,
        "concurrency": concurrency,
        "wall_seconds": round(wall, 2),
        "requests": total,
        "ok": len(samples),
        "errors": errors,
        "error_rate": round(sum(errors.values()) / total, 4) if total else 0.0,
        "rps": round(len(samples) / wall, 2) if wall else 0.0,
        "latency_ms": {
            "mean": round(statistics.fmean(samples) * 1000, 1) if samples else 0.0,
            "p50": round(percentile(samples, 0.50) * 1000, 1),
            "p95": round(percentile(samples, 0.95) * 1000, 1),
            "p99": round(percentile(samples, 0.99) * 1000, 1),
            "max": round(max(samples) * 1000, 1) if samples else 0.0,
        },
    }


async def _drain(client, scenario, seconds, concurrency):
    if seconds <= 0:
        return
    deadline = time.perf_counter() + seconds
    await asyncio.gather(*[
        _worker(client, scenario, deadline, [], {}) for _ in range(concurrency)
    ])


async def main_async(args) -> dict:
    results = []
    for scenario in args.scenarios:
        for concurrency in args.concurrency:
            step = await run_step(args.base_url, scenario, concurrency,
                                  args.duration, args.warmup, args.timeout)
            results.append(step)
            lat = step["latency_ms"]
            print(f"{scenario:9} c={concurrency:<3} RPS {step['rps']:7.2f}  "
                  f"p50 {lat['p50']:8.1f}  p95 {lat['p95']:8.1f}  p99 {lat['p99']:8.1f} мс  "
                  f"ошибок {step['error_rate']:.1%}", flush=True)
    return {"base_url": args.base_url, "duration": args.duration,
            "warmup": args.warmup, "results": results}


def main():
    ap = argparse.ArgumentParser(description="Нагрузочный замер платформы (методика ДЗ-24)")
    ap.add_argument("--base-url", default="http://localhost:8080")
    ap.add_argument("--scenarios", nargs="+", default=["healthz", "ask", "agents"],
                    choices=sorted(SCENARIOS))
    ap.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 4, 8, 16])
    ap.add_argument("--duration", type=float, default=30.0, help="секунд на ступень")
    ap.add_argument("--warmup", type=float, default=5.0, help="секунд прогрева на ступень")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--out", help="куда сложить сырые замеры (JSON)")
    args = ap.parse_args()

    report = asyncio.run(main_async(args))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nсырые замеры: {args.out}")


if __name__ == "__main__":
    main()
