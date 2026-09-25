#!/usr/bin/env python3
"""Боевые метрики vLLM за окно — из VictoriaMetrics, без единого синтетического запроса.

    python3 vllm_prod_stats.py                # два окна по умолчанию → stdout + JSON
    VM=http://10.100.1.16:8428 python3 vllm_prod_stats.py --out prod-2026-09-25.json

Считается по счётчикам и гистограммам, которые vLLM отдаёт сам (`/metrics`,
джоба `vllm-engine`). `increase()` переживает перезапуски движка.

Средние (sum/count) точные. Перцентили — `histogram_quantile`, то есть линейная
интерполяция внутри корзины: у TTFT между 1 и 2,5 с одна корзина, поэтому p50/p95
приближённые, и сравнивать их между окнами можно, а читать до десятых — нет.
"""
import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VM = os.environ.get("VM", "http://10.100.1.16:8428")
SEL = '{job="vllm-engine"}'

# Окна выбраны так, чтобы в них не попали перезапуски свопа и бенчмарки 18.09,
# а также нагрузочный прогон стенда 25.09 (19:02 UTC).
WINDOWS = {
    "qwen3.6-35b-a3b": ("2026-09-11T00:00:00Z", "2026-09-18T00:00:00Z"),
    "qwen3.8-27b": ("2026-09-19T00:00:00Z", "2026-09-25T18:00:00Z"),
}

HISTOGRAMS = {
    "ttft_s": "vllm:time_to_first_token_seconds",
    "e2e_s": "vllm:e2e_request_latency_seconds",
    "queue_s": "vllm:request_queue_time_seconds",
    "prefill_s": "vllm:request_prefill_time_seconds",
    "decode_s": "vllm:request_decode_time_seconds",
    "tpot_s": "vllm:request_time_per_output_token_seconds",
    "prompt_tokens": "vllm:request_prompt_tokens",
    "gen_tokens": "vllm:request_generation_tokens",
}


def ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


# Напрямую, мимо прокси: на macOS urllib берёт системный HTTP-прокси, а
# VictoriaMetrics — внутренний адрес; через прокси запросы висели и падали 502.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def query(expr: str, at: int):
    url = f"{VM}/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": at})
    with OPENER.open(url, timeout=90) as r:
        res = json.load(r)["data"]["result"]
    return res


def scalar(expr: str, at: int):
    res = query(expr, at)
    return float(res[0]["value"][1]) if res else None


def window_stats(start: str, end: str) -> dict:
    t0, t1 = ts(start), ts(end)
    rng = f"[{t1 - t0}s]"
    out = {"start": start, "end": end, "hours": round((t1 - t0) / 3600, 1)}

    out["requests"] = scalar(f"sum(increase(vllm:request_success_total{SEL}{rng}))", t1)
    out["by_finish_reason"] = {
        r["metric"].get("finished_reason", "?"): round(float(r["value"][1]))
        for r in query(f"sum by (finished_reason) (increase(vllm:request_success_total{SEL}{rng}))", t1)
    }
    out["prompt_tokens_total"] = scalar(f"sum(increase(vllm:prompt_tokens_total{SEL}{rng}))", t1)
    out["gen_tokens_total"] = scalar(f"sum(increase(vllm:generation_tokens_total{SEL}{rng}))", t1)
    hits = scalar(f"sum(increase(vllm:prefix_cache_hits_total{SEL}{rng}))", t1)
    queries = scalar(f"sum(increase(vllm:prefix_cache_queries_total{SEL}{rng}))", t1)
    out["prefix_cache_hit_rate"] = round(hits / queries, 4) if hits is not None and queries else None
    out["preemptions"] = scalar(f"sum(increase(vllm:num_preemptions_total{SEL}{rng}))", t1)
    out["max_running"] = scalar(f"max_over_time(sum(vllm:num_requests_running{SEL}){rng})", t1)
    out["max_waiting"] = scalar(f"max_over_time(sum(vllm:num_requests_waiting{SEL}){rng})", t1)

    for key, m in HISTOGRAMS.items():
        s = scalar(f"sum(increase({m}_sum{SEL}{rng}))", t1)
        c = scalar(f"sum(increase({m}_count{SEL}{rng}))", t1)
        row = {"count": round(c) if c else 0, "mean": round(s / c, 4) if s is not None and c else None}
        for q in (0.5, 0.95, 0.99):
            row[f"p{int(q * 100)}"] = scalar(
                f"histogram_quantile({q}, sum by (le) (increase({m}_bucket{SEL}{rng})))", t1)
            if row[f"p{int(q * 100)}"] is not None:
                row[f"p{int(q * 100)}"] = round(row[f"p{int(q * 100)}"], 4)
        out[key] = row
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="куда сохранить JSON")
    args = ap.parse_args()
    result = {
        "source": VM,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "windows": {name: window_stats(*w) for name, w in WINDOWS.items()},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
