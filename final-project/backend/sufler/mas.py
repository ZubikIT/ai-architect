"""Мультиагентный слой: супервизор + роли-агенты на LangGraph (ADR-0015).

Это ответ на критичное требование ТЗ «LangGraph или аналог state machine, а не
линейные цепочки». Линейного пути здесь нет: есть состояние (досье запроса),
ветвление супервизора, цикл «супервизор → сотрудник → супервизор» с лимитами и
checkpoint'ами, и терминальное сведение.

    START → supervisor ──(есть кому поручить)──→ worker ──┐
              │                                            │
              └──(очередь пуста | лимит исчерпан)──→ synthesize → END
                                     ▲                     │
                                     └─────────────────────┘

Конструктивные инварианты (ADR-0015):

1. **Супервизор детерминирован** там, где может быть: маршрутизация правилами,
   LLM-классификация — только для запросов, не попавших ни в одно правило.
2. **Роль = промпт + инструменты + права**; сужение прав выполняет инструмент
   ([`tools.py`](tools.py)), а не доверие к промпту.
3. **Агенты не общаются напрямую.** Обмен — через общее досье (`Dossier`),
   которое читает и пишет супервизор. Канала «агент → агент» нет, значит нет и
   поверхности ASI07.
4. **Состояние — в checkpointer**, ключ — `request_id`: разбор инцидента
   воспроизводим по шагам.
5. **Жёсткие лимиты** шагов, вызовов инструментов и токенов; при исчерпании —
   явная деградация с объяснением, а не молчаливый обрыв (LLM06, ASI08).
6. **ReAct-trace виден**: Thought → Action → Observation по каждому шагу
   (рекомендация ревьюера ДЗ-07).
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import telemetry
from .access import RequestContext
from .config import settings
from .guardrails import check_input, mask_pii
from .rag import ANSWER_RULES, NO_ANSWER, Sufler, build_context
from .roles import DEFAULT_ROLE, ROLE_BY_ID, ROLES, ROUTING_SYSTEM, route_by_rules
from .tools import GraphSearchTool

SUPERVISOR_SYSTEM = (
    "Ты — супервизор платформы цифровых сотрудников. Тебе переданы выводы специалистов "
    "по одному вопросу. Сведи их в один связный ответ, НЕ добавляя фактов от себя и не "
    "убирая предупреждений об отменённых нормах. Укажи, какой специалист что установил. "
    + ANSWER_RULES
)

# Грубая оценка длины в токенах: считать точно нечем в офлайн-режиме, а бюджет
# нужен именно как потолок, а не как учёт. Для кириллицы ~2.5 символа на токен.
_CHARS_PER_TOKEN = 2.5

_STOPWORDS = {"как", "что", "какой", "какая", "какие", "где", "когда", "нужно", "можно",
              "ли", "для", "это", "мне", "при", "если", "или", "быть", "есть"}


def _tokens(text: str) -> int:
    return int(len(text) / _CHARS_PER_TOKEN)


def _keyword_query(question: str) -> str:
    """Переформулировка второй попытки: вопрос → ключевые слова.

    Без LLM: у векторного поиска вопросительная обвязка («как», «какой порядок»)
    только размывает эмбеддинг, и снятие её иногда достаётся дешевле, чем вызов
    модели. Если и это не помогло — агент честно возвращает пустую находку.
    """
    words = [w.strip(".,;:!?»«()") for w in question.lower().split()]
    keep = [w for w in words if len(w) > 3 and w not in _STOPWORDS]
    return " ".join(keep) or question


def build_checkpointer(cfg=settings):
    """PostgreSQL в проде, in-memory без DATABASE_URL (ADR-0015, правило 4)."""
    if cfg.database_url:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            saver = PostgresSaver.from_conn_string(cfg.database_url)
            saver.setup()
            return saver
        except ImportError:
            # Пакет langgraph-checkpoint-postgres не поставлен — работаем без
            # долговечного состояния, но говорим об этом вслух: молчаливая потеря
            # воспроизводимости хуже отсутствующей зависимости.
            import warnings
            warnings.warn("DATABASE_URL задан, но langgraph-checkpoint-postgres "
                          "не установлен — состояние MAS остаётся в памяти процесса")
    from langgraph.checkpoint.memory import InMemorySaver
    return InMemorySaver()


class Dossier(TypedDict):
    """Общее досье запроса — единственный канал обмена между «сотрудниками».

    Все поля сериализуемы (dict/list/str/int): состояние обязано ложиться в
    checkpointer PostgreSQL, а не только в память процесса.
    """
    question: str
    subject: str
    roles: list
    request_id: str
    routing: dict
    pending: list      # очередь id ролей, которым поручено
    findings: list     # что установил каждый «сотрудник»
    trace: list        # ReAct-trace: Thought → Action → Observation
    steps: int
    tool_calls: int
    tokens: int
    degraded: str      # причина неполного ответа, если лимит исчерпан
    answer: str
    sources: list
    contexts: list
    graph_notes: list


class Platform:
    """«Цифровые сотрудники» над GraphRAG-ядром.

    Ядро (`Sufler`) переиспользуется целиком: индекс, граф и ACL-инварианты у
    одиночного ассистента и у мультиагентного слоя общие — иначе пришлось бы
    доказывать безопасность дважды.
    """

    def __init__(self, engine: Sufler = None, checkpointer=None):
        self.engine = engine or Sufler()
        self.llm = self.engine.llm
        self.tool = GraphSearchTool(self.engine.retriever)
        self.checkpointer = checkpointer or build_checkpointer(settings)
        self.app = self._build().compile(checkpointer=self.checkpointer)

    # ------------------------------------------------------------------ граф
    def _build(self) -> StateGraph:
        g = StateGraph(Dossier)
        g.add_node("supervisor", self._supervisor)
        g.add_node("worker", self._worker)
        g.add_node("synthesize", self._synthesize)
        g.add_edge(START, "supervisor")
        g.add_conditional_edges("supervisor", self._dispatch,
                                {"worker": "worker", "synthesize": "synthesize"})
        g.add_edge("worker", "supervisor")   # цикл: сотрудник всегда возвращает управление
        g.add_edge("synthesize", END)
        return g

    @staticmethod
    def _dispatch(state: Dossier) -> str:
        """Единственное ветвление: есть ли ещё кому поручить. Решение о лимитах
        принял супервизор — условное ребро не пишет состояние и потому не может
        быть местом, где лимит «потеряется»."""
        return "worker" if state["pending"] else "synthesize"

    # ----------------------------------------------------------------- узлы
    def _supervisor(self, state: Dossier) -> dict:
        upd = {}
        if not state["routing"]:
            upd.update(self._route(state))

        pending = upd.get("pending", state["pending"])
        if pending:
            reason = self._limit_hit(state)
            if reason:
                # Деградация — это решение, а не авария: снимаем очередь и идём
                # сводить то, что уже найдено, назвав причину пользователю.
                waiting = [ROLE_BY_ID[r].title for r in pending]
                telemetry.AGENT_LIMIT_HITS.inc()
                upd["pending"] = []
                upd["degraded"] = f"{reason}; не опрошены: {', '.join(waiting)}"
                upd["trace"] = state["trace"] + [{
                    "step": state["steps"], "agent": "supervisor",
                    "thought": f"Лимит исчерпан ({reason}) — дальше не иду",
                    "action": "stop()", "observation": upd["degraded"],
                }]
        return upd

    @staticmethod
    def _limit_hit(state: Dossier) -> str:
        """Какой потолок уже достигнут. Проверяется перед каждой выдачей поручения,
        а не после — иначе лимит узнаётся уже потраченным."""
        if state["steps"] >= settings.mas_max_steps:
            return f"исчерпан лимит шагов ({settings.mas_max_steps})"
        if state["tool_calls"] >= settings.mas_max_tool_calls:
            return f"исчерпан лимит вызовов инструментов ({settings.mas_max_tool_calls})"
        if state["tokens"] >= settings.mas_token_budget:
            return f"исчерпан бюджет токенов ({settings.mas_token_budget})"
        return ""

    def _route(self, state: Dossier) -> dict:
        """Маршрутизация: правила → (при промахе) LLM → роль по умолчанию."""
        with telemetry.span("supervisor.route") as sp:
            decision = route_by_rules(state["question"], settings.mas_fanout)
            if not decision["route"]:
                decision = self._route_by_llm(state["question"], decision)
            sp.set_attribute("mode", decision["mode"])
            sp.set_attribute("confidence", decision["confidence"])
            sp.set_attribute("route", ",".join(decision["route"]))
        for agent in decision["route"]:
            telemetry.ROUTING.labels(decision["mode"], agent).inc()

        titles = ", ".join(ROLE_BY_ID[r].title for r in decision["route"])
        trace = state["trace"] + [{
            "step": 0, "agent": "supervisor",
            "thought": f"Классифицирую запрос ({decision['mode']}, "
                       f"уверенность {decision['confidence']})",
            "action": f"route({decision['route']})",
            "observation": f"поручено: {titles}",
        }]
        return {"routing": decision, "pending": list(decision["route"]), "trace": trace}

    def _route_by_llm(self, question: str, decision: dict) -> dict:
        """Запасной путь классификации. Ответ модели валидируется по списку ролей:
        сгенерированный идентификатор не становится маршрутом только потому, что
        он сгенерирован (ASI01 — манипуляция целями агента)."""
        if self.llm:
            try:
                raw = (self.llm.chat(ROUTING_SYSTEM, question) or "").strip().lower()
                picked = next((r.id for r in ROLES if r.id in raw), None)
                if picked:
                    return {**decision, "mode": "llm", "route": [picked], "confidence": 0.5}
            except Exception as e:      # недоступный LLM не должен ронять маршрутизацию
                decision = {**decision, "llm_error": type(e).__name__}
        return {**decision, "mode": "default", "route": [DEFAULT_ROLE], "confidence": 0.0}

    def _worker(self, state: Dossier) -> dict:
        """Один «цифровой сотрудник»: Thought → Action (инструмент) → Observation."""
        role = ROLE_BY_ID[state["pending"][0]]
        ctx = RequestContext.of(state["roles"], state["subject"], state["request_id"])
        step = state["steps"] + 1
        trace, calls = list(state["trace"]), state["tool_calls"]
        query, found, effective = state["question"], [], ()

        with telemetry.span(f"agent.{role.id}", agent_title=role.title, step=step) as sp:
            for attempt in range(1, role.max_tool_calls + 1):
                if calls >= settings.mas_max_tool_calls:
                    break
                with telemetry.span("tool.graph_search", agent=role.id, attempt=attempt) as tsp:
                    found, effective = self.tool(query, role, ctx)
                    tsp.set_attribute("effective_roles", ",".join(effective))
                    tsp.set_attribute("found", len(found))
                telemetry.AGENT_TOOL_CALLS.labels(role.id).inc()
                calls += 1
                trace.append({
                    "step": step, "agent": role.id, "agent_title": role.title,
                    "thought": (f"Вопрос в моей компетенции; ищу в графе ЛПА правами {list(effective)}"
                                if attempt == 1 else
                                "Первая попытка пуста — переформулирую запрос ключевыми словами"),
                    "action": self.tool.signature(query, effective),
                    "observation": (f"найдено пунктов: {len(found)}" if found
                                    else "ничего доступного не найдено"),
                })
                if found:
                    break
                query = _keyword_query(state["question"])

            # ReAct-шаг ложится в трейс теми же тремя полями, что и в UI, — событием
            # спана, а не атрибутом: шагов у сотрудника может быть несколько.
            for entry in trace[len(state["trace"]):]:
                sp.add_event("react", {"thought": entry["thought"], "action": entry["action"],
                                       "observation": entry["observation"]})
            sp.set_attribute("effective_roles", ",".join(effective))
            sp.set_attribute("found", len(found))

        blocks, sources, contexts, notes = build_context(found)
        draft = self._draft(role, state["question"], blocks) if found else ""
        finding = {"agent": role.id, "title": role.title,
                   "effective_roles": list(effective), "draft": draft,
                   "blocks": blocks, "sources": sources,
                   "contexts": contexts, "notes": notes}

        return {
            "pending": state["pending"][1:],
            "findings": state["findings"] + [finding],
            "trace": trace,
            "steps": step,
            "tool_calls": calls,
            "tokens": state["tokens"] + _tokens("".join(blocks) + draft),
        }

    def _draft(self, role, question: str, blocks: list) -> str:
        """Вывод одного сотрудника. Промпт роли + общие правила ответа."""
        context = "\n\n".join(blocks)
        if self.llm:
            with telemetry.span("llm.generate", agent=role.id, model=settings.llm_model,
                                context_chars=len(context)):
                return self.llm.chat(role.mission + " " + ANSWER_RULES,
                                     f"Контекст:\n{context}\n\nВопрос: {question}")
        return f"(демо без LLM) {role.title}, наиболее релевантный пункт:\n\n{blocks[0]}"

    def _synthesize(self, state: Dossier) -> dict:
        """Супервизор сводит досье в один ответ и снимает дубли источников."""
        with telemetry.span("supervisor.synthesize", findings=len(state["findings"])) as sp:
            result = self._merge_dossier(state)
            sp.set_attribute("sources", len(result["sources"]))
            sp.set_attribute("cancellation_flagged", bool(result["graph_notes"]))
            return result

    def _merge_dossier(self, state: Dossier) -> dict:
        blocks, sources, contexts, notes, owner = [], [], [], [], {}
        seen = set()
        for f in state["findings"]:
            for b, s, c in zip(f["blocks"], f["sources"], f["contexts"]):
                if s["chunk_id"] in seen:
                    continue           # один пункт, найденный двумя ролями, — один источник
                seen.add(s["chunk_id"])
                owner[s["chunk_id"]] = f["agent"]
                blocks.append(b)
                sources.append({**s, "agent": f["agent"]})
                contexts.append(c)
            notes.extend(f["notes"])

        drafts = [f for f in state["findings"] if f["draft"]]
        if not drafts:
            answer = NO_ANSWER
        elif len(drafts) == 1:
            # Один сотрудник — сводить нечего. Лишний вызов LLM здесь был бы
            # платой за симметрию схемы, а не за качество ответа (ADR-0015: цена
            # топологии обязана окупаться).
            answer = drafts[0]["draft"]
        else:
            answer = self._merge(state["question"], drafts)

        notes = list(dict.fromkeys(notes))
        if notes:
            answer += "\n\n⚠️ " + "; ".join(notes) + "."
        if state["degraded"]:
            answer += f"\n\nℹ️ Ответ неполный: {state['degraded']}."

        trace = state["trace"] + [{
            "step": state["steps"] + 1, "agent": "supervisor",
            "thought": f"Свожу выводы ({len(drafts)} из {len(state['findings'])} с находками)",
            "action": f"synthesize(sources={len(sources)})",
            "observation": f"ответ готов, пометок об отменах: {len(notes)}",
        }]
        return {"answer": mask_pii(answer),      # output-guardrail — последним, над сводкой
                "sources": sources, "contexts": contexts, "graph_notes": notes,
                "trace": trace}

    def _merge(self, question: str, drafts: list) -> str:
        sections = "\n\n".join(f"{d['title']}: {d['draft']}" for d in drafts)
        if self.llm:
            with telemetry.span("llm.merge", model=settings.llm_model, drafts=len(drafts)):
                return self.llm.chat(SUPERVISOR_SYSTEM,
                                     f"Вопрос: {question}\n\nВыводы:\n{sections}")
        return sections

    # ------------------------------------------------------------------ API
    def answer(self, question: str, roles=("all",), subject: str = "anonymous") -> dict:
        # Guardrail — до запуска графа: отклонённый запрос не должен создавать
        # checkpoint. Иначе отравленный ввод осел бы в долговечном состоянии и
        # вернулся при возобновлении потока (ASI06 — отравление памяти).
        try:
            check_input(question)
        except ValueError:
            telemetry.GUARDRAIL_BLOCKS.labels("input").inc()
            raise
        ctx = RequestContext.of(roles, subject)

        init: Dossier = {
            "question": question, "subject": ctx.subject, "roles": list(ctx.roles),
            "request_id": ctx.request_id, "routing": {}, "pending": [],
            "findings": [], "trace": [], "steps": 0, "tool_calls": 0, "tokens": 0,
            "degraded": "", "answer": "", "sources": [], "contexts": [], "graph_notes": [],
        }
        # thread_id = request_id: состояние обращения адресуется тем же ключом,
        # что и записи аудита, и тем же — трейс в Jaeger (ADR-0017).
        with telemetry.request_span("agents.ask", ctx.request_id, path="mas",
                                    subject=ctx.subject, roles=",".join(ctx.roles),
                                    question=telemetry.content(question)) as root:
            final = self.app.invoke(init, config={"configurable": {"thread_id": ctx.request_id}})

            telemetry.AGENT_STEPS.observe(final["steps"])
            root.set_attribute("route", ",".join(final["routing"].get("route", [])))
            root.set_attribute("steps", final["steps"])
            root.set_attribute("tool_calls", final["tool_calls"])
            root.set_attribute("tokens_estimate", final["tokens"])
            root.set_attribute("degraded", final["degraded"] or "")
            if final["sources"]:
                from_graph = any(s["relation"] != "ВЕКТОР" for s in final["sources"])
                Sufler._record(root, "mas", final["sources"], from_graph,
                               bool(final["graph_notes"]))
            else:
                root.set_attribute("outcome", "no_answer")

        return {
            "answer": final["answer"],
            "sources": final["sources"],
            "contexts": final["contexts"],
            "graph_notes": final["graph_notes"],
            "request_id": ctx.request_id,
            "route": final["routing"].get("route", []),
            "routing": final["routing"],
            "trace": final["trace"],
            "agents": [{"id": f["agent"], "title": f["title"],
                        "effective_roles": f["effective_roles"],
                        "found": len(f["sources"])} for f in final["findings"]],
            "budget": {"steps": final["steps"], "tool_calls": final["tool_calls"],
                       "tokens_estimate": final["tokens"], "degraded": final["degraded"]},
        }

    def graph_stats(self):
        return self.engine.graph_stats()


def roster() -> list:
    """Штат «цифровых сотрудников» — для /agents и для демо."""
    return [{"id": r.id, "title": r.title, "grants": list(r.grants),
             "keywords": list(r.keywords)} for r in ROLES]
