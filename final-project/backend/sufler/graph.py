"""Граф знаний ЛПА: онтология, построение, обход с ACL-предикатом (ADR-0012, ADR-0013, ADR-0016).

Онтология — 4 типа узлов (рекомендация занятия 32 «начните с 3–4»):
    (:Документ)-[:СОДЕРЖИТ]->(:Чанк)
    (:Чанк)-[:ОТМЕНЯЕТ]->(:Чанк)        отменяющая редакция → отменённый пункт
    (:Чанк)-[:ССЫЛАЕТСЯ_НА]->(:Документ)
    (:Чанк|:Документ)-[:ДОСТУПЕН_РОЛИ]->(:Роль)

Две реализации за одним интерфейсом:
  • InMemoryGraphStore — тесты и офлайн-демо без инфраструктуры;
  • Neo4jGraphStore    — боевой путь; ВЕСЬ Cypher живёт только здесь
    (ADR-0016: единственная точка сборки запросов, ACL-предикат обязателен).

Права проверяются на КАЖДОМ узле пути, а не на финальной выдаче: иначе закрытый
документ утекает через структуру связей — сам факт существования и название.
"""
from dataclasses import dataclass
from typing import Sequence

from .access import allowed

CANCELLED_BY = "ОТМЕНЁН"      # входящее ребро ОТМЕНЯЕТ: seed отменён другим пунктом
CANCELS = "ОТМЕНЯЕТ"          # исходящее: seed сам отменяет другой пункт
REFERENCES = "ССЫЛАЕТСЯ_НА"


@dataclass
class Expansion:
    """Чанк, добытый обходом графа, и причина его появления в контексте."""
    chunk_id: int
    relation: str
    via: str          # человекочитаемый источник связи: «ЛПА-04 · 1. Продолжительность отпуска»


class GraphStore:
    """Интерфейс графового слоя."""

    def build(self, documents, chunks) -> None: raise NotImplementedError
    def expand(self, seed_ids, roles, hops=1, limit=10): raise NotImplementedError
    def annotations(self, chunk_ids, roles): raise NotImplementedError
    def stats(self) -> dict: raise NotImplementedError
    def close(self) -> None: pass


# --------------------------------------------------------------------------- #
#  Общая часть: вычисление рёбер из документов и чанков
# --------------------------------------------------------------------------- #
def derive_edges(documents, chunks):
    """(src_chunk_id, тип, dst_chunk_id|None, dst_doc_code) — правилами, без LLM."""
    by_code = {}
    for ch in chunks:
        by_code.setdefault(ch.doc_code, []).append(ch)

    edges = []
    for doc in documents:
        # отмены объявляет документ, ребро вешаем на его пункт с тем же номером
        for target_code, clause in doc.cancels:
            targets = by_code.get(target_code, [])
            dst = [c for c in targets if c.ordinal == clause] if clause else targets
            if not dst:
                continue
            src_pool = [c for c in by_code.get(doc.code, []) if not clause or c.ordinal == clause]
            src_pool = src_pool or by_code.get(doc.code, [])
            for s in src_pool[:1]:
                for d in dst:
                    edges.append((s.id, CANCELS, d.id, target_code))

    for ch in chunks:
        for code, clause in ch.references:
            if code == ch.doc_code:
                continue
            # None в позиции пункта → ссылка на карточку документа
            edges.append((ch.id, REFERENCES, clause, code))
    return edges


