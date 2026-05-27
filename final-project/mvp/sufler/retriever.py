"""Этап 2 — Hybrid search (dense + BM25, RRF) + reranking + RBAC pre-filter (урок 06, ADR-0004)."""
import re

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


def _tok(s: str):
    return re.findall(r"\w+", s.lower())


class HybridRetriever:
    def __init__(self, chunks, settings):
        self.chunks = chunks
        self.settings = settings
        self.embedder = SentenceTransformer(settings.embed_model)
        self.reranker = CrossEncoder(settings.rerank_model)

        # dense → Qdrant (в демо :memory:, в проде — self-hosted сервер, ADR-0004)
        vecs = self.embedder.encode([c.text for c in chunks], normalize_embeddings=True)
        dim = int(vecs.shape[1])
        self.client = QdrantClient(":memory:")
        self.client.recreate_collection(
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
        self.bm25 = BM25Okapi([_tok(c.text) for c in chunks])

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

        qv = self.embedder.encode([query], normalize_embeddings=True)[0]
        dense = self.client.search(
            collection_name=self.settings.collection,
            query_vector=qv.tolist(), limit=top_k,
        )
        dense_ids = [int(p.id) for p in dense]

        scores = self.bm25.get_scores(_tok(query))
        bm25_ids = [int(i) for i in np.argsort(scores)[::-1][:top_k]]

        # объединение результатов (Reciprocal Rank Fusion)
        fused = self._rrf([dense_ids, bm25_ids])

        # RBAC pre-filter (№ 99-З): только разрешённые роли
        cand = [self.chunks[i] for i in fused if self._allowed(self.chunks[i], roles)][:top_k]
        if not cand:
            return []

        # rerank (cross-encoder) — урок 06
        rr = self.reranker.predict([(query, c.text) for c in cand])
        order = np.argsort(rr)[::-1]
        return [cand[i] for i in order][:top_ctx]
