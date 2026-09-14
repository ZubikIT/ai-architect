#!/usr/bin/env python3
"""Граф ссылок на РЕАЛЬНОМ корпусе НПА — 25 кодексов РБ, а не на демо-ЛПА.

Зачем. ADR-0028 оставил открытым пункт: «Масштаб не проверен. 19 чанков — это не
корпус. На НПА рекурсивный CTE придётся мерить заново». Здесь он меряется: граф
строится на 7 284 статьях боевого корпуса `zubriq-legal-corpus` и грузится в тот
же `PgGraphStore`, что и демо.

Что меряется:
  * плотность связей — сколько рёбер даёт корпус правилами, без модели;
  * время обхода по глубине — то, ради чего в ADR-0028 выбран рекурсивный CTE;
  * достижимость — насколько граф связен, а не рассыпан на пары.

    SP=<каталог с *_articles.jsonl> python -m tools.npa_graph --report

Корпус тянется из MinIO (`zubriq-legal-corpus`) учёткой kb-graph из Vault
`secret/minio/kb-graph`, либо берётся из уже скачанного каталога.
"""
import argparse
import json
import os
import pathlib
import re
import time
from collections import Counter, defaultdict

# «в соответствии со статьёй 164 настоящего Кодекса», «статьи 12 и 14»
ARTICLE_REF = re.compile(r"стат(?:ья|ьи|ье|ьей|ьёй|ью|ей|ей)\s+(\d+(?:[.\-]\d+)*)", re.I)
# ссылка наружу: «в соответствии с Гражданским кодексом»
FOREIGN_CODE = re.compile(
    r"(Гражданск|Уголовн|Труд|Налогов|Жилищн|Земельн|Банковск|Бюджетн|Воздушн|"
    r"Водн|Лесн|Избирательн|Уголовно-процессуальн|Гражданск\w+ процессуальн)\w*\s+кодекс",
    re.I)
# отменённый ПУНКТ внутри действующей статьи: «1.48. исключен;»
INNER_REPEALED = re.compile(r"^\s*(\d+(?:\.\d+)*)\.\s*(?:исключен[аоы]?|утратил[аои]?\s+силу)\s*[;.]",
                            re.I | re.M)

SHORT = {
    "konst": "Конституция", "bk": "БК", "bud": "БюдК", "gk": "ГК", "gpk": "ГПК",
    "izb": "ИК", "jk": "ЖК", "koap": "КоАП", "kobs": "КоБС", "ktm": "КТМ",
    "kult": "КоК", "kvvt": "КВВТ", "lk": "ЛК", "nedra": "КоН", "nk1": "НК-1",
    "nk2": "НК-2", "obr": "КоО", "pikoap": "ПИКоАП", "sud": "КоСС", "tk": "ТК",
    "uik": "УИК", "uk": "УК", "upk": "УПК", "vodk": "ВК", "vozk": "ВозК", "zk": "ЗК",
}


def load(corpus_dir):
    """→ {slug: {"meta": …, "articles": [{article, title, text}, …]}}"""
    out = {}
    for path in sorted(pathlib.Path(corpus_dir).glob("*_articles.jsonl")):
        slug = path.stem.replace("_articles", "")
        meta, arts = {}, []
        for line in open(path, encoding="utf-8"):
            rec = json.loads(line)
            if "_meta" in rec:
                meta = rec["_meta"]
            else:
                arts.append(rec)
        out[slug] = {"meta": meta, "articles": arts}
    if not out:
        raise SystemExit(f"нет *_articles.jsonl в {corpus_dir}")
    return out