class InMemoryGraphStore(GraphStore):
    """Словарная реализация с той же семантикой ACL, что и Neo4j."""

    def __init__(self):
        self.chunks = {}
        self.doc_acl = {}
        self.edges = []
        self.by_code = {}

    def build(self, documents, chunks):
        self.chunks = {c.id: c for c in chunks}
        self.doc_acl = {d.code: d.acl for d in documents}
        self.by_code = {}
        for c in chunks:
            self.by_code.setdefault(c.doc_code, []).append(c)
        self.edges = derive_edges(documents, chunks)

    def _visible(self, chunk, roles) -> bool:
        # предикат на узле-чанке И на его документе
        return allowed(chunk.acl, roles) and allowed(self.doc_acl.get(chunk.doc_code, []), roles)

    def _label(self, chunk) -> str:
        return f"{chunk.doc_code} · {chunk.section}"

    def expand(self, seed_ids, roles, hops=1, limit=10):
        seen, frontier, out = set(seed_ids), list(seed_ids), []
        for _ in range(max(1, hops)):
            nxt = []
            for sid in frontier:
                for src, rel, dst_id, dst_code in self.edges:
                    cand, relation = None, None
                    # relation описывает роль ДОБАВЛЯЕМОГО чанка, via — seed, к которому он привязан
                    if rel == CANCELS and dst_id == sid:          # найден тот, кто отменяет seed
                        cand, relation = self.chunks.get(src), CANCELS
                    elif rel == CANCELS and src == sid:            # найден пункт, отменённый seed'ом
                        cand, relation = self.chunks.get(dst_id), CANCELLED_BY
                    elif rel == REFERENCES and src == sid:         # ссылка на другой документ
                        pool = self.by_code.get(dst_code, [])
                        clause = dst_id  # в рёбрах-ссылках здесь лежит номер пункта или None
                        targets = ([c for c in pool if c.ordinal == clause] if clause
                                   else [c for c in pool if not c.ordinal][:1])
                        for target in targets:
                            if target.id in seen or not self._visible(target, roles):
                                continue
                            seen.add(target.id)
                            nxt.append(target.id)
                            out.append(Expansion(target.id, REFERENCES, self._label(self.chunks[sid])))
                        continue
                    if cand is None or cand.id in seen:
                        continue
                    if not self._visible(cand, roles):             # закрытый узел пути не существует
                        continue
                    seen.add(cand.id)
                    nxt.append(cand.id)
                    out.append(Expansion(cand.id, relation, self._label(self.chunks[sid])))
            frontier = nxt
            if not frontier:
                break
        return out[:limit]

    def annotations(self, chunk_ids, roles):
        """Статус пунктов, попавших в контекст: отменён / отменяет.

        Нужна отдельно от expand: пункт-модификатор может прийти и векторным
        поиском — тогда обход его не добавляет, но пометка всё равно обязана
        появиться, иначе пользователь получит отменённую норму без оговорки.

        Аннотация показывается, только если отменяющий узел виден субъекту:
        иначе сам факт отмены раскрыл бы существование закрытого документа
        (ADR-0016). Это осознанное ограничение в пользу режима доступа.
        """
        ann = {}
        wanted = set(chunk_ids)
        for src, rel, dst_id, _ in self.edges:
            if rel != CANCELS:   # ссылки статус пункта не меняют
                continue
            src_c, dst_c = self.chunks.get(src), self.chunks.get(dst_id)
            if src_c is None or dst_c is None:
                continue
            if dst_id in wanted and self._visible(src_c, roles):
                ann.setdefault(dst_id, []).append((CANCELLED_BY, self._label(src_c)))
            if src in wanted and self._visible(dst_c, roles):
                ann.setdefault(src, []).append((CANCELS, self._label(dst_c)))
        return ann

    def stats(self):
        cancels = sum(1 for _, rel, _, _ in self.edges if rel == CANCELS)
        return {"backend": "in-memory", "nodes": len(self.chunks),
                "documents": len(self.doc_acl), "edges": len(self.edges),
                "cancels": cancels, "references": len(self.edges) - cancels}


