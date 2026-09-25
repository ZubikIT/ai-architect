#!/usr/bin/env python3
"""Боевые метрики шлюза LiteLLM — то, что видит клиент платформы, а не движок.

VictoriaMetrics кластера Talos доступна только изнутри, поэтому сначала:

    kubectl -n monitoring port-forward svc/vmsingle-vm-k8s-stack-victoria-metrics-k8s-stack 18429:8429
    python3 litellm_prod_stats.py --out litellm-prod-2026-09-25.json

Серии `litellm_*` пишет коллбек `prometheus` шлюза с 21.09.2026 (devops/argocd
88e5b34), скрейп — по подам (две реплики, `sum` складывает их реестры).

В отличие от метрик vLLM здесь есть **кто** (`api_key_alias`) и **куда**
(`requested_model`, `api_provider`). Свой контур — метка `model="zubr"`: под неё
попадают и `zubr`, и `zubr-vision`, и синонимы, потому что все они маршрутизированы
на `openai/zubr` (vLLM на GPU-боксе). По `api_provider="openai"` фильтровать нельзя:
туда же попадают сторонние OpenAI-совместимые провайдеры (`onefast/…`, `yandex/…`).

Кеш шлюза отвечает без вызова модели, поэтому `total_s` смешивает кешированные и
настоящие ответы; время модели — `llm_api_s` и `ttft_s`, они пишутся только для
настоящих вызовов.
Клиенты, которые ходят в бокс мимо шлюза (чат-боты, Open WebUI), сюда не
попадают — их видно только в метриках vLLM.

Средние (sum/count) точные, перцентили — интерполяция внутри корзин.
"""
import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VM = os.environ.get("VM", "http://127.0.0.1:18429")
START = os.environ.get("START", "2026-09-21T09:00:00Z")   # первая серия litellm_*
END = os.environ.get("END", "2026-09-25T18:00:00Z")       # до прогона стенда 25.09

# Мимо системного прокси macOS — см. vllm_prod_stats.py.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

HISTOGRAMS = {
    "total_s": "litellm_request_total_latency_metric",      # весь запрос через шлюз
    "llm_api_s": "litellm_llm_api_latency_metric",          # вызов модели
    "ttft_s": "litellm_llm_api_time_to_first_token_metric",  # только стриминг
    "overhead_s": "litellm_overhead_latency_metric",        # собственные расходы шлюза
}
COUNTERS = {
    "input_tokens": "litellm_input_tokens_metric_total",
    "output_tokens": "litellm_output_tokens_metric_total",
    "reasoning_tokens": "litellm_output_reasoning_tokens_metric_total",
    "cache_hits": "litellm_cache_hits_metric_total",
}
OWN = '{model="zubr"}'


def ts(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def query(expr, at):
    url = f"{VM}/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": at})
    with OPENER.open(url, timeout=90) as r:
        return json.load(r)["data"]["result"]


def grouped(expr, at, by):
    out = {}
    for r in query(expr, at):
        key = " / ".join(r["metric"].get(b, "—") for b in by)
        out[key] = float(r["value"][1])
    return out


def stats(by, sel=""):
    t0, t1 = ts(START), ts(END)
    rng = f"[{t1 - t0}s]"
    g = ",".join(by)
    rows = {}
    for key, m in HISTOGRAMS.items():
        cnt = grouped(f"sum by ({g}) (increase({m}_count{sel}{rng}))", t1, by)
        sm = grouped(f"sum by ({g}) (increase({m}_sum{sel}{rng}))", t1, by)
        p50 = grouped(f"histogram_quantile(0.5, sum by ({g}, le) (increase({m}_bucket{sel}{rng})))", t1, by)
        p95 = grouped(f"histogram_quantile(0.95, sum by ({g}, le) (increase({m}_bucket{sel}{rng})))", t1, by)
        for k, c in cnt.items():
            if c < 0.5:
                continue
            rows.setdefault(k, {})[key] = {
                "count": round(c), "mean": round(sm.get(k, 0) / c, 3),
                "p50": round(p50[k], 3) if k in p50 else None,
                "p95": round(p95[k], 3) if k in p95 else None,
            }
    for key, m in COUNTERS.items():
        for k, v in grouped(f"sum by ({g}) (increase({m}{sel}{rng}))", t1, by).items():
            if k in rows:
                rows[k][key] = round(v)
    return dict(sorted(rows.items(), key=lambda kv: -kv[1].get("total_s", {}).get("count", 0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    result = {
        "source": VM, "start": START, "end": END,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "by_provider": stats(["api_provider"]),
        "own_contour_by_model": stats(["requested_model"], OWN),
        "own_contour_by_key": stats(["api_key_alias"], OWN),
        "cloud_top_models": dict(list(stats(["requested_model"], '{api_provider="openrouter"}').items())[:6]),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
