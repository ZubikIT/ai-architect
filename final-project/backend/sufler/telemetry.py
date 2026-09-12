"""Единый слой наблюдаемости: спаны OpenTelemetry + доменные метрики (ADR-0017).

Три вещи, которые здесь сделаны намеренно и стоят объяснения.

**`trace_id` = `request_id`.** ADR-0017 требует сшить трейс, журнал доступа и
запись в Langfuse одним ключом. `request_id` — это `uuid4().hex`, то есть ровно
те же 128 бит, что и `trace_id` OpenTelemetry, поэтому идентификатор не
«прокидывается атрибутом», а **становится** идентификатором трейса. На защите это
один жест: `request_id` из ответа вставляется в поиск Jaeger и открывает трейс.
Цена — собственный генератор идентификаторов и отказ от авто-инструментации
FastAPI: её серверный спан открывается раньше, чем известен `request_id`.

**Содержимое запроса в трейс не попадает** — ни вопрос, ни контекст, ни ответ.
Спан с промптом внутри содержит фрагменты ЛПА и ПДн, а Jaeger в контуре доступен
шире, чем сами документы ([Data Flow](../../docs/diagrams/data-flow.md): трейсы —
поверхность утечки). `SUFLER_OTEL_CONTENT=1` включает текст для отладки, и тогда
он проходит через ту же PII-маску, что и ответ пользователю. Страховка — обёртка
над экспортёром: маска применяется ко всем строковым атрибутам **до** отправки,
что бы ни записал вызывающий код.

**Без эндпоинта ничего не экспортируется.** Спаны создаются всегда (дёшево), но
уходят только при заданном `OTEL_EXPORTER_OTLP_ENDPOINT`. Офлайн-демо и тесты не
требуют ни коллектора, ни сети.
"""
import contextlib
import threading
from contextvars import ContextVar

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from prometheus_client import Counter, Histogram

from .config import settings
from .guardrails import mask_pii

_current_request_id: ContextVar[str] = ContextVar("sufler_request_id", default="")
_setup_lock = threading.Lock()
_provider = None


# --------------------------------------------------------------------------- #
#  Метрики (ADR-0017: Golden Signals в api.py, доменные — здесь)
# --------------------------------------------------------------------------- #
# Ключевая метрика проекта: доля ответов, где сработало ребро ОТМЕНЯЕТ. Это
# числовое доказательство пользы GraphRAG, а не декларация — при нулевом
# значении граф в проде не работает, как бы хорошо он ни выглядел на демо.
ANSWERS = Counter("sufler_answers_total", "Ответы платформы",
                  ["path", "graph_contribution", "cancellation"])
GRAPH_EXPAND = Histogram("sufler_graph_expand_seconds", "Время обхода графа, с",
                         ["backend"], buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2))
GRAPH_HOPS = Histogram("sufler_graph_expansions", "Связанных пунктов добавлено обходом",
                       buckets=(0, 1, 2, 3, 5, 8, 13))
# Две причины пустого ответа, и их нельзя смешивать: «прав не хватило» и «вопрос
# не про наш корпус» требуют разных действий от эксплуатации. Обе считаются в
# ретривере — только он знает, что именно отсекло выдачу.
ACL_DENIALS = Counter("sufler_acl_denials_total", "Запросы, где права не оставили ни одного пункта")
LOW_RELEVANCE = Counter("sufler_low_relevance_total", "Запросы, отсечённые порогом релевантности")
GUARDRAIL_BLOCKS = Counter("sufler_guardrail_blocks_total", "Срабатывания guardrails", ["stage"])
AUTH_FAILURES = Counter("sufler_auth_failures_total", "Отклонённые токены", ["reason"])
AGENT_STEPS = Histogram("sufler_agent_steps", "Шагов агентов на запрос",
                        buckets=(0, 1, 2, 3, 4, 6, 8))
AGENT_TOOL_CALLS = Counter("sufler_agent_tool_calls_total", "Вызовы инструментов", ["agent"])
AGENT_LIMIT_HITS = Counter("sufler_agent_limit_hits_total", "Срабатывания лимитов MAS")
ROUTING = Counter("sufler_routing_total", "Решения супервизора", ["mode", "agent"])


