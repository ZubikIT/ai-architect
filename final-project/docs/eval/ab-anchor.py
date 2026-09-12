"""Изолированный A/B якоря статьи на корпусе кодексов РБ.

Тот замер, которого не делал никто. В пилоте платформы 01.08.2026 разрыв
67 % → 89 % объяснили нарезкой с заголовком, но сравнивали ДВЕ СИСТЕМЫ, у
которых одновременно различались размер куска, нарезчик и реализация
hybrid+rerank. Здесь двигается ровно одна переменная: есть заголовок в теле
куска или нет. Всё остальное — нарезка, модели, протокол, golden — одно и то же.

Протокол взят из pilot_vectors/eval.py без изменений:
    вопрос → bge-m3 → top-24 кандидатов → bge-reranker-v2-m3 → top-6
    → номера статей из `name` → hit@1/3/6 против golden.jsonl

`name` в обоих вариантах одинаков и в тело НЕ входит у варианта «без якоря» —
иначе сравнение было бы фиктивным: метрика читает номер из name, а ищем мы по
телу.
"""
import json, os, pathlib, re, sys, time
import numpy as np
import urllib.request

urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

SP = pathlib.Path(os.environ["SP"])
CORPUS = SP / "corpus"
GOLDEN = pathlib.Path("/home/a.zubik/www/artcloud/zubriq/dify/kb/codes/golden.jsonl")
EMB_BASE = os.environ["SUFLER_RERANK_URL"].rstrip("/")
KEY = os.environ["SUFLER_RERANK_API_KEY"]
ART_RE = re.compile(r"Статья\s+(\d+(?:[.-]\d+)*)")
CAND, TOP, TARGET, HARD_MAX = 24, 6, 1500, 2000


def http(url, body, timeout=300):
    req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {KEY}"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def chunks_of(text):                      # дословно из pilot_vectors/chunk.py
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    out, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > TARGET:
            out.append(cur); cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
        while len(cur) > HARD_MAX:
            cut = cur.rfind(". ", 0, HARD_MAX)
            cut = cut + 1 if cut > 200 else HARD_MAX
            out.append(cur[:cut]); cur = cur[cut:].strip()
    if cur:
        out.append(cur)
    return out


def build():
    """→ names + четыре варианта тела куска.

    Разложение якоря на составляющие: он несёт И адрес («КоАП — Статья 339»),
    И название статьи («Хулиганство»). Первое отвечает на вопросы, которые
    адресуют документ; второе — на смысловые, потому что название статьи это
    написанная человеком тематическая метка, часто дословно совпадающая с
    формулировкой вопроса. Что из двух работает — вопрос замера, а не вкуса.
    """
    names, withh, without, only_title, only_addr = [], [], [], [], []
    for path in sorted(CORPUS.glob("*_articles.jsonl")):
        short = path.stem.replace("_articles", "").upper()
        for line in path.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            if "_meta" in d:
                short = d["_meta"].get("short", short); continue
            name = f"{short} — Статья {d['article']}. {d.get('title','')}".strip()
            header = f"{name}\n({d.get('chapter','')})\n\n"
            title = (d.get("title", "") or "").strip()
            addr = f"{short} — Статья {d['article']}"
            for c in chunks_of(d.get("text", "")):
                names.append(name)
                withh.append(header + c)
                without.append(c)
                only_title.append(f"{title}\n\n{c}" if title else c)
                only_addr.append(f"{addr}\n\n{c}")
    return names, withh, without, only_title, only_addr


def embed_all(texts, cache):
    p = SP / cache
    if p.exists():
        return np.load(p)
    vecs, t0 = [], time.time()
    for i in range(0, len(texts), 32):
        d = http(f"{EMB_BASE}/embeddings", {"model": "BAAI/bge-m3", "input": texts[i:i+32]})
        vecs.extend(x["embedding"] for x in d["data"])
        if i % 3200 == 0:
            print(f"    {i}/{len(texts)}  {time.time()-t0:.0f} с", flush=True)
    a = np.asarray(vecs, dtype=np.float32)
    a /= np.linalg.norm(a, axis=1, keepdims=True)
    np.save(p, a)
    return a


