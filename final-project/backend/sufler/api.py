"""HTTP API: /ask (нативный) · /agents/ask (мультиагентный, ADR-0015) ·
/v1/chat/completions (OpenAI-совместимый — для Open WebUI, ADR-0007)."""
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, make_asgi_app

from .config import settings
from .rag import Sufler

_engine = None
_platform = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Соединение с графом закрывается на остановке сервиса: иначе драйвер Neo4j
    # доживает до сборщика мусора, а пул сокетов — до перезапуска пода.
    global _engine, _platform
    if _engine is not None:
        _engine.close()
    _engine = _platform = None


app = FastAPI(title="Суфлёр MVP", version="0.1", lifespan=lifespan)

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


_verifier = None
_verifier_built = False


def get_verifier():
    """Верификатор JWT или None в dev-режиме (ADR-0016). Строится один раз."""
    global _verifier, _verifier_built
    if not _verifier_built:
        from .auth import build_verifier
        _verifier = build_verifier(settings)
        _verifier_built = True
    return _verifier


def subject_of(request: Request, body_roles=("all",)):
    """Кто спрашивает: (роли, субъект).

    При настроенном Keycloak роли берутся ТОЛЬКО из подписанного токена, а поле
    `roles` в теле запроса не влияет на доступ вообще — не «влияет меньше», а не
    влияет (ADR-0016, урок 26: контекст субъекта из токена, а не из тела).
    """
    verifier = get_verifier()
    if verifier is None:
        return tuple(body_roles), "anonymous"      # dev-режим доверенного контура
    from .auth import AuthError
    try:
        ctx = verifier.context(request.headers.get("authorization", ""))
    except AuthError as e:
        # Наружу — факт отказа, без подробностей о том, какая проверка не прошла.
        raise HTTPException(status_code=401, detail=str(e),
                            headers={"WWW-Authenticate": "Bearer"})
    return ctx.roles, ctx.subject


class AskReq(BaseModel):
    question: str
    # Роли из тела — только для dev-режима и демо без Keycloak. При заданном
    # OIDC_JWKS_URL это поле игнорируется: см. `subject_of`.
    roles: list[str] = ["all"]


@app.get("/healthz")
def healthz():
    # Режим доступа виден снаружи намеренно: dev-режим, о котором не знают, —
    # это открытый контур, который считают закрытым.
    return {"status": "ok", "auth": "jwt" if settings.oidc_jwks_url else "dev"}


@app.get("/graph/stats")
def graph_stats():
    """Статистика графа знаний — для демо и проверки, что ingestion отработал."""
    return get_engine().graph_stats()


@app.post("/ask")
def ask(req: AskReq, request: Request):
    roles, subject = subject_of(request, req.roles)
    try:
        return get_engine().answer(req.question, roles, subject)
    except ValueError as e:  # guardrail-блок
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/agents")
def agents():
    """Штат «цифровых сотрудников»: компетенция, мандат прав, правила маршрутизации."""
    from .config import settings
    from .mas import roster
    return {"enabled": settings.mas_enabled, "agents": roster()}


@app.post("/agents/ask")
def agents_ask(req: AskReq, request: Request):
    """Мультиагентный путь: супервизор → роли-агенты → сведение (ADR-0015).

    Отдельный эндпоинт, а не флаг в /ask: у ответа другой контракт — маршрут,
    ReAct-trace и израсходованный бюджет. Клиент выбирает путь осознанно.
    """
    platform = get_platform()
    roles, subject = subject_of(request, req.roles)
    try:
        return platform.answer(req.question, roles, subject)
    except ValueError as e:  # guardrail-блок — до создания checkpoint
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/v1/chat/completions")
def chat_completions(body: dict, request: Request):
    """Минимальная OpenAI-совместимость — чтобы Open WebUI мог подключить Суфлёр как модель.

    Границу доверия проходит так же, как `/ask`: OpenAI-совместимая обёртка не
    повод для второго, более слабого пути аутентификации (ADR-0011 брал роли из
    `body.user.groups` — здесь этого нет).
    """
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages required")
    roles, subject = subject_of(request)
    question = messages[-1]["content"]
    res = get_engine().answer(question, roles, subject)
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