# --------------------------------------------------------------------------- #
#  Трейсинг
# --------------------------------------------------------------------------- #
class RequestIdGenerator(RandomIdGenerator):
    """`trace_id` корневого спана берётся из `request_id`, если он задан."""

    def generate_trace_id(self) -> int:
        rid = _current_request_id.get()
        if rid:
            try:
                value = int(rid, 16)
                if value:            # trace_id = 0 недопустим по спецификации
                    return value
            except ValueError:
                pass                 # не hex — падать на этом незачем, будет случайный
        return super().generate_trace_id()


class PiiScrubbingExporter(SpanExporter):
    """Маска ПДн поверх любого экспортёра (ADR-0017, правило 1: санитизация
    выполняется в процессе приложения, а не в бэкенде).

    Завершённый спан неизменяем: его атрибуты — `BoundedAttributes`, и попытка
    записи в них поднимает `TypeError`, который процессор проглатывает, оставляя
    ПДн в трейсе. Поэтому спан не правится, а **пересобирается**: новый
    `ReadableSpan` с теми же метаданными и промаскированными строками. Это
    страховка на случай, если вызывающий код записал текст напрямую, минуя
    `content()` — санитизация не должна зависеть от дисциплины вызывающего.
    """

    def __init__(self, inner: SpanExporter):
        self._inner = inner

    @staticmethod
    def _scrub(value):
        if isinstance(value, str):
            return mask_pii(value)
        if isinstance(value, (list, tuple)):
            return type(value)(PiiScrubbingExporter._scrub(v) for v in value)
        return value

    def export(self, spans):
        return self._inner.export([self._rebuild(span) for span in spans])

    def _rebuild(self, span):
        attrs = {k: self._scrub(v) for k, v in (span.attributes or {}).items()}
        events = [Event(e.name, {k: self._scrub(v) for k, v in (e.attributes or {}).items()},
                        e.timestamp) for e in span.events]
        if not attrs and not events:
            return span                      # нечего маскировать — лишних объектов не создаём
        return ReadableSpan(
            name=span.name, context=span.context, parent=span.parent,
            resource=span.resource, attributes=attrs, events=events, links=span.links,
            kind=span.kind, status=span.status, start_time=span.start_time,
            end_time=span.end_time, instrumentation_scope=span.instrumentation_scope,
        )

    def shutdown(self):
        return self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def setup(exporter: SpanExporter = None, cfg=settings) -> None:
    """Идемпотентная настройка провайдера. `exporter` — точка входа для тестов."""
    global _provider
    with _setup_lock:
        if _provider is not None:
            return
        _provider = TracerProvider(
            resource=Resource.create({"service.name": cfg.otel_service_name}),
            id_generator=RequestIdGenerator(),
        )
        if exporter is None and cfg.otel_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=cfg.otel_endpoint, insecure=True)
        if exporter is not None:
            _provider.add_span_processor(BatchSpanProcessor(PiiScrubbingExporter(exporter)))
        # Глобальный провайдер OpenTelemetry ставится один раз за процесс и молча
        # игнорирует повторную установку. Поэтому собственные спаны берутся прямо
        # из `_provider` (см. `tracer()`), а глобальный нужен лишь сторонним
        # инструментациям — и его переустановка не должна ломать наш путь.
        trace.set_tracer_provider(_provider)


def reset_for_tests() -> None:
    """Сброс глобального состояния — только для тестов."""
    global _provider
    with _setup_lock:
        if _provider is not None:
            _provider.shutdown()
        _provider = None


def tracer():
    if _provider is None:
        setup()
    return _provider.get_tracer("sufler")


@contextlib.contextmanager
def request_span(name: str, request_id: str, **attrs):
    """Корневой спан обращения: именно здесь `request_id` становится `trace_id`."""
    token = _current_request_id.set(request_id)
    try:
        with tracer().start_as_current_span(name) as span:
            span.set_attribute("request_id", request_id)
            _apply(span, attrs)
            yield span
    finally:
        _current_request_id.reset(token)


@contextlib.contextmanager
def span(name: str, **attrs):
    with tracer().start_as_current_span(name) as sp:
        _apply(sp, attrs)
        yield sp


def _apply(span, attrs: dict) -> None:
    for key, value in attrs.items():
        # Пустая строка — это выключенный `content()`: атрибута быть не должно,
        # иначе трейс засоряется пустыми полями.
        if value is None or value == "":
            continue
        span.set_attribute(key, value if isinstance(value, (bool, int, float, str)) else str(value))


def content(text: str) -> str:
    """Текст для спана: пусто, пока `SUFLER_OTEL_CONTENT` не включён явно."""
    if not settings.otel_capture_content:
        return ""
    return mask_pii(text or "")
