"""Оркестрация GraphRAG: guardrails → hybrid → обход графа → LLM → ответ с цитатами.

Ядро платформы цифровых сотрудников (ADR-0013, ADR-0015, ADR-0016).
Ключевое отличие от плоского RAG: ответ несёт не только найденные пункты, но и
их модификаторы — если норма отменена более поздним приказом, это видно и в
контексте модели, и в ответе пользователю.
"""
from .access import RequestContext
from .config import settings
from .graph import CANCELLED_BY, CANCELS
from .graphrag import GraphAugmentedRetriever
from .guardrails import StreamingPiiFilter, check_input, mask_pii
from .ingest import chunk_documents, load_documents
from .retriever import HybridRetriever
from . import telemetry

# Правила ответа отделены от роли: их наследуют и Суфлёр, и каждый «цифровой
# сотрудник» (ADR-0015). Разъедься эти формулировки — разъехались бы и требования
# цитирования с предупреждением об отмене, то есть ровно то, что проверяется.
ANSWER_RULES = (
    "Отвечай ТОЛЬКО на основе предоставленного контекста из локальных правовых актов (ЛПА). "
    "Если ответа в контексте нет — честно скажи «Не нашёл в ЛПА, уточните у профильного отдела». "
    "Всегда указывай источник (документ и раздел). "
    "Если пункт помечен как отменённый — отвечай по действующей редакции и прямо предупреди, "
    "что прежняя норма отменена. Не выдумывай факты."
)

SYSTEM = "Ты — корпоративный ассистент «Суфлёр». " + ANSWER_RULES

NO_ANSWER = "Не нашёл подходящих пунктов ЛПА — уточните формулировку или обратитесь в профильный отдел."


def build_context(found):
    """Результаты retrieval → (блоки контекста, источники, тексты, пометки об отменах).

    Вынесено из `Sufler.answer`, потому что мультиагентный слой (ADR-0015) собирает
    контекст тем же способом. Разойдись эти две сборки — разошлись бы и пометки об
    отменах, а ради них и строился граф: «цифровой сотрудник» обязан предупреждать
    об отменённой норме ровно так же, как одиночный Суфлёр.

    Списки параллельны (i-й блок ↔ i-й источник ↔ i-й текст): на этом держится
    слияние находок нескольких агентов по `chunk_id`.
    """
    blocks, sources, contexts, notes = [], [], [], []
    for item in found:
        c = item.chunk
        mark = ""
        if item.relation == CANCELLED_BY:
            mark = " · ОТМЕНЁН, применению не подлежит"
            # Заметка формулируется от отменённого пункта: парное ребро
            # ОТМЕНЯЕТ описывает ту же отмену с другой стороны, и вторая
            # формулировка только зашумила бы предупреждение.
            notes.append(f"{c.doc_code} «{c.section}» отменён"
                         + (f" документом {item.via}" if item.via else ""))
        elif item.relation == CANCELS:
            mark = " · действующая редакция, отменяет прежнюю"
        elif item.from_graph:
            mark = f" · связан по графу ({item.relation}, через {item.via})"
        blocks.append(f"[{c.doc} · {c.section}{mark}]\n{c.text}")
        # doc_code и ordinal отдаются наружу намеренно: «ЛПА-01 § 1» — устойчивый
        # адрес пункта, переживающий перечанкинг, в отличие от chunk_id. На нём
        # держится golden set (eval/golden.yaml) и человекочитаемая ссылка в UI.
        sources.append({"chunk_id": c.id, "doc": c.doc, "doc_code": c.doc_code,
                        "ordinal": c.ordinal, "section": c.section,
                        "relation": item.relation, "via": item.via,
                        "extracted_by": c.extracted_by})
        contexts.append(c.text)
    return blocks, sources, contexts, notes


