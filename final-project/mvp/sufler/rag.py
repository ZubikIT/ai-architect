"""Оркестрация RAG: guardrails → hybrid+rerank → LLM → цитаты. Ядро Суфлёра (этапы 1-2)."""
from .config import settings
from .guardrails import check_input, mask_pii
from .ingest import chunk_documents, load_documents
from .retriever import HybridRetriever

SYSTEM = (
    "Ты — корпоративный ассистент «Суфлёр». Отвечай ТОЛЬКО на основе предоставленного "
    "контекста из локальных правовых актов (ЛПА). Если ответа в контексте нет — честно скажи "
    "«Не нашёл в ЛПА, уточните у профильного отдела». Всегда указывай источник (документ и раздел). "
    "Не выдумывай факты."
)


class Sufler:
    def __init__(self):
        chunks = chunk_documents(load_documents(settings.data_dir))
        self.retriever = HybridRetriever(chunks, settings)
        self.llm = None
        if settings.use_llm:
            from .llm import LLM
            self.llm = LLM()

    def answer(self, question: str, roles=("all",)) -> dict:
        check_input(question)  # input-guardrail
        ctx = self.retriever.search(question, list(roles))
        if not ctx:
            return {"answer": "Не нашёл релевантных пунктов ЛПА для вашего уровня доступа.",
                    "sources": []}

        context = "\n\n".join(f"[{c.doc} · {c.section}]\n{c.text}" for c in ctx)
        sources = [{"doc": c.doc, "section": c.section} for c in ctx]

        if self.llm:
            draft = self.llm.chat(SYSTEM, f"Контекст:\n{context}\n\nВопрос: {question}")
        else:
            # офлайн-демо без LLM — extractive fallback
            draft = ("(демо без LLM) Наиболее релевантный пункт:\n\n"
                     f"{ctx[0].text}")

        return {"answer": mask_pii(draft), "sources": sources}  # output-guardrail