def build_edges(corpus):
    """Рёбра правилами: ссылка внутри кодекса и упоминание чужого кодекса.

    Ссылка «статья N» без уточнения кодекса по правилам законодательной техники
    означает статью ЭТОГО же кодекса, поэтому цель ищется внутри своего слага.
    Ссылка, у которой рядом назван другой кодекс, ведёт на карточку того кодекса,
    а не на его статью: номер в такой конструкции относится к чужой нумерации и
    без разбора конкретной формулировки не разрешается.
    """
    index = {(slug, str(a["article"])): a for slug, d in corpus.items() for a in d["articles"]}
    edges, dangling, foreign, repealed = [], 0, 0, 0
    for slug, d in corpus.items():
        for a in d["articles"]:
            src = (slug, str(a["article"]))
            text = f'{a.get("title") or ""}\n{a.get("text") or ""}'
            repealed += len(INNER_REPEALED.findall(text))
            for m in ARTICLE_REF.finditer(text):
                target = m.group(1)
                window = text[max(0, m.start() - 70):m.end() + 70]
                if FOREIGN_CODE.search(window):
                    foreign += 1
                    continue
                dst = (slug, target)
                if dst == src:
                    continue
                if dst in index:
                    edges.append((src, dst))
                else:
                    dangling += 1
    uniq = sorted(set(edges))
    return uniq, {"index": index, "dangling": dangling,
                  "foreign": foreign, "inner_repealed": repealed,
                  "duplicates": len(edges) - len(uniq)}


def report(corpus, edges, stats):
    arts = sum(len(d["articles"]) for d in corpus.values())
    out_deg = Counter(s for s, _ in edges)
    in_deg = Counter(t for _, t in edges)
    adj = defaultdict(list)
    for s, t in edges:
        adj[s].append(t)

    print(f"\nКОРПУС: {len(corpus)} кодексов, {arts} статей")
    print(f"РЁБРА:  {len(edges)} уникальных ссылок «статья N» "
          f"(дублей схлопнуто {stats['duplicates']})")
    print(f"        {len(out_deg)} статей ссылаются, {len(in_deg)} статей цитируются")
    print(f"        покрытие графом: {len(set(out_deg) | set(in_deg)) / arts:.1%} статей")
    print(f"ОТБРОШЕНО: {stats['foreign']} ссылок на чужой кодекс (номер в чужой нумерации), "
          f"{stats['dangling']} — на несуществующую статью")
    print(f"ОТМЕНЁННЫХ ПУНКТОВ внутри действующих статей: {stats['inner_repealed']}")

    print("\nсамые цитируемые статьи:")
    for (slug, num), n in in_deg.most_common(5):
        title = stats["index"][(slug, num)].get("title", "")[:52]
        print(f"   {SHORT.get(slug, slug):9s} ст.{num:<7s} ← {n:3d}  {title}")

    # достижимость: сколько узлов видно за k хопов от самых связных
    print("\nдостижимость обходом (BFS от 200 самых ссылающихся статей):")
    seeds = [s for s, _ in out_deg.most_common(200)]
    for hops in (1, 2, 3, 5):
        seen = set(seeds)
        frontier = set(seeds)
        for _ in range(hops):
            nxt = {t for f in frontier for t in adj.get(f, ())} - seen
            seen |= nxt
            frontier = nxt
            if not frontier:
                break
        print(f"   {hops} хоп(а): {len(seen)} узлов")
    return {"articles": arts, "edges": len(edges),
            "linked_share": len(set(out_deg) | set(in_deg)) / arts}


def to_store_model(corpus, edges):
    """Корпус НПА → сущности `sufler.ingest`, чтобы граф лёг в тот же PgGraphStore.

    Документ = кодекс, чанк = статья, ordinal = её номер. ACL у всего корпуса
    открытый: кодексы публичны, закрытых норм в нём нет — разграничение прав
    проверяется на демо-ЛПА, где закрытый документ есть по построению.
    """
    from sufler.ingest import Chunk, Document

    docs, chunks, ids = [], [], {}
    for slug, d in corpus.items():
        code = SHORT.get(slug, slug.upper())
        docs.append(Document(name=f"{slug}_articles.jsonl", code=code,
                             title=d["meta"].get("code", code), acl=["all"]))
        for a in d["articles"]:
            cid = len(chunks) + 1
            ids[(slug, str(a["article"]))] = cid
            chunks.append(Chunk(
                id=cid, doc=f"{slug}_articles.jsonl",
                section=f'Статья {a["article"]}. {a.get("title") or ""}'.strip(),
                text=a.get("text") or "", acl=["all"], doc_code=code,
                ordinal=str(a["article"]), doc_title=d["meta"].get("short", code),
                references=[]))
    # Рёбра кладём напрямую: derive_edges() умеет только формат ЛПА.
    rows = [(ids[s], "ССЫЛАЕТСЯ_НА", ids[t], chunks[ids[t] - 1].doc_code,
             chunks[ids[t] - 1].ordinal) for s, t in edges]
    return docs, chunks, rows


