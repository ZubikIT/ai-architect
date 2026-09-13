"""Графовый бэкенд на рекурсивных CTE: паритет со словарной реализацией.

Запускается только при заданном `SUFLER_GRAPH_DSN`
(`docker compose --profile core up -d postgres`), иначе пропускается —
офлайн-набор обязан оставаться запускаемым без стека.

Зачем третий бэкенд и зачем эти тесты. Векторная часть платформы уже живёт в
Postgres, и отдельный Neo4j — это второе stateful-хранилище ради онтологии из
четырёх типов узлов. Выбор делается замером (ADR-0028), а замер имеет смысл
только если бэкенды **семантически одинаковы**: сравнивать быстрый неправильный
обход с медленным правильным незачем.

Паритет здесь уже отработал: первая редакция запроса аннотаций возвращала
отношение как есть, и пометки встали наоборот — действующая редакция
объявлялась отменённой. Глазами это не видно, тестом видно сразу.
"""
import os

import pytest

from sufler.graph import CANCELLED_BY, CANCELS, InMemoryGraphStore, PgGraphStore
from sufler.ingest import Chunk, Document

pytestmark = pytest.mark.skipif(
    not os.getenv("SUFLER_GRAPH_DSN"),
    reason="нужен живой Postgres: docker compose --profile core up -d postgres",
)

CHAIN_CODES = ["ЛПА-П1", "ЛПА-П2", "ЛПА-П3"]


@pytest.fixture(scope="module")
def pg_store():
    store = PgGraphStore(os.environ["SUFLER_GRAPH_DSN"])
    yield store
    store.close()


@pytest.fixture
def chain(pg_store):
    """Цепочка отмен: ЛПА-П3 отменяет ЛПА-П2, тот — ЛПА-П1. Два хопа от исходной нормы.

    Коды и идентификаторы свои (не как у Neo4j-набора): базы разные, но привычка
    делить пространство имён между наборами дешевле, чем разбираться потом, чей
    корпус в базе. На общем Neo4j это уже стоило испорченного прогона.
    """
    docs, chunks = [], []
    for i, code in enumerate(CHAIN_CODES):
        cancels = [(CHAIN_CODES[i - 1], "1")] if i else []
        docs.append(Document(name=f"{code}.md", code=code, title=f"{code}. Тестовая норма",
                             acl=["all"], cancels=cancels))
        chunks.append(Chunk(id=9200 + i, doc=f"{code}.md", section="1. Норма",
                            text=f"Редакция {i + 1}.", acl=["all"], doc_code=code, ordinal="1"))
    pg_store.build(docs, chunks)
    yield docs, chunks, chunks[0]


def test_hops_walk_the_cancellation_chain(pg_store, chain):
    """Глубина обхода реальна: один хоп — одно звено, два хопа — оба.

    У этого бэкенда глубина — параметр рекурсии, а не число round-trip'ов, и
    именно поэтому её надо проверить: ошибка в условии `depth < %(hops)s` даёт
    молча обрезанный обход, а не отказ.
    """
    _, _, seed = chain

    one = pg_store.expand([seed.id], roles=["all"], hops=1)
    assert {e.relation for e in one} == {CANCELS}
    assert len(one) == 1, "первый хоп даёт только отменяющую редакцию"

    two = pg_store.expand([seed.id], roles=["all"], hops=2)
    assert len(two) == 2, "второй хоп обязан достать отмену отмены"


def test_expand_knows_both_directions_of_cancellation(pg_store, chain):
    _, chunks, _ = chain
    canceller = chunks[1]
    rel = {e.relation for e in pg_store.expand([canceller.id], roles=["all"], hops=1)}
    assert CANCELLED_BY in rel, "не найден пункт, отменённый seed'ом"
    assert CANCELS in rel, "не найден пункт, отменяющий seed"


