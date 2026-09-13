"""Где проявляется разница «обход одним запросом» против «запрос на каждый хоп».

На демо-корпусе цепочка отмен одна и в один хоп, поэтому фронтир Neo4j пустеет
сразу и лишних round-trip'ов не делает. Строим цепочку заведомо глубокую —
ЛПА-Г1 ← ЛПА-Г2 ← … — и меряем обход по глубине.
"""
import os, statistics, sys, time; sys.path.insert(0, ".")
from sufler.graph import Neo4jGraphStore, PgGraphStore
from sufler.ingest import Chunk, Document

DEPTH = 12
codes = [f"ЛПА-Г{i}" for i in range(DEPTH)]
docs = [Document(name=f"{c}.md", code=c, title=f"{c}. Норма", acl=["all"],
                 cancels=([(codes[i - 1], "1")] if i else [])) for i, c in enumerate(codes)]
chunks = [Chunk(id=9500 + i, doc=f"{c}.md", section="1. Норма", text=f"Редакция {i+1}.",
                acl=["all"], doc_code=c, ordinal="1") for i, c in enumerate(codes)]

stores = {}
if os.getenv("NEO4J_URI"):
    stores["neo4j"] = Neo4jGraphStore(os.environ["NEO4J_URI"], "neo4j", os.environ["NEO4J_PASSWORD"])
if os.getenv("SUFLER_GRAPH_DSN"):
    stores["postgres"] = PgGraphStore(os.environ["SUFLER_GRAPH_DSN"])
for st in stores.values():
    st.build(docs, chunks)

seed = chunks[0].id
print(f"цепочка отмен глубиной {DEPTH}, seed — исходная норма\n")
print(f"{'hops':>5} " + " ".join(f"{n:>22}" for n in stores) + "   найдено")
for hops in (1, 2, 4, 6, 8, 11):
    cells, found = [], None
    for name, st in stores.items():
        st.expand([seed], ["all"], hops=hops, limit=50)
        ts = []
        for _ in range(15):
            t0 = time.perf_counter()
            out = st.expand([seed], ["all"], hops=hops, limit=50)
            ts.append(time.perf_counter() - t0)
        cells.append(f"{statistics.median(ts)*1000:9.2f} мс")
        found = len(out) if found is None else found
        assert len(out) == found, f"бэкенды нашли разное: {name}"
    print(f"{hops:>5} " + " ".join(f"{c:>22}" for c in cells) + f"   {found}")

# уборка за собой: инстанс общий
if "neo4j" in stores:
    with stores["neo4j"]._driver.session() as s:
        s.run("MATCH (n) WHERE n.code IN $c OR n.doc_code IN $c DETACH DELETE n", c=codes)
for st in stores.values():
    st.close()