def load_pg(dsn, docs, chunks, rows):
    """Грузит корпус и рёбра в схему PgGraphStore, минуя derive_edges()."""
    import psycopg
    from sufler.graph import PgGraphStore

    conn = psycopg.connect(dsn, autocommit=True)
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        for stmt in PgGraphStore.SCHEMA:
            cur.execute(stmt)
        cur.execute(PgGraphStore.VISIBLE)
        cur.execute(PgGraphStore.NEIGHBOURS)
        cur.execute("TRUNCATE graph_documents CASCADE")
        cur.executemany(
            "INSERT INTO graph_documents (code, name, title, acl_roles) VALUES (%s,%s,%s,%s)",
            [(d.code, d.name, d.title, list(d.acl)) for d in docs])
        cur.executemany(
            """INSERT INTO graph_chunks (chunk_id, doc_code, section, ordinal, body,
                                         acl_roles, extracted_by, confidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(c.id, c.doc_code, c.section, c.ordinal, c.text, list(c.acl), "text", 1.0)
             for c in chunks])
        cur.executemany(
            "INSERT INTO graph_edges (src, rel, dst_chunk, dst_doc, clause) VALUES (%s,%s,%s,%s,%s)",
            rows)
        cur.execute(PgGraphStore.RESOLVE)
        cur.execute("ANALYZE graph_edges")
        cur.execute("ANALYZE graph_chunks")
    build_s = time.perf_counter() - t0
    print(f"\nв PostgreSQL загружено за {build_s:.1f} с: "
          f"{len(docs)} документов, {len(chunks)} статей, {len(rows)} рёбер")
    return conn


HOPS = (1, 2, 3, 4, 5)


def measure_pg(conn, chunks, rows, repeats=3, timeout_ms=20000):
    """Время обхода по глубине — то, ради чего в ADR-0028 выбран рекурсивный CTE."""
    from sufler.graph import PgGraphStore
    import statistics

    out_deg = Counter(r[0] for r in rows)
    seeds = [cid for cid, _ in out_deg.most_common(10)]
    print(f"\nобход от 10 самых связных статей (медиана из {repeats} прогонов, "
          f"бюджет {timeout_ms} мс):", flush=True)
    print(f"{'hops':>5} {'узлов':>8} {'медиана, мс':>13} {'худшая, мс':>12}")
    results = []
    for hops in HOPS:
        times, found = [], 0
        for _ in range(repeats):
            t0 = time.perf_counter()
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SET statement_timeout = {timeout_ms}")
                    cur.execute(PgGraphStore.EXPAND,
                                {"seeds": seeds, "hops": hops, "roles": ["all"]})
                    found = len(cur.fetchall())
            except Exception as exc:                 # обход не уложился в бюджет
                print(f"{hops:>5} {chr(8212):>8}  прерван по таймауту {timeout_ms} мс "
                      f"({type(exc).__name__})", flush=True)
                return results
            times.append((time.perf_counter() - t0) * 1000)
        med, worst = statistics.median(times), max(times)
        print(f"{hops:>5} {found:>8} {med:>13.1f} {worst:>12.1f}", flush=True)
        results.append((hops, found, med))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.environ.get("SP", "") + "/corpus")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--pg", help="DSN: загрузить граф в PgGraphStore и замерить обход")
    a = ap.parse_args()

    t0 = time.perf_counter()
    corpus = load(a.corpus)
    edges, stats = build_edges(corpus)
    print(f"построено за {time.perf_counter() - t0:.2f} с")
    report(corpus, edges, stats)

    if a.pg:
        docs, chunks, rows = to_store_model(corpus, edges)
        conn = load_pg(a.pg, docs, chunks, rows)
        measure_pg(conn, chunks, rows)


if __name__ == "__main__":
    main()