class Sufler:
    def __init__(self):
        documents, chunks = chunk_documents(load_documents(settings.data_dir))
        hybrid = HybridRetriever(chunks, settings)

        from .graph import build_graph_store
        self.graph = build_graph_store(settings)
        self.graph.build(documents, chunks)
        self.retriever = GraphAugmentedRetriever(hybrid, self.graph, settings)

        self.llm = None
        if settings.use_llm:
            from .llm import LLM
            self.llm = LLM()

    def _prepare(self, question: str, ctx, root):
        """Общая часть обоих путей: guardrail → retrieval → сборка контекста.

        Вынесено, чтобы потоковый ответ шёл по той же дороге, что и обычный.
        Разойдись они — разошлись бы и проверка прав, и пометки об отменах, то
        есть ровно то, что доказывается тестами для одного из путей.
        """
        with telemetry.span("guardrail.input"):
            try:
                check_input(question)
            except ValueError:
                telemetry.GUARDRAIL_BLOCKS.labels("input").inc()
                root.set_attribute("outcome", "blocked")
                raise

        with telemetry.span("retrieve") as sp:
            found = self.retriever.search(question, ctx)
            sp.set_attribute("chunks", len(found))

        if not found:
            # Отказ — такое же событие для аудита, как и выдача (ADR-0016, инвариант 6);
            # причину (права или релевантность) считает ретривер, он её и знает.
            #
            # Формулировка намеренно одна на оба случая. Прежняя — «нет пунктов
            # ДЛЯ ВАШЕГО УРОВНЯ ДОСТУПА» — сообщала, что документ существует,
            # просто закрыт. Это та самая утечка через факт существования,
            # против которой построен весь ACL на узлах графа (ADR-0016).
            root.set_attribute("outcome", "no_answer")
            return None
        return (found, *build_context(found))

    def answer_stream(self, question: str, roles=("all",), subject: str = "anonymous"):
        """Тот же ответ, но событиями по мере готовности (SSE).

        Порядок событий выбран под UX, а не под удобство сервера: **источники
        уходят раньше текста**. Пользователь видит, на чём будет основан ответ,
        пока модель ещё генерирует — а для корпоративного ассистента цитата
        важнее скорости появления первого слова.

        Спаны здесь заводятся вручную, а не контекстным менеджером: контекстные
        переменные не переживают `yield` (см. `telemetry.start_request_span`).
        """
        ctx = RequestContext.of(roles, subject)
        root = telemetry.start_request_span(
            "ask.stream", ctx.request_id, path="rag-stream", subject=ctx.subject,
            roles=",".join(ctx.roles), question=telemetry.content(question))
        try:
            yield "meta", {"request_id": ctx.request_id}

            with telemetry.active(root):          # внутри `_prepare` нет `yield`
                prepared = self._prepare(question, ctx, root)
            if prepared is None:
                yield "token", {"text": NO_ANSWER}
                yield "done", {"request_id": ctx.request_id, "sources": 0, "graph_notes": []}
                return

            found, blocks, sources, contexts, notes = prepared
            yield "sources", sources

            # Маска ПДн держит окно: шаблон почти всегда разорван границей токена,
            # поэтому маскируется накопленный текст, а наружу идёт устойчивый префикс.
            pii = StreamingPiiFilter()
            context = "\n\n".join(blocks)
            if self.llm:
                gen = telemetry.child_span(root, "llm.generate", model=settings.llm_model,
                                           context_chars=len(context), streaming=True)
                try:
                    for delta in self.llm.stream(
                            SYSTEM, f"Контекст:\n{context}\n\nВопрос: {question}"):
                        out = pii.push(delta)
                        if out:
                            yield "token", {"text": out}
                finally:
                    gen.end()
            else:
                # Офлайн-демо: текст режется на куски, чтобы поток был виден без LLM.
                demo = "(демо без LLM) Наиболее релевантный пункт:\n\n" + found[0].chunk.text
                for i in range(0, len(demo), 48):
                    out = pii.push(demo[i:i + 48])
                    if out:
                        yield "token", {"text": out}

            tail = pii.flush()
            if tail:
                yield "token", {"text": tail}
            if pii.text != pii.raw:
                telemetry.GUARDRAIL_BLOCKS.labels("output").inc()

            unique_notes = list(dict.fromkeys(notes))
            for note in unique_notes:
                # Предупреждение об отмене — отдельным событием, а не хвостом
                # текста: интерфейс обязан показать его заметно, а не абзацем ниже.
                yield "note", {"text": note}

            self._record(root, "rag-stream", sources, any(i.from_graph for i in found),
                         bool(unique_notes))
            yield "done", {"request_id": ctx.request_id, "sources": len(sources),
                           "graph_notes": unique_notes}
        finally:
            # Клиент может оборваться на любом шаге — спан обязан закрыться всё равно,
            # иначе трейс подвиснет незавершённым.
            root.end()

    def answer(self, question: str, roles=("all",), subject: str = "anonymous") -> dict:
        ctx = RequestContext.of(roles, subject)   # создаётся один раз на запрос (ADR-0016)
        # Корневой спан: с этого места trace_id == request_id (ADR-0017), и тот же
        # идентификатор лежит в ответе пользователю и в журнале доступа.
        with telemetry.request_span("ask", ctx.request_id, path="rag",
                                    subject=ctx.subject, roles=",".join(ctx.roles),
                                    question=telemetry.content(question)) as root:
            prepared = self._prepare(question, ctx, root)
            if prepared is None:
                return {"answer": NO_ANSWER, "sources": [], "contexts": [],
                        "graph_notes": [], "request_id": ctx.request_id}

            found, blocks, sources, contexts, notes = prepared
            context = "\n\n".join(blocks)
            if self.llm:
                with telemetry.span("llm.generate", model=settings.llm_model,
                                    context_chars=len(context)):
                    draft = self.llm.chat(SYSTEM, f"Контекст:\n{context}\n\nВопрос: {question}")
            else:
                # офлайн-демо без LLM — extractive fallback
                draft = ("(демо без LLM) Наиболее релевантный пункт:\n\n" + found[0].chunk.text)

            if notes:
                draft += "\n\n⚠️ " + "; ".join(dict.fromkeys(notes)) + "."

            with telemetry.span("guardrail.output"):
                answer = mask_pii(draft)
                if answer != draft:
                    telemetry.GUARDRAIL_BLOCKS.labels("output").inc()

            from_graph = any(i.from_graph for i in found)
            self._record(root, "rag", sources, from_graph, bool(notes))
            return {"answer": answer,
                    "sources": sources, "contexts": contexts,
                    "graph_notes": list(dict.fromkeys(notes)),
                    "request_id": ctx.request_id}

    @staticmethod
    def _record(span, path: str, sources, from_graph: bool, cancelled: bool) -> None:
        """Итог обращения в метрики и в корневой спан.

        `cancellation` — ключевой показатель проекта: доля ответов, где сработало
        ребро ОТМЕНЯЕТ. Ноль в проде означает, что граф не работает, как бы хорошо
        он ни выглядел на демо (ADR-0017).
        """
        yes = lambda flag: "yes" if flag else "no"   # noqa: E731
        telemetry.ANSWERS.labels(path, yes(from_graph), yes(cancelled)).inc()
        span.set_attribute("outcome", "ok")
        span.set_attribute("sources", len(sources))
        span.set_attribute("graph_contribution", from_graph)
        span.set_attribute("cancellation_flagged", cancelled)

    def graph_stats(self):
        return self.retriever.graph_stats()

    def close(self):
        """Освободить соединение с графом. Драйвер Neo4j держит пул сокетов:
        в долгоживущем сервисе его обязан закрывать владелец, а не сборщик мусора."""
        self.graph.close()