class Neo4jGraphStore(GraphStore):
    """Боевой путь. Cypher — только здесь, только параметризованный.

    Свободный text2Cypher сознательно не поддерживается (ADR-0013): LLM выбирает
    шаблон и заполняет параметры, но не пишет запрос.
    """

    SCHEMA = [
        "CREATE CONSTRAINT doc_code IF NOT EXISTS FOR (d:Документ) REQUIRE d.code IS UNIQUE",
        "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Чанк) REQUIRE c.chunk_id IS UNIQUE",
        "CREATE CONSTRAINT role_name IF NOT EXISTS FOR (r:Роль) REQUIRE r.name IS UNIQUE",
        "CREATE INDEX chunk_acl IF NOT EXISTS FOR (c:Чанк) ON (c.acl_roles)",
    ]

    UPSERT_DOC = """
    MERGE (d:Документ {code: $code})
    SET d.name = $name, d.title = $title, d.acl_roles = $acl
    WITH d UNWIND $acl AS role
      MERGE (r:Роль {name: role})
      MERGE (d)-[:ДОСТУПЕН_РОЛИ]->(r)
    """

    UPSERT_CHUNK = """
    MATCH (d:Документ {code: $doc_code})
    MERGE (c:Чанк {chunk_id: $chunk_id})
    SET c.text = $text, c.section = $section, c.ordinal = $ordinal,
        c.acl_roles = $acl, c.doc_code = $doc_code,
        c.extracted_by = $extracted_by, c.confidence = $confidence
    MERGE (d)-[:СОДЕРЖИТ]->(c)
    WITH c UNWIND $acl AS role
      MERGE (r:Роль {name: role})
      MERGE (c)-[:ДОСТУПЕН_РОЛИ]->(r)
    """

    LINK_CANCELS = """
    MATCH (s:Чанк {chunk_id: $src}), (t:Чанк {chunk_id: $dst})
    MERGE (s)-[e:ОТМЕНЯЕТ]->(t) SET e.derived_by = 'rule'
    """

    LINK_REFERENCES = """
    MATCH (s:Чанк {chunk_id: $src}), (d:Документ {code: $code})
    MERGE (s)-[e:ССЫЛАЕТСЯ_НА {clause: coalesce($clause, '')}]->(d)
    SET e.derived_by = 'rule'
    """

    # ОДИН хоп обхода. ACL-предикат стоит на КАЖДОМ узле пути, включая
    # документ-владелец. Глубина набирается повторным запуском этого же запроса
    # с новым фронтиром (см. `expand`), а не переменной длиной пути: во-первых,
    # Cypher не принимает верхнюю границу `*1..$hops` параметром, и пришлось бы
    # склеивать запрос строкой — ровно то, что ADR-0013 запрещает; во-вторых,
    # пошаговый фронтир даёт ту же семантику, что у InMemoryGraphStore, по
    # построению, а не по совпадению. Цена — `hops` round-trip'ов вместо одного.
    EXPAND = """
    MATCH (seed:Чанк) WHERE seed.chunk_id IN $seeds
    MATCH (seed)<-[:ОТМЕНЯЕТ]-(other:Чанк)<-[:СОДЕРЖИТ]-(od:Документ)
    WHERE ('all' IN other.acl_roles OR any(r IN other.acl_roles WHERE r IN $roles))
      AND ('all' IN od.acl_roles   OR any(r IN od.acl_roles   WHERE r IN $roles))
    RETURN other.chunk_id AS chunk_id, 'ОТМЕНЯЕТ' AS relation,
           seed.doc_code + ' · ' + seed.section AS via
    UNION
    MATCH (seed:Чанк) WHERE seed.chunk_id IN $seeds
    MATCH (seed)-[:ОТМЕНЯЕТ]->(other:Чанк)<-[:СОДЕРЖИТ]-(od:Документ)
    WHERE ('all' IN other.acl_roles OR any(r IN other.acl_roles WHERE r IN $roles))
      AND ('all' IN od.acl_roles   OR any(r IN od.acl_roles   WHERE r IN $roles))
    RETURN other.chunk_id AS chunk_id, 'ОТМЕНЁН' AS relation,
           seed.doc_code + ' · ' + seed.section AS via
    UNION
    MATCH (seed:Чанк) WHERE seed.chunk_id IN $seeds
    MATCH (seed)-[e:ССЫЛАЕТСЯ_НА]->(d:Документ)-[:СОДЕРЖИТ]->(other:Чанк)
    WHERE other.ordinal = e.clause
      AND ('all' IN other.acl_roles OR any(r IN other.acl_roles WHERE r IN $roles))
      AND ('all' IN d.acl_roles     OR any(r IN d.acl_roles     WHERE r IN $roles))
    RETURN other.chunk_id AS chunk_id, 'ССЫЛАЕТСЯ_НА' AS relation,
           seed.doc_code + ' · ' + seed.section AS via
    """

    ANNOTATE = """
    MATCH (c:Чанк) WHERE c.chunk_id IN $ids
    MATCH (c)<-[:ОТМЕНЯЕТ]-(other:Чанк)<-[:СОДЕРЖИТ]-(od:Документ)
    WHERE ('all' IN other.acl_roles OR any(r IN other.acl_roles WHERE r IN $roles))
      AND ('all' IN od.acl_roles   OR any(r IN od.acl_roles   WHERE r IN $roles))
    RETURN c.chunk_id AS chunk_id, 'ОТМЕНЁН' AS relation,
           other.doc_code + ' · ' + other.section AS via
    UNION
    MATCH (c:Чанк) WHERE c.chunk_id IN $ids
    MATCH (c)-[:ОТМЕНЯЕТ]->(other:Чанк)<-[:СОДЕРЖИТ]-(od:Документ)
    WHERE ('all' IN other.acl_roles OR any(r IN other.acl_roles WHERE r IN $roles))
      AND ('all' IN od.acl_roles   OR any(r IN od.acl_roles   WHERE r IN $roles))
    RETURN c.chunk_id AS chunk_id, 'ОТМЕНЯЕТ' AS relation,
           other.doc_code + ' · ' + other.section AS via
    """

    # Считаем ровно то же, что и in-memory: смысловые рёбра онтологии.
    # СОДЕРЖИТ и ДОСТУПЕН_РОЛИ — служебная разводка (структура документа и
    # материализованный ACL), и если сложить их в ту же цифру, показатели двух
    # бэкендов перестают быть сопоставимыми: на демо-корпусе получалось 4 против 52.
    STATS = """
    MATCH (c:Чанк) WITH count(c) AS chunks
    MATCH (d:Документ) WITH chunks, count(d) AS documents
    OPTIONAL MATCH ()-[e:ОТМЕНЯЕТ]->() WITH chunks, documents, count(e) AS cancels
    OPTIONAL MATCH ()-[e:ССЫЛАЕТСЯ_НА]->()
    RETURN chunks, documents, cancels, count(e) AS references
    """

    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase  # импорт здесь: драйвер не нужен в офлайн-режиме
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    # Снос перед пересборкой, ограниченный кодами строящихся документов.
    #
    # `build` на одних MERGE — это не пересборка, а доливка: узлы и рёбра,
    # переставшие следовать из корпуса, остаются навсегда. Найдено сравнением
    # бэкендов: в базе жило ребро ЛПА-03 §4 → ЛПА-03 §1 от прежней редакции
    # правил извлечения связей, обход добавлял по нему лишний пункт, и паритет
    # со словарной реализацией расходился на 12 случаях. Источник истины —
    # корпус (ADR-0012), значит производный граф обязан пересобираться, а не
    # накапливаться.
    #
    # Снос ограничен кодами входящих документов СОЗНАТЕЛЬНО: инстанс Neo4j общий
    # (тот же, где живёт корпус Суфлёра), и `MATCH (n) DETACH DELETE n` вынес бы
    # чужие данные. Цена честно названа в ADR-0028: документ, целиком исчезнувший
    # из корпуса, этим сносом не убирается — его узлы придётся удалять отдельно.
    # У Postgres такой развилки нет, там граф владеет своей базой и `TRUNCATE`
    # безопасен по построению.
    PURGE = """
    MATCH (d:Документ) WHERE d.code IN $codes
    OPTIONAL MATCH (d)-[:СОДЕРЖИТ]->(c:Чанк)
    DETACH DELETE d, c
    """

    def build(self, documents, chunks):
        with self._driver.session() as s:
            for stmt in self.SCHEMA:
                s.run(stmt)
            codes = sorted({d.code for d in documents} | {c.doc_code for c in chunks})
            s.run(self.PURGE, codes=codes)
            for d in documents:
                s.run(self.UPSERT_DOC, code=d.code, name=d.name, title=d.title, acl=list(d.acl))
            for c in chunks:
                s.run(self.UPSERT_CHUNK, chunk_id=c.id, doc_code=c.doc_code, text=c.text,
                      section=c.section, ordinal=c.ordinal, acl=list(c.acl),
                      extracted_by=getattr(c, "extracted_by", "text"),
                      confidence=getattr(c, "confidence", 1.0))
            for src, rel, dst_id, dst_code in derive_edges(documents, chunks):
                if rel == CANCELS:
                    s.run(self.LINK_CANCELS, src=src, dst=dst_id)
                else:
                    s.run(self.LINK_REFERENCES, src=src, code=dst_code, clause=dst_id)

    def expand(self, seed_ids, roles, hops=1, limit=10):
        """Обход фронтиром: `hops` одинаковых запросов, каждый — от узлов,
        найденных на предыдущем шаге. Цепочка отмен (ЛПА-07 отменяет ЛПА-04,
        который отменил ЛПА-01) достаётся только так; одиночный запрос находил
        лишь первое звено, и боевой бэкенд молча терял глубину, заявленную в
        `SUFLER_GRAPH_HOPS`."""
        out, seen, frontier = [], set(seed_ids), list(seed_ids)
        with self._driver.session() as s:
            for _ in range(max(1, hops)):
                if not frontier:
                    break
                rows = s.run(self.EXPAND, seeds=frontier, roles=list(roles))
                nxt = []
                for r in rows:
                    cid = int(r["chunk_id"])
                    if cid in seen:
                        continue
                    seen.add(cid)
                    nxt.append(cid)
                    out.append(Expansion(cid, r["relation"], r["via"]))
                frontier = nxt
        return out[:limit]

    def annotations(self, chunk_ids, roles):
        with self._driver.session() as s:
            rows = s.run(self.ANNOTATE, ids=list(chunk_ids), roles=list(roles))
            ann = {}
            for r in rows:
                ann.setdefault(int(r["chunk_id"]), []).append((r["relation"], r["via"]))
            return ann

    def stats(self):
        with self._driver.session() as s:
            rec = s.run(self.STATS).single()
            if not rec:
                return {}
            return {"backend": "neo4j", "nodes": rec["chunks"], "documents": rec["documents"],
                    "edges": rec["cancels"] + rec["references"],
                    "cancels": rec["cancels"], "references": rec["references"]}

    def close(self):
        self._driver.close()