def run(label, names, bodies, mat, golden):
    hits = {1: 0, 3: 0, 6: 0}
    misses = []
    for case in golden:
        q = case["q"]
        qv = np.asarray(http(f"{EMB_BASE}/embeddings",
                             {"model": "BAAI/bge-m3", "input": [q]})["data"][0]["embedding"],
                        dtype=np.float32)
        qv /= np.linalg.norm(qv)
        idx = np.argpartition(-(mat @ qv), CAND)[:CAND]
        idx = idx[np.argsort(-(mat[idx] @ qv))]
        order = http(f"{EMB_BASE}/rerank",
                     {"model": "BAAI/bge-reranker-v2-m3", "query": q,
                      "documents": [bodies[i] for i in idx]})["results"]
        order = [r["index"] for r in sorted(order, key=lambda r: -r["relevance_score"])][:TOP]
        arts = [ART_RE.search(names[idx[o]]).group(1) if ART_RE.search(names[idx[o]]) else ""
                for o in order]
        exp = set(case["expect"])
        for k in (1, 3, 6):
            if exp & set(arts[:k]):
                hits[k] += 1
        if not (exp & set(arts[:1])):
            misses.append((q, sorted(exp), arts[:3]))
    n = len(golden)
    print(f"\n== {label}")
    print(f"   hit@1 {hits[1]/n:.1%}  hit@3 {hits[3]/n:.1%}  hit@6 {hits[6]/n:.1%}  ({n} вопросов)")
    return hits, misses


golden = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
names, withh, without, only_title, only_addr = build()
print(f"кусков: {len(names)} · вопросов: {len(golden)}")

print("\nэмбеддинги (с якорем)…", flush=True);  m_with = embed_all(withh, "emb_with.npy")
print("эмбеддинги (без якоря)…", flush=True);  m_without = embed_all(without, "emb_without.npy")

print("эмбеддинги (только название)…", flush=True); m_title = embed_all(only_title, "emb_title.npy")
print("эмбеддинги (только адрес)…", flush=True);     m_addr  = embed_all(only_addr,  "emb_addr.npy")

h1, miss_with    = run("ПОЛНЫЙ ЯКОРЬ: адрес + название (как в проде)", names, withh, m_with, golden)
h2, miss_without = run("БЕЗ ЯКОРЯ", names, without, m_without, golden)
h3, _            = run("ТОЛЬКО НАЗВАНИЕ статьи (без адреса)", names, only_title, m_title, golden)
h4, _            = run("ТОЛЬКО АДРЕС (без названия)", names, only_addr, m_addr, golden)
n = len(golden)
print("\n--- разложение вклада, hit@1:")
print(f"   без якоря              {h2[1]/n:6.1%}   базис")
print(f"   + только название      {h3[1]/n:6.1%}   {(h3[1]-h2[1])/n*100:+.1f} п.п.")
print(f"   + только адрес         {h4[1]/n:6.1%}   {(h4[1]-h2[1])/n*100:+.1f} п.п.")
print(f"   + полный якорь         {h1[1]/n:6.1%}   {(h1[1]-h2[1])/n*100:+.1f} п.п.")

print(f"\nразница hit@1: {(h1[1]-h2[1])/len(golden)*+100:+.1f} п.п.  ({h2[1]} → {h1[1]} из {len(golden)})")
only_without = {q for q,_,_ in miss_without} - {q for q,_,_ in miss_with}
print(f"\nвопросов, которые ломаются ТОЛЬКО без якоря: {len(only_without)}")
for q, exp, got in miss_without:
    if q in only_without:
        print(f"  ждали ст. {','.join(exp):<8} получили {','.join(got[:3]):<18} {q[:60]}")
json.dump({"with": h1, "without": h2, "n": len(golden)},
          open(SP/"ab_anchor.json","w"), ensure_ascii=False, indent=2)
