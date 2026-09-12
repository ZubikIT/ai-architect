"""HTTP API: /ask (нативный) · /agents/ask (мультиагентный, ADR-0015) ·
/v1/chat/completions (OpenAI-совместимый — для Open WebUI, ADR-0007)."""
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, make_asgi_app

from .rag import Sufler

app = FastAPI(title="Суфлёр MVP", version="0.1")
_engine = None
_platform = None

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


def get_platform():
    """Мультиагентный слой поверх того же движка (ADR-0015): индекс, граф и
    ACL-инварианты у одиночного Суфлёра и у «цифровых сотрудников» общие.

    `SUFLER_MAS=0` — рубильник: если слой агентов начинает вести себя плохо в
    проде, контур остаётся рабочим на одиночном `/ask`, а не выключается целиком.
    """
    from .config import settings
    if not settings.mas_enabled:
        raise HTTPException(status_code=503, detail="Мультиагентный слой выключен (SUFLER_MAS=0)")
    global _platform
    if _platform is None:
        from .mas import Platform
        _platform = Platform(engine=get_engine())
    return _platform


class AskReq(BaseModel):
    question: str
    # ВРЕМЕННО: роли из тела запроса — только для локальной отладки и демо.
    # Целевой путь (ADR-0016): роли берутся из проверенного по JWKS токена
    # Keycloak, тело запроса на доступ не влияет. Пока OIDC_JWKS_URL не задан,
    # сервис обязан работать в доверенном контуре.
    roles: list[str] = ["all"]


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/graph/stats")
def graph_stats():
    """Статистика графа знаний — для демо и проверки, что ingestion отработал."""
    return get_engine().graph_stats()


@app.post("/ask")
def ask(req: AskReq):
    try:
        return get_engine().answer(req.question, tuple(req.roles))
    except ValueError as e:  # guardrail-блок
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/agents")
def agents():
    """Штат «цифровых сотрудников»: компетенция, мандат прав, правила маршрутизации."""
    from .config import settings
    from .mas import roster
    return {"enabled": settings.mas_enabled, "agents": roster()}


@app.post("/agents/ask")
def agents_ask(req: AskReq):
    """Мультиагентный путь: супервизор → роли-агенты → сведение (ADR-0015).

    Отдельный эндпоинт, а не флаг в /ask: у ответа другой контракт — маршрут,
    ReAct-trace и израсходованный бюджет. Клиент выбирает путь осознанно.
    """
    try:
        return get_platform().answer(req.question, tuple(req.roles))
    except ValueError as e:  # guardrail-блок — до создания checkpoint
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
