"""Общие фикстуры. Движок поднимается один раз на сессию: инициализация тянет
эмбеддер и реранкер, а это десятки секунд — гонять их на каждый тест незачем.
"""
import os

import pytest

os.environ.setdefault("SUFLER_USE_LLM", "0")   # офлайн: без внешнего LLM
os.environ.setdefault("SUFLER_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "lpa"))


@pytest.fixture(scope="session")
def engine():
    from sufler.rag import Sufler
    eng = Sufler()
    yield eng
    eng.close()      # при NEO4J_URI это закрытие драйвера, а не формальность


@pytest.fixture                       # НЕ session: см. ниже
def corpus():
    """Свежий разбор корпуса на каждый тест.

    Сессионная фикстура здесь протекала: `test_annotations_hide_cancellation_by_
    invisible_document` меняет ACL ЛПА-04 прямо в объектах, и мутация доставалась
    следующим тестам. На живом Neo4j это было не просто грязью в тестах —
    `test_demo_corpus_parity` записывал изменённый корпус в базу, ЛПА-04
    становился закрытым, и демонстрация отмены («28 → 30 дней») переставала
    работать до следующей переиндексации. Разбор markdown стоит миллисекунды,
    моделей не трогает — экономить на нём нечего.
    """
    from sufler.ingest import chunk_documents, load_documents
    return chunk_documents(load_documents(os.environ["SUFLER_DATA_DIR"]))


@pytest.fixture(scope="session")
def platform(engine):
    """Мультиагентный слой поверх того же движка — второй раз модели не грузим."""
    from sufler.mas import Platform
    return Platform(engine=engine)
