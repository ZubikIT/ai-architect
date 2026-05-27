"""HTTP API: /ask (нативный) + /v1/chat/completions (OpenAI-совместимый — для Open WebUI, ADR-0007)."""
import time
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .rag import Sufler

app = FastAPI(title="Суфлёр MVP", version="0.1")
_engine = None


def get_engine() -> Sufler:
    global _engine
    if _engine is None:
        _engine = Sufler()  # ленивая инициализация (загрузка моделей + индекс)
    return _engine


class AskReq(BaseModel):
    question: str
    roles: list[str] = ["all"]


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskReq):
    try:
        return get_engine().answer(req.question, tuple(req.roles))
    except ValueError as e:  # guardrail-блок
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/v1/chat/completions")
def chat_completions(body: dict):
    """Минимальная OpenAI-совместимость — чтобы Open WebUI мог подключить Суфлёр как модель."""
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages required")
    question = messages[-1]["content"]
    res = get_engine().answer(question)
    content = res["answer"]
    if res["sources"]:
        content += "\n\nИсточники: " + "; ".join(f"{s['doc']}·{s['section']}" for s in res["sources"])
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "sufler"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
    }
