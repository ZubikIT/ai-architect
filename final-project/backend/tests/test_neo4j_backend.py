"""Боевой графовый бэкенд на живой Neo4j: паритет с in-memory и глубина обхода.

Запускается только при заданном `NEO4J_URI` (`docker compose --profile core up -d`),
иначе пропускается — офлайн-набор тестов обязан оставаться запускаемым без стека.

Зачем эти тесты вообще нужны. In-memory-хранилище — это демо и тесты, Neo4j —
то, что поедет в контур. Пока их семантика сверялась только глазами, боевой путь
тихо расходился с проверенным: одиночный запрос обхода не набирал глубину,
заявленную в `SUFLER_GRAPH_HOPS`, и не знал направления «seed сам отменяет пункт».
На демо-корпусе оба расхождения не проявлялись — их видно только так.
"""
import os

import pytest

from sufler.graph import CANCELLED_BY, CANCELS, InMemoryGraphStore, Neo4jGraphStore
from sufler.ingest import Chunk, Document

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="нужен живой Neo4j: docker compose --profile core up -d neo4j",
)

CHAIN_CODES = ["ЛПА-Т1", "ЛПА-Т2", "ЛПА-Т3"]


@pytest.fixture(scope="module")
def neo_store():
    store = Neo4jGraphStore(os.environ["NEO4J_URI"],
                            os.getenv("NEO4J_USER", "neo4j"),
                            os.environ["NEO4J_PASSWORD"])
    yield store
    store.close()


@pytest.fixture
def chain(neo_store):
    """Цепочка отмен: ЛПА-Т3 отменяет ЛПА-Т2, тот — ЛПА-Т1. Два хопа от исходной нормы.

    В демо-корпусе такой цепочки нет: там одна отмена, и глубину обхода на нём
    не проверить. После теста узлы удаляются — граф остаётся чистым для видео-демо
    и для `/graph/stats`.
    """
    docs, chunks = [], []
    for i, code in enumerate(CHAIN_CODES):
        cancels = [(CHAIN_CODES[i - 1], "1")] if i else []
        docs.append(Document(name=f"{code}.md", code=code, title=f"{code}. Тестовая норма",
                             acl=["all"], cancels=cancels))
        chunks.append(Chunk(id=9000 + i, doc=f"{code}.md", section="1. Норма",
                            text=f"Редакция {i + 1}.", acl=["all"], doc_code=code, ordinal="1"))
    neo_store.build(docs, chunks)
    yield docs, chunks, chunks[0]
    # Housekeeping теста, не путь запроса: единственный Cypher вне graph.py.
    with neo_store._driver.session() as s:
        s.run("MATCH (n) WHERE n.code IN $codes OR n.doc_code IN $codes DETACH DELETE n",
              codes=CHAIN_CODES)


def test_hops_walk_the_cancellation_chain(neo_store, chain):
    """Глубина обхода реальна: один хоп — одно звено, два хопа — оба."""
    _, _, seed = chain

    one = neo_store.expand([seed.id], roles=["all"], hops=1)
    assert {e.relation for e in one} == {CANCELS}
    assert len(one) == 1, "первый хоп даёт только отменяющую редакцию"

    two = neo_store.expand([seed.id], roles=["all"], hops=2)
    assert len(two) == 2, "второй хоп обязан достать отмену отмены"


def test_expand_knows_both_directions_of_cancellation(neo_store, chain):
    """От отменяющего пункта виден отменённый: обратное направление ребра не потеряно."""
    _, chunks, _ = chain
    canceller = chunks[1]        # ЛПА-Т2 отменяет ЛПА-Т1 и сам отменён ЛПА-Т3
    rel = {e.relation for e in neo_store.expand([canceller.id], roles=["all"], hops=1)}
    assert CANCELLED_BY in rel, "не найден пункт, отменённый seed'ом"
    assert CANCELS in rel, "не найден пункт, отменяющий seed"


def test_chain_parity_with_in_memory(neo_store, chain):
    """Тот же корпус, тот же обход — тот же результат у обоих бэкендов."""
    docs, chunks, seed = chain
    mem = InMemoryGraphStore()
    mem.build(docs, chunks)

    def shape(store):
        return {(e.chunk_id, e.relation) for e in store.expand([seed.id], ["all"], hops=2)}

    assert shape(neo_store) == shape(mem)


def test_demo_corpus_parity(neo_store, corpus):
    """Паритет на боевом корпусе ЛПА — по каждому чанку как seed, для двух ролей.

    Проверяется и обход, и аннотации: расхождение хотя бы в одном чанке означает,
    что доказательства безопасности, полученные на in-memory, к Neo4j не относятся.
    """
    documents, chunks = corpus
    mem = InMemoryGraphStore()
    mem.build(documents, chunks)
    neo_store.build(documents, chunks)

    for roles in (["all"], ["legal"], ["security"]):
        for c in chunks:
            got = {(e.chunk_id, e.relation) for e in neo_store.expand([c.id], roles, hops=2)}
            want = {(e.chunk_id, e.relation) for e in mem.expand([c.id], roles, hops=2)}
            assert got == want, f"обход разошёлся: чанк {c.id} ({c.doc} · {c.section}), роли {roles}"

        ids = [c.id for c in chunks]
        got_ann = {k: sorted(v) for k, v in neo_store.annotations(ids, roles).items()}
        want_ann = {k: sorted(v) for k, v in mem.annotations(ids, roles).items()}
        assert got_ann == want_ann, f"аннотации разошлись для ролей {roles}"


def test_stats_are_comparable_between_backends(neo_store, corpus):
    """Цифры `/graph/stats` означают одно и то же на обоих путях."""
    documents, chunks = corpus
    mem = InMemoryGraphStore()
    mem.build(documents, chunks)
    neo_store.build(documents, chunks)

    a, b = neo_store.stats(), mem.stats()
    for key in ("nodes", "documents", "edges", "cancels", "references"):
        assert a[key] == b[key], f"расходится показатель {key}: neo4j {a[key]} ≠ in-memory {b[key]}"