class PgGraphStore(GraphStore):
    """Граф на рекурсивных CTE в PostgreSQL. SQL — только здесь, только параметризованный.

    Зачем третий бэкенд. Векторная часть платформы уже живёт в Postgres
    (`kb_chunks` в Pigsty), и отдельный Neo4j означает **второе stateful-хранилище
    в кластере ради онтологии из четырёх типов узлов**. Прежде чем платить за него
    бэкапами, мониторингом и дежурством, стоит проверить, не хватает ли той СУБД,
    которая уже есть и уже сопровождается.

    Ключевое отличие от Neo4j-бэкенда — **обход целиком на стороне БД**. У Neo4j
    глубина набирается повторными запросами с новым фронтиром: Cypher не
    принимает верхнюю границу `*1..$hops` параметром, а склеивать запрос строкой
    ADR-0013 запрещает. Здесь глубина — параметр рекурсии, поэтому обход любой
    глубины стоит **один round-trip** вместо `hops`.

    ACL-предикат стоит внутри рекурсивного члена, то есть проверяется на КАЖДОМ
    узле пути, а не на итоговой выборке. Разница не косметическая: во втором
    случае до закрытого документа можно дойти транзитом через него же.
    """

    SCHEMA = [
        """CREATE TABLE IF NOT EXISTS graph_documents (
               code text PRIMARY KEY,
               name text, title text,
               acl_roles text[] NOT NULL DEFAULT '{}')""",
        """CREATE TABLE IF NOT EXISTS graph_chunks (
               chunk_id int PRIMARY KEY,
               doc_code text NOT NULL REFERENCES graph_documents(code) ON DELETE CASCADE,
               section text, ordinal text, body text,
               acl_roles text[] NOT NULL DEFAULT '{}',
               extracted_by text, confidence real)""",
        # Ребро ссылается на пункт НОМЕРОМ, а не идентификатором: «в порядке,
        # установленном ЛПА-03 § 2» — это адрес в тексте, и он переживает
        # перечанкинг, тогда как chunk_id нет.
        """CREATE TABLE IF NOT EXISTS graph_edges (
               src int NOT NULL REFERENCES graph_chunks(chunk_id) ON DELETE CASCADE,
               rel text NOT NULL,
               dst_chunk int REFERENCES graph_chunks(chunk_id) ON DELETE CASCADE,
               dst_doc text,
               clause text,
               derived_by text NOT NULL DEFAULT 'rule')""",
        "CREATE INDEX IF NOT EXISTS graph_edges_src ON graph_edges (src)",
        "CREATE INDEX IF NOT EXISTS graph_edges_dst ON graph_edges (dst_chunk)",
        "CREATE INDEX IF NOT EXISTS graph_chunks_doc ON graph_chunks (doc_code, ordinal)",
    ]

    # Видимость узла: метка на самом чанке И на документе-владельце.
    # Вынесено в функцию, чтобы предикат был ОДИН и в обходе, и в аннотациях:
    # разъехавшиеся копии одного правила доступа — классический способ получить
    # утечку в редком пути.
    VISIBLE = """
    CREATE OR REPLACE FUNCTION graph_visible(chunk_acl text[], doc_acl text[], roles text[])
    RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
      SELECT ('all' = ANY(chunk_acl) OR chunk_acl && roles)
         AND ('all' = ANY(doc_acl)   OR doc_acl   && roles)
    $$
    """

    # Один шаг обхода как представление: от узла фронтира к соседям с причиной
    # появления. Три ветви — те же, что в Cypher и в словарной реализации.
    NEIGHBOURS = """
    CREATE OR REPLACE VIEW graph_neighbours AS
      -- кто-то отменяет наш пункт
      SELECT e.dst_chunk AS from_id, e.src AS to_id, 'ОТМЕНЯЕТ'::text AS relation
        FROM graph_edges e WHERE e.rel = 'ОТМЕНЯЕТ' AND e.dst_chunk IS NOT NULL
      UNION ALL
      -- наш пункт отменяет чей-то
      SELECT e.src AS from_id, e.dst_chunk AS to_id, 'ОТМЕНЁН'::text AS relation
        FROM graph_edges e WHERE e.rel = 'ОТМЕНЯЕТ' AND e.dst_chunk IS NOT NULL
      UNION ALL
      -- ссылка на пункт другого документа по его номеру
      SELECT e.src AS from_id, t.chunk_id AS to_id, 'ССЫЛАЕТСЯ_НА'::text AS relation
        FROM graph_edges e
        JOIN graph_chunks t ON t.doc_code = e.dst_doc
       WHERE e.rel = 'ССЫЛАЕТСЯ_НА'
         AND (t.ordinal = e.clause OR (e.clause IS NULL AND coalesce(t.ordinal, '') = ''))
    """

    # Весь обход — один запрос. depth ограничивает глубину параметром, а не
    # склейкой строки; UNION в рекурсивной части Postgres не поддерживает
    # дедупликацию по подмножеству колонок, поэтому цикл рвём явным NOT IN по
    # уже пройденному пути, а повторы одного чанка снимаем DISTINCT ON снаружи.
    EXPAND = """
    WITH RECURSIVE walk AS (
        SELECT c.chunk_id, 0 AS depth, NULL::text AS relation, NULL::text AS via,
               ARRAY[c.chunk_id] AS path
          FROM graph_chunks c
         WHERE c.chunk_id = ANY(%(seeds)s)
        UNION ALL
        SELECT n.to_id, w.depth + 1, n.relation,
               src.doc_code || ' · ' || src.section,
               w.path || n.to_id
          FROM walk w
          JOIN graph_neighbours n ON n.from_id = w.chunk_id
          JOIN graph_chunks  src  ON src.chunk_id = w.chunk_id
          JOIN graph_chunks  tgt  ON tgt.chunk_id = n.to_id
          JOIN graph_documents td ON td.code = tgt.doc_code
         WHERE w.depth < %(hops)s
           AND NOT n.to_id = ANY(w.path)
           -- ACL на КАЖДОМ узле пути: закрытый узел не существует, и транзит
           -- через него невозможен, потому что рекурсия дальше не идёт.
           AND graph_visible(tgt.acl_roles, td.acl_roles, %(roles)s)
    )
    SELECT DISTINCT ON (chunk_id) chunk_id, relation, via, depth
      FROM walk
     WHERE depth > 0 AND NOT chunk_id = ANY(%(seeds)s)
     ORDER BY chunk_id, depth
    """

    # Отношение здесь ИНВЕРТИРУЕТСЯ относительно представления, и это не
    # опечатка. `graph_neighbours.relation` описывает роль узла-ЦЕЛИ — так нужно
    # обходу, который добавляет цель в контекст и обязан объяснить, кем она
    # приходится. Аннотация описывает роль самого пункта: если сосед его
    # отменяет, то пункт — отменённый. Первая редакция запроса возвращала
    # отношение как есть, и пометки встали наоборот: действующая редакция
    # объявлялась отменённой. Паритет со словарной реализацией это поймал.
    ANNOTATE = """
    SELECT c.chunk_id,
           CASE n.relation WHEN 'ОТМЕНЯЕТ' THEN 'ОТМЕНЁН' ELSE 'ОТМЕНЯЕТ' END AS relation,
           o.doc_code || ' · ' || o.section AS via
      FROM graph_chunks c
      JOIN graph_neighbours n ON n.from_id = c.chunk_id
      JOIN graph_chunks    o  ON o.chunk_id = n.to_id
      JOIN graph_documents od ON od.code = o.doc_code
     WHERE c.chunk_id = ANY(%(ids)s)
       AND n.relation IN ('ОТМЕНЯЕТ', 'ОТМЕНЁН')
       AND graph_visible(o.acl_roles, od.acl_roles, %(roles)s)
    """

    STATS = """
    SELECT (SELECT count(*) FROM graph_chunks)                                AS chunks,
           (SELECT count(*) FROM graph_documents)                             AS documents,
           (SELECT count(*) FROM graph_edges WHERE rel = 'ОТМЕНЯЕТ')          AS cancels,
           (SELECT count(*) FROM graph_edges WHERE rel = 'ССЫЛАЕТСЯ_НА')      AS refs
    """

    def __init__(self, dsn: str):
        import psycopg                       # импорт здесь: драйвер не нужен офлайн
        self._conn = psycopg.connect(dsn, autocommit=True)

    def build(self, documents, chunks):
        with self._conn.cursor() as cur:
            for stmt in self.SCHEMA:
                cur.execute(stmt)
            cur.execute(self.VISIBLE)
            cur.execute(self.NEIGHBOURS)
            # Индекс — производный артефакт, источник истины остаётся в корпусе
            # (ADR-0012). Перестроение целиком дешевле и честнее, чем попытка
            # выяснить, какие рёбра «устарели»: правила извлечения меняются, и
            # инкрементальное обновление начинает расходиться с корпусом молча.
            cur.execute("TRUNCATE graph_documents CASCADE")
            cur.executemany(
                """INSERT INTO graph_documents (code, name, title, acl_roles)
                   VALUES (%s, %s, %s, %s) ON CONFLICT (code) DO UPDATE
                   SET name = EXCLUDED.name, title = EXCLUDED.title,
                       acl_roles = EXCLUDED.acl_roles""",
                [(d.code, d.name, d.title, list(d.acl)) for d in documents])
            cur.executemany(
                """INSERT INTO graph_chunks (chunk_id, doc_code, section, ordinal, body,
                                             acl_roles, extracted_by, confidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [(c.id, c.doc_code, c.section, c.ordinal, c.text, list(c.acl),
                  getattr(c, "extracted_by", "text"), getattr(c, "confidence", 1.0))
                 for c in chunks])
            known = {c.id for c in chunks}
            cur.executemany(
                "INSERT INTO graph_edges (src, rel, dst_chunk, dst_doc, clause) VALUES (%s,%s,%s,%s,%s)",
                [(src, rel,
                  dst if rel == CANCELS and dst in known else None,
                  code,
                  None if rel == CANCELS else dst)
                 for src, rel, dst, code in derive_edges(documents, chunks)])

    def expand(self, seed_ids, roles, hops=1, limit=10):
        seeds = [int(i) for i in seed_ids]
        with self._conn.cursor() as cur:
            cur.execute(self.EXPAND, {"seeds": seeds, "roles": list(roles),
                                      "hops": max(1, hops)})
            rows = cur.fetchall()
        # Порядок выдачи — по глубине: ближние связи важнее дальних, и это та же
        # семантика, что у обхода фронтиром в двух других бэкендах.
        rows.sort(key=lambda r: (r[3], r[0]))
        return [Expansion(int(r[0]), r[1], r[2]) for r in rows][:limit]

    def annotations(self, chunk_ids, roles):
        with self._conn.cursor() as cur:
            cur.execute(self.ANNOTATE, {"ids": [int(i) for i in chunk_ids], "roles": list(roles)})
            ann = {}
            for cid, relation, via in cur.fetchall():
                ann.setdefault(int(cid), []).append((relation, via))
            return ann

    def stats(self):
        with self._conn.cursor() as cur:
            cur.execute(self.STATS)
            chunks, documents, cancels, refs = cur.fetchone()
        return {"backend": "postgres", "nodes": chunks, "documents": documents,
                "edges": cancels + refs, "cancels": cancels, "references": refs}

    def close(self):
        self._conn.close()


def build_graph_store(settings) -> GraphStore:
    """Бэкенд графа по конфигурации; при отказе выбранного — in-memory.

    `SUFLER_GRAPH_BACKEND`: `auto` (по умолчанию — Postgres, если задан DSN,
    иначе Neo4j, иначе память), либо явное имя. Явное имя нужно замеру: чтобы
    сравнивать бэкенды, надо уметь потребовать конкретный, а не тот, который
    сегодня оказался доступнее (ADR-0028).
    """
    want = getattr(settings, "graph_backend", "auto")
    dsn = getattr(settings, "graph_dsn", "")

    if want == "memory":
        return InMemoryGraphStore()
    if want in ("postgres", "auto") and dsn:
        try:
            return PgGraphStore(dsn)
        except Exception as e:
            print(f"[graph] Postgres недоступен ({e})")
            if want == "postgres":
                raise
    if want in ("neo4j", "auto") and settings.neo4j_uri:
        try:
            return Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        except Exception as e:  # драйвер не установлен или БД недоступна
            print(f"[graph] Neo4j недоступен ({e})")
            if want == "neo4j":
                raise
    if want in ("postgres", "neo4j"):
        # Явно потребованный бэкенд не настроен — молча уехать в память нельзя:
        # замер сравнит память с памятью и покажет «разницы нет».
        raise RuntimeError(f"бэкенд графа '{want}' затребован, но не настроен")
    return InMemoryGraphStore()
