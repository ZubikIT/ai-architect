"""Этап 2 — Hybrid search (dense + BM25, RRF) + reranking + RBAC pre-filter (урок 06, ADR-0004)."""
import re

import numpy as np
from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from . import telemetry
from .embedding import build_embedder
from .ranking import LocalCrossEncoder, build_reranker


def _tok(s: str):
    return re.findall(r"\w+", s.lower())


class HybridRetriever:
    def __init__(self, chunks, settings):
        self.chunks = chunks
        self.settings = settings
        # Где считаются модели — вопрос конфигурации, а не кода retrieval:
        # сервис платформы при заданных SUFLER_EMBED_URL / SUFLER_RERANK_URL,
        # иначе локальные модели на CPU (офлайн-демо и тесты).
        self.embedder = build_embedder(settings)
        self.reranker = build_reranker(settings)

        # dense → Qdrant: self-hosted сервер при QDRANT_URL, иначе встроенный
        # :memory: (офлайн-демо и тесты). Сервис в compose до этого никем не
        # использовался — поднятый Qdrant стоял пустым, а индекс жил в процессе.
        # indexed_text, а не text: каждый кусок несёт собственный адрес, иначе
        # «пункт 3. Возмещение расходов» неотличим от любого другого пункта 3
        # в корпусе (ADR-0027, вывод пилота платформы).
        vecs = self.embedder.encode([c.indexed_text for c in chunks], normalize_embeddings=True)
        dim = int(vecs.shape[1])
        self.client = QdrantClient(url=settings.qdrant_url) if settings.qdrant_url \
            else QdrantClient(":memory:")
        # Коллекция пересоздаётся на старте: индекс — производный артефакт, его
        # источник истины остаётся в корпусе ЛПА (ADR-0012, тот же принцип, что и
        # для графа). В проде это работа индексатора, а не runtime-учётки (ADR-0016).
        if self.client.collection_exists(settings.collection):
            self.client.delete_collection(settings.collection)
        self.client.create_collection(
            collection_name=settings.collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        self.client.upsert(
            collection_name=settings.collection,
            points=[
                PointStruct(id=c.id, vector=vecs[i].tolist(),
                            payload={"doc": c.doc, "section": c.section, "acl": c.acl})
                for i, c in enumerate(chunks)
            ],
        )

        # sparse → BM25
        self.bm25 = BM25Okapi([_tok(c.indexed_text) for c in chunks])

    @staticmethod
    def _allowed(chunk, roles):
        return "all" in chunk.acl or bool(set(chunk.acl) & set(roles))

    @staticmethod
    def _rrf(rankings, k: int = 60):
        scores = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking):
                scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
        return [idx for idx, _ in sorted(scores.items(), key=lambda x: -x[1])]

    def search(self, query: str, roles, top_k=None, top_ctx=None):
        top_k = top_k or self.settings.top_k_retrieve
        top_ctx = top_ctx or self.settings.top_k_context

        # Шаги разделены спанами не для красоты: в нагрузочном отчёте вопрос
        # «что именно упирается» без этого разложения не имеет ответа, а без
        # ответа непонятно, что оптимизировать — индекс, эмбеддер или реранк
        # (ADR-0017: hybrid-поиск и rerank — отдельные шаги трейса).
        with telemetry.span("retrieve.embed", chars=len(query)):
            qv = self.embedder.encode([query], normalize_embeddings=True)[0]

        with telemetry.span("retrieve.dense", top_k=top_k) as sp:
            dense = self.client.search(
                collection_name=self.settings.collection,
                query_vector=qv.tolist(), limit=top_k,
            )
            dense_ids = [int(p.id) for p in dense]
            top_score = max((p.score for p in dense), default=0.0)
            sp.set_attribute("top_score", round(float(top_score), 4))

        # Отказ от ответа. Без этого порога система отвечает на любой вопрос —
        # включая те, которых в корпусе нет, — и прикладывает к ответу цитаты,
        # что выглядит убедительнее, чем есть на самом деле.
        if top_score < self.settings.min_relevance:
            telemetry.LOW_RELEVANCE.inc()
            return []

        with telemetry.span("retrieve.bm25", top_k=top_k):
            scores = self.bm25.get_scores(_tok(query))
            bm25_ids = [int(i) for i in np.argsort(scores)[::-1][:top_k]]

        # объединение результатов (Reciprocal Rank Fusion)
        fused = self._rrf([dense_ids, bm25_ids])

        # RBAC pre-filter (№ 99-З): только разрешённые роли
        cand = [self.chunks[i] for i in fused if self._allowed(self.chunks[i], roles)][:top_k]
        if not cand:
            telemetry.ACL_DENIALS.inc()
            return []

        # rerank (cross-encoder) — урок 06. Стоимость линейна по числу кандидатов,
        # а их число зависит от прав субъекта: широкие права — дороже запрос.
        with telemetry.span("retrieve.rerank", candidates=len(cand)) as sp:
            rr = self.reranker.predict([(query, c.indexed_text) for c in cand])
            sp.set_attribute("model", self.reranker.model_name)
            sp.set_attribute("remote", not isinstance(self.reranker, LocalCrossEncoder))
        order = np.argsort(rr)[::-1]

        # Отказ по релевантности — здесь он точнее, чем по косинусу выше: косинус
        # меряет близость запроса к тексту, реранкер — отвечает ли текст на
        # вопрос. Разница видна на вопросах, которые звучат по-корпоративному, но
        # ответа в корпусе не имеют. Порог работает только на калиброванной
        # модели; на некалиброванной решает косинус, и это осознанная деградация,
        # а не запасной вариант «на всякий случай».
        if self.reranker.calibrated and float(rr[order[0]]) < self.settings.min_rerank_score:
            telemetry.LOW_RELEVANCE.inc()
            return []

        return [cand[i] for i in order][:top_ctx]
