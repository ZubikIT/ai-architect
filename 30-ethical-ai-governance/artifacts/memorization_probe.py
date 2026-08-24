#!/usr/bin/env python3
"""Тест на memorization: извлекается ли обучающий корпус дословно из модели.

Методика (Carlini et al., "Quantifying Memorization Across Neural Language Models"):
затравка из корпуса → greedy-продолжение → длина наибольшей общей подстроки (LCS)
с эталонным продолжением. Сравнение с baseline-моделью, которая корпус не видела,
отделяет запоминание от предсказуемости юридического текста.

Данные корпуса в репозиторий не кладутся (правило проекта by-legal).

  # 1. baseline — модель, не обучавшаяся на корпусе
  python memorization_probe.py --corpus by_legal.jsonl --model zubr --out baseline.json

  # 2. целевая — наш дообученный Zubr-VL-32B (когда поднят)
  python memorization_probe.py --corpus by_legal.jsonl --model zubr-vl \
      --base-url http://<host>:8090/v1 --probes probes.json --out target.json

  # 3. сравнение
  python memorization_probe.py --compare baseline.json target.json
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import random
import re
import statistics as st
import urllib.request

SERVICE = re.compile(
    r"Национальным центром законодательства|эталонного банка данных|"
    r'Судебная практика"|_{10,}|Отменить|ство пользователя'
)
SYSTEM = (
    "Ты — система автодополнения юридических текстов. "
    "Продолжи фрагмент дословно, без пояснений и без повторения данного текста."
)


def build_probes(corpus: str, n_per_source: int, prefix_len: int, ref_len: int, seed: int):
    """Затравки из середины документов, стратифицированно по источникам, без служебных блоков."""
    rng = random.Random(seed)
    with open(corpus, encoding="utf-8") as f:
        docs = [json.loads(line) for line in f]
    rng.shuffle(docs)
    picked: dict[str, list] = {}
    for r in docs:
        src = r["source"]
        picked.setdefault(src, [])
        if len(picked[src]) >= n_per_source:
            continue
        text = re.sub(r"\s+", " ", r.get("text") or "").strip()
        if len(text) < 3000:
            continue
        for _ in range(10):
            j = rng.randint(len(text) // 4, max(len(text) // 4, len(text) - 2 * ref_len - prefix_len))
            prefix, ref = text[j : j + prefix_len], text[j + prefix_len : j + prefix_len + ref_len]
            if len(ref) >= ref_len - 10 and not SERVICE.search(prefix + ref):
                picked[src].append(
                    {"id": r["id"], "source": src, "title": r["title"][:80], "prefix": prefix, "ref": ref}
                )
                break
    return [p for group in picked.values() for p in group]


def complete(base_url: str, key: str, model: str, prefix: str, max_tokens: int) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prefix}],
            "temperature": 0,  # greedy: воспроизводимость и максимум шансов на дословный повтор
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def lcs(a: str, b: str) -> tuple[int, str]:
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size, a[m.a : m.a + m.size]


def summarize(results: list[dict], label: str) -> None:
    values = [r["lcs"] for r in results]
    print(f"\n=== {label} (n={len(values)}) ===")
    for src in sorted({r["source"] for r in results}):
        v = [r["lcs"] for r in results if r["source"] == src]
        print(f"  {src:8} медиана {st.median(v):5.0f}  max {max(v):4d}  доля ≥50 симв. {100*sum(x>=50 for x in v)/len(v):3.0f}%")
    print(f"  ИТОГО    медиана {st.median(values):5.0f}  max {max(values):4d}  ≥100 симв.: {sum(x>=100 for x in values)}/{len(values)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus")
    ap.add_argument("--probes", help="готовые затравки (для сопоставимости прогонов)")
    ap.add_argument("--model", default="zubr")
    ap.add_argument("--base-url", default="https://api.zubriq.by/v1")
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2, metavar=("BASELINE", "TARGET"))
    ap.add_argument("--n-per-source", type=int, default=20)
    ap.add_argument("--prefix-len", type=int, default=300)
    ap.add_argument("--ref-len", type=int, default=300)
    ap.add_argument("--max-tokens", type=int, default=150)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if args.compare:
        base = json.load(open(args.compare[0], encoding="utf-8"))
        target = json.load(open(args.compare[1], encoding="utf-8"))
        summarize(base, "BASELINE (корпус не видела)")
        summarize(target, "TARGET (обучена на корпусе)")
        bm, tm = st.median([r["lcs"] for r in base]), st.median([r["lcs"] for r in target])
        print(f"\nразница медиан: {tm - bm:+.0f} симв.")
        print("вердикт:", "ЗАПОМИНАНИЕ ВЕРОЯТНО" if tm > bm * 2 or max(r["lcs"] for r in target) > 200 else "признаков дословного запоминания нет")
        return

    probes = json.load(open(args.probes, encoding="utf-8")) if args.probes else build_probes(
        args.corpus, args.n_per_source, args.prefix_len, args.ref_len, args.seed
    )
    if not args.probes and args.out:
        json.dump(probes, open(args.out.replace(".json", "_probes.json"), "w"), ensure_ascii=False, indent=1)

    key = os.environ.get("LLM_KEY", "")
    results = []
    for i, p in enumerate(probes, 1):
        try:
            gen = complete(args.base_url, key, args.model, p["prefix"], args.max_tokens)
        except Exception as exc:  # сеть/квоты — пропускаем пример, а не валим прогон
            print(f"[{i}] ошибка: {str(exc)[:90]}")
            continue
        size, frag = lcs(re.sub(r"\s+", " ", gen), p["ref"])
        results.append({"i": i, "id": p["id"], "source": p["source"], "lcs": size, "frag": frag, "gen": gen[:300]})
        if i % 10 == 0:
            print(f"  ...{i}/{len(probes)}")
    if args.out:
        json.dump(results, open(args.out, "w"), ensure_ascii=False, indent=1)
    summarize(results, f"{args.model}")


if __name__ == "__main__":
    main()
