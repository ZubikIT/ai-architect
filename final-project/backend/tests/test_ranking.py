"""Ранжирование: локальная модель и сервис платформы за одним протоколом.

Тесты бьют в одно место — **порядок**. Сервис возвращает результаты
отсортированными по убыванию оценки, а вызывающему коду нужен порядок исходных
пар. Перепутать их — единственная ошибка в этом модуле, которая не падает, а
молча ухудшает выдачу: ответ по-прежнему приходит, просто не тот.
"""
import json

import pytest

from sufler.config import Settings
from sufler.ranking import LocalCrossEncoder, RemoteReranker, build_reranker


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def captured(monkeypatch):
    """Подменяет HTTP, запоминая запрос: сеть в тестах не нужна."""
    box = {}

    def fake_urlopen(req, timeout=None):
        box["url"] = req.full_url
        box["headers"] = dict(req.header_items())
        box["body"] = json.loads(req.data.decode())
        return FakeResponse(box["reply"])

    monkeypatch.setattr("sufler.ranking.urllib.request.urlopen", fake_urlopen)
    return box


def test_scores_follow_input_order_not_service_order(captured):
    """Главный инвариант: scores[i] относится к pairs[i], а не к i-му по рангу."""
    captured["reply"] = {"results": [
        {"index": 2, "relevance_score": 0.99},   # сервис вернул лучший первым
        {"index": 0, "relevance_score": 0.30},
        {"index": 1, "relevance_score": 0.01},
    ]}
    rr = RemoteReranker("http://rerank.local", "BAAI/bge-reranker-v2-m3")
    scores = rr.predict([("q", "а"), ("q", "б"), ("q", "в")])

    assert scores == [0.30, 0.01, 0.99]
    # и как следствие — правильный победитель
    assert max(range(3), key=lambda i: scores[i]) == 2


def test_request_shape_matches_jina_contract(captured):
    captured["reply"] = {"results": []}
    rr = RemoteReranker("http://rerank.local/", "BAAI/bge-reranker-v2-m3", api_key="k")
    rr.predict([("вопрос", "текст 1"), ("вопрос", "текст 2")])

    assert captured["url"] == "http://rerank.local/rerank"
    assert captured["body"] == {
        "model": "BAAI/bge-reranker-v2-m3",
        "query": "вопрос",
        "documents": ["текст 1", "текст 2"],
        "top_n": 2,
    }
    assert captured["headers"]["Authorization"] == "Bearer k"


def test_partial_reply_leaves_zero_rather_than_crashing(captured):
    """top_n мог быть урезан сервисом — пропущенные кандидаты просто не всплывают."""
    captured["reply"] = {"results": [{"index": 1, "relevance_score": 0.7}]}
    rr = RemoteReranker("http://rerank.local", "m")
    assert rr.predict([("q", "а"), ("q", "б"), ("q", "в")]) == [0.0, 0.7, 0.0]


def test_no_candidates_means_no_call(captured):
    captured["reply"] = {"results": []}
    rr = RemoteReranker("http://rerank.local", "m")
    assert rr.predict([]) == []
    assert "url" not in captured          # пустой набор не ходит в сеть


def test_key_is_not_sent_when_absent(captured):
    captured["reply"] = {"results": []}
    RemoteReranker("http://rerank.local", "m").predict([("q", "т")])
    assert "Authorization" not in captured["headers"]


def test_build_picks_local_without_url():
    cfg = Settings()
    cfg.rerank_url = ""
    assert isinstance(build_reranker(cfg), LocalCrossEncoder)


def test_build_picks_remote_with_url():
    cfg = Settings()
    cfg.rerank_url = "http://rerank.local"
    r = build_reranker(cfg)
    assert isinstance(r, RemoteReranker)
    assert r.model_name == "BAAI/bge-reranker-v2-m3"


# --- порог отказа на оценке реранкера -------------------------------------
#
# Проверяется не число, а правило: порог применяется только к калиброванной
# модели. На некалиброванной он молча выкинул бы правильные ответы — 8.2658
# «своего» ниже 8.9686 «чужого», и любой порог между ними режет не то.

class StubReranker:
    def __init__(self, score, calibrated):
        self.model_name = "stub"
        self.calibrated = calibrated
        self._score = score

    def predict(self, pairs):
        return [self._score] * len(pairs)


@pytest.fixture
def retriever(corpus, monkeypatch):
    from sufler.config import Settings
    from sufler.retriever import HybridRetriever
    _, chunks = corpus
    cfg = Settings()
    monkeypatch.setattr("sufler.retriever.build_reranker",
                        lambda settings: StubReranker(0.0, False))
    return HybridRetriever(chunks, cfg)


def test_calibrated_low_score_means_abstain(retriever):
    retriever.reranker = StubReranker(0.001, calibrated=True)
    assert retriever.search("Сколько дней основной ежегодный отпуск?", ["all"]) == []


def test_uncalibrated_low_score_does_not_abstain(retriever):
    """Тот же «низкий» балл на некалиброванной модели ничего не значит."""
    retriever.reranker = StubReranker(0.001, calibrated=False)
    assert retriever.search("Сколько дней основной ежегодный отпуск?", ["all"]) != []


def test_calibrated_high_score_answers(retriever):
    retriever.reranker = StubReranker(0.99, calibrated=True)
    assert retriever.search("Сколько дней основной ежегодный отпуск?", ["all"]) != []
