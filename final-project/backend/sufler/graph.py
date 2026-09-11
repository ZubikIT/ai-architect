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
        return {"backend": "in-memory", "nodes": len(self.chunks), "edges": len(self.edges)}


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

    # ACL-предикат стоит на КАЖДОМ узле пути, включая документ-владелец.
    EXPAND = """
    MATCH (seed:Чанк) WHERE seed.chunk_id IN $seeds
    MATCH (seed)<-[:ОТМЕНЯЕТ]-(other:Чанк)<-[:СОДЕРЖИТ]-(od:Документ)
    WHERE ('all' IN other.acl_roles OR any(r IN other.acl_roles WHERE r IN $roles))
      AND ('all' IN od.acl_roles   OR any(r IN od.acl_roles   WHERE r IN $roles))
    RETURN other.chunk_id AS chunk_id, 'ОТМЕНЯЕТ' AS relation,
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

    STATS = """
    MATCH (c:Чанк) WITH count(c) AS nodes
    MATCH ()-[e]->() RETURN nodes, count(e) AS edges
    """

    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase  # импорт здесь: драйвер не нужен в офлайн-режиме
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def build(self, documents, chunks):
        with self._driver.session() as s:
            for stmt in self.SCHEMA:
                s.run(stmt)
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
        with self._driver.session() as s:
            rows = s.run(self.EXPAND, seeds=list(seed_ids), roles=list(roles))
            out, seen = [], set(seed_ids)
            for r in rows:
                cid = int(r["chunk_id"])
                if cid in seen:
                    continue
                seen.add(cid)
                out.append(Expansion(cid, r["relation"], r["via"]))
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
            return {"backend": "neo4j", "nodes": rec["nodes"], "edges": rec["edges"]} if rec else {}

    def close(self):
        self._driver.close()


def build_graph_store(settings) -> GraphStore:
    """Neo4j, если настроен и драйвер доступен; иначе — in-memory (офлайн-демо и тесты)."""
    if settings.neo4j_uri:
        try:
            return Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        except Exception as e:  # драйвер не установлен или БД недоступна
            print(f"[graph] Neo4j недоступен ({e}) → in-memory режим")
    return InMemoryGraphStore()