def test_cycle_gives_clean_output(pg_store):
    """Взаимная отмена — не выдумка: два приказа, каждый правит пункт другого.

    Проверяется выдача: обход завершается, чанк не приходит дважды, seed не
    возвращается сам себе.

    Чего этот тест НЕ проверяет — сторож цикла в рекурсии. Проверено мутацией:
    без `NOT n.to_id = ANY(w.path)` он проходит точно так же, потому что дубли
    снимает `DISTINCT ON`, а глубину ограничивает `depth < hops`. Для сторожа
    есть отдельный тест ниже.
    """
    codes = ["ЛПА-Ц1", "ЛПА-Ц2"]
    docs = [Document(name=f"{c}.md", code=c, title=f"{c}. Норма", acl=["all"],
                     cancels=[(codes[1 - i], "1")]) for i, c in enumerate(codes)]
    chunks = [Chunk(id=9300 + i, doc=f"{c}.md", section="1. Норма", text="Текст.",
                    acl=["all"], doc_code=c, ordinal="1") for i, c in enumerate(codes)]
    pg_store.build(docs, chunks)

    out = pg_store.expand([chunks[0].id], roles=["all"], hops=5)
    assert len(out) == len({e.chunk_id for e in out}), "один чанк не должен прийти дважды"
    assert all(e.chunk_id != chunks[0].id for e in out), "seed не возвращается сам себе"


def test_cycle_guard_bounds_the_work(pg_store):
    """Сторож цикла ограничивает промежуточную работу рекурсии.

    На выдаче его не видно вовсе — и именно поэтому он нуждается в собственном
    тесте. Замер на полном графе из семи пунктов (каждый отменяет каждого),
    глубина 6:

        со сторожем    75 973 строки     456 мс
        без сторожа  3 257 437 строк  11 084 мс

    43× по строкам, 24× по времени. Тест намеренно **по времени**: число
    промежуточных строк через публичный интерфейс не видно, а воспроизводить
    здесь SQL запроса значило бы проверять копию, а не оригинал. Бюджет взят с
    девятикратным запасом к хорошему случаю и почти трёхкратным — до плохого.
    """
    import time

    codes = [f"ЛПА-К{i}" for i in range(7)]
    docs = [Document(name=f"{c}.md", code=c, title=f"{c}. Норма", acl=["all"],
                     cancels=[(o, "1") for o in codes if o != c]) for c in codes]
    chunks = [Chunk(id=9400 + i, doc=f"{c}.md", section="1. Норма", text="Текст.",
                    acl=["all"], doc_code=c, ordinal="1") for i, c in enumerate(codes)]
    pg_store.build(docs, chunks)

    t0 = time.perf_counter()
    out = pg_store.expand([chunks[0].id], roles=["all"], hops=6)
    elapsed = time.perf_counter() - t0

    assert len(out) == 6, "все прочие пункты достижимы за один хоп"
    assert elapsed < 4.0, (
        f"обход занял {elapsed:.1f} с — похоже, сторож цикла снят: "
        "без него тот же запрос давал 11 с")


def test_demo_corpus_parity(pg_store, corpus):
    """Паритет на корпусе ЛПА — по каждому чанку как seed, для трёх наборов ролей.

    Проверяется и обход, и аннотации: расхождение хотя бы в одном чанке означает,
    что доказательства безопасности, полученные на in-memory, к этому бэкенду не
    относятся.
    """
    documents, chunks = corpus
    mem = InMemoryGraphStore()
    mem.build(documents, chunks)
    pg_store.build(documents, chunks)

    for roles in (["all"], ["legal"], ["security"]):
        for c in chunks:
            got = {(e.chunk_id, e.relation) for e in pg_store.expand([c.id], roles, hops=2)}
            want = {(e.chunk_id, e.relation) for e in mem.expand([c.id], roles, hops=2)}
            assert got == want, f"обход разошёлся: чанк {c.id} ({c.doc} · {c.section}), роли {roles}"

        ids = [c.id for c in chunks]
        got_ann = {k: sorted(v) for k, v in pg_store.annotations(ids, roles).items()}
        want_ann = {k: sorted(v) for k, v in mem.annotations(ids, roles).items()}
        assert got_ann == want_ann, f"аннотации разошлись для ролей {roles}"


def test_closed_node_is_not_a_transit(pg_store, corpus):
    """ACL стоит внутри рекурсии, а не на итоговой выборке.

    Разница видна только так: при проверке на выходе до узла за закрытым
    документом можно доехать транзитом через него же, и наружу он выйдет
    «законно» — по своей собственной метке.
    """
    documents, chunks = corpus
    pg_store.build(documents, chunks)
    closed = {c.id for c in chunks if c.doc_code == "ЛПА-03"}
    assert closed, "в корпусе должен быть закрытый документ"

    for c in chunks:
        reached = {e.chunk_id for e in pg_store.expand([c.id], ["all"], hops=3)}
        assert not (reached & closed), f"чанк {c.id} дотянулся до закрытого документа"
