"""Эмбеддер: протокол, батчинг, порядок и отказы.

Тесты не ходят в сеть — `urlopen` подменяется. Проверяется то, что ломается
молча: перепутанный порядок векторов, потерянные тексты в батче, отказ,
выдающий себя за пустую выдачу.
"""
import io
import json
import urllib.error

import numpy as np
import pytest

from sufler.config import Settings
from sufler.embedding import EmbedUnavailable, LocalEmbedder, RemoteEmbedder, build_embedder


def _reply(vectors, shuffle=False):
    """Ответ сервиса; при shuffle элементы идут в обратном порядке — сервис
    порядка не обещает, и код обязан раскладывать по полю index."""
    data = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    if shuffle:
        data = list(reversed(data))
    body = json.dumps({"data": data}).encode()
    return io.BytesIO(body)


def test_url_gets_embeddings_path():
    e = RemoteEmbedder("http://infinity.local", "BAAI/bge-m3")
    assert e.url == "http://infinity.local/embeddings"
    e = RemoteEmbedder("http://infinity.local/", "BAAI/bge-m3")
    assert e.url == "http://infinity.local/embeddings"


def test_empty_input_does_not_touch_the_network(monkeypatch):
    def boom(*a, **k):
        pytest.fail("пустой ввод не должен уходить в сеть")
    monkeypatch.setattr("sufler.httpservice.urllib.request.urlopen", boom)
    assert RemoteEmbedder("http://x", "m").encode([]).shape == (0, 0)


def test_order_follows_index_not_reply_order(monkeypatch):
    """Порядок векторов задаёт поле index, а не позиция в ответе.

    Если полагаться на позицию, вектор чужого текста молча встанет на место
    своего: выдача останется непустой и правдоподобной, но неверной.
    """
    monkeypatch.setattr("sufler.httpservice.urllib.request.urlopen",
                        lambda *a, **k: _reply([[1.0, 0.0], [0.0, 1.0]], shuffle=True))
    v = RemoteEmbedder("http://x", "m").encode(["первый", "второй"])
    assert np.allclose(v[0], [1.0, 0.0]) and np.allclose(v[1], [0.0, 1.0])


def test_batching_covers_every_text(monkeypatch):
    seen = []

    def fake(req, timeout=None):
        payload = json.loads(req.data.decode())
        seen.append(len(payload["input"]))
        return _reply([[float(i), 1.0] for i in range(len(payload["input"]))])

    monkeypatch.setattr("sufler.httpservice.urllib.request.urlopen", fake)
    v = RemoteEmbedder("http://x", "m", batch=3).encode([f"т{i}" for i in range(7)])
    assert seen == [3, 3, 1], "набор обязан резаться на порции batch"
    assert v.shape == (7, 2)


def test_short_reply_is_an_error_not_a_silent_gap(monkeypatch):
    """Векторов пришло меньше, чем текстов — это отказ, а не повод молча
    продолжить: несовпадение сдвинет соответствие чанков и векторов."""
    monkeypatch.setattr("sufler.httpservice.urllib.request.urlopen",
                        lambda *a, **k: _reply([[1.0, 0.0]]))
    e = RemoteEmbedder("http://x", "m")
    with pytest.raises(EmbedUnavailable):
        e.encode(["первый", "второй"])
    assert e.healthy is False


def test_vectors_are_normalised(monkeypatch):
    monkeypatch.setattr("sufler.httpservice.urllib.request.urlopen",
                        lambda *a, **k: _reply([[3.0, 4.0]]))
    v = RemoteEmbedder("http://x", "m").encode(["т"])
    assert np.isclose(np.linalg.norm(v[0]), 1.0), "косинусный порог требует нормы 1"


def test_client_error_is_not_retried(monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(1)
        raise urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("sufler.httpservice.urllib.request.urlopen", fake)
    with pytest.raises(EmbedUnavailable):
        RemoteEmbedder("http://x", "m").encode(["т"])
    assert len(calls) == 1, "4xx — ошибка конфигурации, повтор вернёт то же самое"


def test_server_error_is_retried_once(monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError("http://x", 503, "Service Unavailable", {}, None)
        return _reply([[1.0, 0.0]])

    monkeypatch.setattr("sufler.httpservice.urllib.request.urlopen", fake)
    v = RemoteEmbedder("http://x", "m").encode(["т"])
    assert len(calls) == 2 and v.shape == (1, 2)


def test_build_embedder_follows_configuration(monkeypatch):
    cfg = Settings()
    cfg.embed_url = ""
    monkeypatch.setattr("sufler.embedding.LocalEmbedder", lambda model: "local")
    assert build_embedder(cfg) == "local"
    cfg.embed_url = "http://infinity.local"
    assert isinstance(build_embedder(cfg), RemoteEmbedder)


def test_threshold_default_depends_on_where_embeddings_come_from(monkeypatch):
    """Порог косинуса привязан к модели: у bge-m3 другой масштаб близости,
    и одно умолчание на оба пути означало бы разное качество отказа."""
    monkeypatch.delenv("SUFLER_MIN_RELEVANCE", raising=False)
    monkeypatch.delenv("EMBEDDINGS_URL", raising=False)
    assert Settings().min_relevance == 0.45
    monkeypatch.setenv("EMBEDDINGS_URL", "http://infinity.local")
    assert Settings().min_relevance == 0.55
