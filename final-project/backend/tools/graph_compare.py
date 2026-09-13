"""Сравнение графовых бэкендов: время обхода и совпадение выдачи.

Один хост, один корпус, один и тот же вызов. Меряется то, что зависит от
хранилища: обход и аннотации. Векторная часть и реранк в обоих случаях общие и
в замер не входят — иначе сравнивались бы не хранилища, а пайплайн целиком.
"""
import os, statistics, sys, time; sys.path.insert(0, ".")
from sufler.config import Settings
from sufler.graph import InMemoryGraphStore, Neo4jGraphStore, PgGraphStore
from sufler.ingest import chunk_documents, load_documents

cfg = Settings()
docs, chunks = chunk_documents(load_documents(cfg.data_dir))
seeds = [c.id for c in chunks]
ROLES = ["legal"]
REPS = 30

stores = {"in-memory": InMemoryGraphStore()}
if os.getenv("NEO4J_URI"):
    stores["neo4j"] = Neo4jGraphStore(os.environ["NEO4J_URI"], os.getenv("NEO4J_USER", "neo4j"),
                                      os.environ["NEO4J_PASSWORD"])
if os.getenv("SUFLER_GRAPH_DSN"):
    stores["postgres"] = PgGraphStore(os.environ["SUFLER_GRAPH_DSN"])

for name, st in stores.items():
    t0 = time.perf_counter()
    st.build(docs, chunks)
    st.build_seconds = time.perf_counter() - t0

def bench(fn, reps=REPS):
    fn()                                          # прогрев соединения
    ts = [(lambda t0=time.perf_counter(): (fn(), time.perf_counter() - t0)[1])() for _ in range(reps)]
    return statistics.median(ts) * 1000, statistics.quantiles(ts, n=20)[-1] * 1000

print(f"корпус: {len(chunks)} чанков, {len(docs)} документов · роли {ROLES} · {REPS} повторов\n")
print(f"{'бэкенд':12} {'build':>9} {'expand h=1':>22} {'expand h=2':>22} {'annotations':>22}")
rows = {}
for name, st in stores.items():
    e1 = bench(lambda st=st: st.expand(seeds[:5], ROLES, hops=1, limit=10))
    e2 = bench(lambda st=st: st.expand(seeds[:5], ROLES, hops=2, limit=10))
    an = bench(lambda st=st: st.annotations(seeds, ROLES))
    rows[name] = (e1, e2, an)
    print(f"{name:12} {st.build_seconds*1000:7.0f} мс "
          f"{e1[0]:9.2f} / p95 {e1[1]:6.2f} мс {e2[0]:9.2f} / p95 {e2[1]:6.2f} мс "
          f"{an[0]:9.2f} / p95 {an[1]:6.2f} мс")

print("\nсовпадение выдачи (обход + аннотации), все чанки × 3 набора ролей:")
mem = stores["in-memory"]
for name, st in stores.items():
    if name == "in-memory":
        continue
    bad = 0
    for roles in (["all"], ["legal"], ["security"]):
        for sid in seeds:
            a = {(e.chunk_id, e.relation) for e in mem.expand([sid], roles, hops=2)}
            b = {(e.chunk_id, e.relation) for e in st.expand([sid], roles, hops=2)}
            bad += (a != b)
        am = {k: sorted(v) for k, v in mem.annotations(seeds, roles).items()}
        bm = {k: sorted(v) for k, v in st.annotations(seeds, roles).items()}
        bad += (am != bm)
    print(f"  {name:12} расхождений: {bad}")

print("\nround-trip'ов к БД на один обход:")
print("  neo4j     hops (запрос на каждый шаг фронтира — Cypher не принимает *1..$hops параметром)")
print("  postgres  1 (глубина — параметр рекурсии)")
for st in stores.values():
    st.close()
