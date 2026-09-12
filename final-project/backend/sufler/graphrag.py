"""GraphRAG-retrieval: vector-first → обход графа → rerank (ADR-0013).

Почему именно так, а не «чистый вектор» или «чистый граф»:
точку входа в граф по естественно-языковому вопросу даёт вектор, а связи,
которые вектор не видит (пункт отменён более поздним приказом, пункт ссылается
на смежный регламент), добавляет обход. Глубина ограничена, рёбра типизированы —
иначе растёт и latency, и шум в контексте.

Инвариант доступа: ACL применяется и в векторном pre-filter, и на каждом узле
обхода (ADR-0016). Пути через закрытый узел для непривилегированного субъекта
не существует — утечки через структуру графа нет.
"""
from dataclasses import dataclass

import numpy as np

from . import telemetry
from .graph import CANCELLED_BY, CANCELS


@dataclass
class Retrieved:
    """Чанк в контексте ответа и то, как он туда попал."""
    chunk: object
    relation: str = "ВЕКТОР"   # ВЕКТОР | ОТМЕНЁН | ОТМЕНЯЕТ | ССЫЛАЕТСЯ_НА
    via: str = ""

    @property
    def from_graph(self) -> bool:
        return self.relation != "ВЕКТОР"


class GraphAugmentedRetriever:
    """Гибрид: HybridRetriever (Qdrant + BM25 + rerank) + обход графа."""

    def __init__(self, hybrid, graph_store, settings):
        self.hybrid = hybrid
        self.graph = graph_store
        self.settings = settings
        self.by_id = {c.id: c for c in hybrid.chunks}
        # Метка бэкенда считается один раз: спрашивать `stats()` на каждом запросе
        # значило бы добавлять запрос к Neo4j ради строчки в метрике.
        self.backend = "neo4j" if type(graph_store).__name__.startswith("Neo4j") else "in-memory"

    def search(self, query: str, ctx, top_ctx: int = None):
        top_ctx = top_ctx or self.settings.top_k_context
        roles = list(ctx.roles)

        # Векторные кандидаты занимают top_ctx мест, графовые получают отдельный
        # резерв: иначе связанный пункт никогда не попадёт в контекст, и граф
        # окажется декорацией (ADR-0013).
        with telemetry.span("retrieve.hybrid", top_ctx=top_ctx) as sp:
            seeds = self.hybrid.search(query, roles, top_ctx=top_ctx)
            sp.set_attribute("seeds", len(seeds))
        if not seeds:
            return []
        result = [Retrieved(chunk=c) for c in seeds]
        if not self.settings.graph_enabled:
            return result[:top_ctx]

        with telemetry.span("graph.expand", backend=self.backend,
                            hops=self.settings.graph_hops,
                            limit=self.settings.graph_limit) as sp, \
                telemetry.GRAPH_EXPAND.labels(self.backend).time():
            expansions = self.graph.expand(
                [c.id for c in seeds], roles,
                hops=self.settings.graph_hops, limit=self.settings.graph_limit,
            )
            sp.set_attribute("expansions", len(expansions))
            telemetry.GRAPH_HOPS.observe(len(expansions))

        # Отмены попадают в контекст безусловно: пункт-модификатор может быть
        # текстуально непохож на вопрос, но именно он делает ответ верным.
        critical = [e for e in expansions if e.relation in (CANCELLED_BY, CANCELS)]
        optional = [e for e in expansions if e.relation not in (CANCELLED_BY, CANCELS)]

        for e in critical:
            chunk = self.by_id.get(e.chunk_id)
            if chunk is not None:
                result.append(Retrieved(chunk=chunk, relation=e.relation, via=e.via))

        # Остальные связанные чанки конкурируют за место в контексте по релевантности.
        if optional:
            cand = [self.by_id[e.chunk_id] for e in optional if e.chunk_id in self.by_id]
            if cand:
                scores = self.hybrid.reranker.predict([(query, c.text) for c in cand])
                order = np.argsort(scores)[::-1]
                room = max(0, self.settings.graph_slots - len(critical))
                for i in list(order)[:room]:
                    e = optional[int(i)]
                    result.append(Retrieved(chunk=cand[int(i)], relation=e.relation, via=e.via))

        # Аннотация статуса: пункт мог прийти вектором, но быть отменённым —
        # пометка обязана появиться независимо от способа попадания в контекст.
        with telemetry.span("graph.annotate", backend=self.backend) as sp:
            ann = self.graph.annotations([r.chunk.id for r in result], roles)
            sp.set_attribute("annotated", len(ann))
        for r in result:
            marks = ann.get(r.chunk.id, [])
            if not marks:
                continue
            relation, via = marks[0]
            if r.relation == "ВЕКТОР":
                r.relation, r.via = relation, via
            elif not r.via:
                r.via = via

        return result

    def graph_stats(self):
        return self.graph.stats()
