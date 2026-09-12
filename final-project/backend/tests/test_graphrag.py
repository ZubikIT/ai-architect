"""GraphRAG-ядро: связи лечат «потерю контекста», ACL держится на каждом узле обхода.

Первый тест — доказательство, что граф не декорация: правильный ответ на этот
вопрос невозможен без ребра ОТМЕНЯЕТ (ADR-0013, критерий приёмки).
Второй блок — обязательный по ТЗ сценарий «User B не получает закрытый документ»,
проверенный по обоим путям: векторному и графовому.
"""
import pytest

from sufler.access import allowed
from sufler.graph import CANCELLED_BY, CANCELS, InMemoryGraphStore

RESTRICTED = "dostup-pdn"      # ЛПА-03, acl: legal, security


# --------------------------------------------------------------------------- #
#  Граф даёт то, чего не даёт плоский вектор
# --------------------------------------------------------------------------- #
def test_cancelled_clause_is_flagged(engine):
    """Вектор находит норму «28 дней», граф сообщает, что она отменена."""
    res = engine.answer("Сколько дней основной ежегодный отпуск?", roles=("all",))

    cancelled = [s for s in res["sources"] if s["relation"] == CANCELLED_BY]
    assert cancelled, "отменённый пункт должен быть помечен"
    assert any("otpusk.md" in s["doc"] for s in cancelled)
    assert any("ЛПА-04" in s["via"] for s in cancelled), "должен быть указан отменяющий документ"

    assert res["graph_notes"], "пользователь обязан увидеть предупреждение об отмене"
    assert "отменён" in " ".join(res["graph_notes"]).lower()
    assert "отменён" in res["answer"].lower()


def test_actual_revision_present_in_context(engine):
    """Действующая редакция попадает в контекст вместе с отменённой."""
    res = engine.answer("Сколько дней основной ежегодный отпуск?", roles=("all",))
    assert any(s["relation"] == CANCELS for s in res["sources"])
    assert any("30 календарных дней" in c for c in res["contexts"]), \
        "в контексте должна быть действующая норма, а не только отменённая"


def test_graph_disabled_loses_the_annotation(engine):
    """Контрольный замер: без графа пометки об отмене нет — эффект даёт именно граф."""
    from sufler.config import settings
    settings.graph_enabled = False
    try:
        res = engine.answer("Сколько дней основной ежегодный отпуск?", roles=("all",))
        assert not res["graph_notes"]
        assert all(s["relation"] == "ВЕКТОР" for s in res["sources"])
    finally:
        settings.graph_enabled = True


# --------------------------------------------------------------------------- #
#  Security: обязательный сценарий ТЗ
# --------------------------------------------------------------------------- #
def test_user_b_does_not_get_restricted_document(engine):
    """User B (роль all) не получает ни текста, ни следа закрытого ЛПА-03."""
    question = "Как обрабатываются персональные данные командированного работника?"
    res = engine.answer(question, roles=("all",))

    assert all(RESTRICTED not in s["doc"] for s in res["sources"]), "закрытый документ в источниках"
    # проверяем не только ответ, но и контекст, ушедший в модель
    joined = " ".join(res["contexts"])
    assert "минимальных привилегий" not in joined, "текст закрытого ЛПА попал в контекст LLM"
    assert RESTRICTED not in res["answer"]


def test_user_a_reaches_restricted_document_through_graph(engine):
    """User A (роль legal) добирается до ЛПА-03 по ребру ССЫЛАЕТСЯ_НА."""
    question = "Как обрабатываются персональные данные командированного работника?"
    res = engine.answer(question, roles=("legal",))
    hit = [s for s in res["sources"] if RESTRICTED in s["doc"]]
    assert hit, "роль legal должна видеть закрытый документ"
    assert any(s["relation"] == "ССЫЛАЕТСЯ_НА" for s in hit), "должен сработать графовый путь"


def test_graph_expansion_respects_acl(corpus):
    """Unit: обход не протаскивает закрытый узел — путь через него не существует."""
    documents, chunks = corpus
    store = InMemoryGraphStore()
    store.build(documents, chunks)

    seed = next(c for c in chunks if "Обработка данных командированного" in c.section)

    public = store.expand([seed.id], roles=["all"])
    assert all(RESTRICTED not in store.chunks[e.chunk_id].doc for e in public)

    privileged = store.expand([seed.id], roles=["legal"])
    assert any(RESTRICTED in store.chunks[e.chunk_id].doc for e in privileged)


def test_deny_by_default():
    """Отсутствие метки — это запрет, а не разрешение (ADR-0016, инвариант 1)."""
    assert allowed(["all"], ["anyone"]) is True
    assert allowed(["legal"], ["legal"]) is True
    assert allowed(["legal"], ["hr"]) is False
    assert allowed([], ["legal"]) is False


def test_annotations_hide_cancellation_by_invisible_document(corpus):
    """Отмена не раскрывается, если отменяющий документ недоступен субъекту."""
    documents, chunks = corpus
    store = InMemoryGraphStore()
    # делаем отменяющий документ ЛПА-04 закрытым
    for d in documents:
        if d.code == "ЛПА-04":
            d.acl = ["security"]
    for c in chunks:
        if c.doc_code == "ЛПА-04":
            c.acl = ["security"]
    store.build(documents, chunks)

    target = next(c for c in chunks if c.doc_code == "ЛПА-01" and c.ordinal == "1")
    assert store.annotations([target.id], ["all"]) == {}, "факт отмены раскрыт без прав"
    assert store.annotations([target.id], ["security"]), "владелец прав должен видеть отмену"


# --------------------------------------------------------------------------- #
#  Отказ от ответа: порог релевантности
# --------------------------------------------------------------------------- #
def test_out_of_corpus_question_is_refused(engine):
    """На вопрос не про ЛПА система отвечает отказом, а не пятью цитатами.

    Без порога релевантности выдача top-k возвращается всегда, и ответ про
    спутники приходит с ссылками на положение об отпуске — выглядит убедительно
    ровно в той мере, в какой неверен.
    """
    from sufler.rag import NO_ANSWER
    res = engine.answer("Каков регламент запуска спутника на геостационарную орбиту?",
                        roles=("all",))
    assert res["sources"] == []
    assert res["answer"] == NO_ANSWER


def test_refusal_does_not_disclose_that_something_exists(engine):
    """Отказ по правам неотличим от отказа по релевантности.

    Прежняя формулировка — «нет пунктов для вашего уровня доступа» — сообщала,
    что документ существует, просто закрыт. Это утечка через факт существования,
    против которой построен ACL на узлах графа (ADR-0016).
    """
    restricted = engine.answer("Что такое принцип минимальных привилегий?", roles=("all",))
    nonsense = engine.answer("Каков регламент запуска спутника?", roles=("all",))
    if not restricted["sources"]:
        assert restricted["answer"] == nonsense["answer"], \
            "по тексту отказа видно, что документ существует"
    assert "доступ" not in nonsense["answer"].lower()


def test_relevant_questions_survive_the_floor(engine):
    """Порог не должен резать нормальные вопросы — иначе он вредит, а не помогает."""
    for question in ("Сколько дней основной ежегодный отпуск?",
                     "Какой размер суточных при командировке?",
                     "Когда выплачивается компенсация за неиспользованный отпуск?"):
        assert engine.answer(question, roles=("all",))["sources"], question
