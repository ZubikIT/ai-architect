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
    return Sufler()


@pytest.fixture(scope="session")
def corpus():
    from sufler.ingest import chunk_documents, load_documents
    return chunk_documents(load_documents(os.environ["SUFLER_DATA_DIR"]))
