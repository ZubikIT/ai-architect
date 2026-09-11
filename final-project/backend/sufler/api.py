"""HTTP API: /ask (нативный) + /v1/chat/completions (OpenAI-совместимый — для Open WebUI, ADR-0007)."""
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, make_asgi_app

from .rag import Sufler

app = FastAPI(title="Суфлёр MVP", version="0.1")
_engine = None

# ── Observability (урок 15): Golden Signals для дашборда GenAI/Суфлёр ──────────
# Имена совпадают с sufler-dashboard.json: ① latency, ② traffic, ③ errors.
# Скрейпится VictoriaMetrics (job 'sufler' → 10.100.1.45:8080/metrics).
SUFLER_REQUESTS = Counter(
    "sufler_requests_total", "Запросы к Суфлёру", ["endpoint", "status"]
)
SUFLER_LATENCY = Histogram(
    "sufler_request_latency_seconds", "Время ответа Суфлёра, с", ["endpoint"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 6, 8, 12, 20),
)


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":  # не считаем сам скрейп
        return await call_next(request)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        endpoint = request.scope.get("route").path if request.scope.get("route") else request.url.path
        SUFLER_LATENCY.labels(endpoint).observe(time.perf_counter() - start)
        SUFLER_REQUESTS.labels(endpoint, str(status)).inc()


# /metrics в формате Prometheus (для VictoriaMetrics scrape)
app.mount("/metrics", make_asgi_app())


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
