"""Инструментальный слой агентов — единственная дверь «цифрового сотрудника» к знаниям.

Агент не обращается ни к Qdrant, ни к Neo4j напрямую: всё идёт через инструмент,
и сужение прав (least privilege, ADR-0015 правило 2) выполняется **здесь**, а не
в промпте. Промпт — это текст, его можно переубедить; пересечение множеств ролей
переубедить нельзя. ACL-предикат при этом остаётся там же, где был: на каждом
узле обхода графа (ADR-0016) — инструмент только сообщает ему суженный контекст.

Все инструменты MVP — **read-only**. Мутирующая операция по ADR-0015 (правило 6)
требует подтверждения оператора (HITL) и в этот слой без него не добавляется.
"""
from .access import RequestContext


class GraphSearchTool:
    """GraphRAG-поиск от имени роли-агента: vector-first → обход графа → rerank."""

    name = "graph_search"

    def __init__(self, retriever):
        self.retriever = retriever

    def __call__(self, query: str, role, ctx: RequestContext):
        """Возвращает (найденное, фактические права) — права попадают в trace и аудит."""
        effective = role.effective_roles(ctx.roles)
        # Контекст пересобирается с суженными ролями, но с тем же request_id:
        # шаги одного обращения обязаны сшиваться в журнале (ADR-0016, инвариант 6).
        scoped = RequestContext.of(effective, subject=ctx.subject, request_id=ctx.request_id)
        return self.retriever.search(query, scoped), effective

    def signature(self, query: str, effective) -> str:
        """Строка вызова для ReAct-trace — то, что увидит оператор в Jaeger и в UI."""
        return f'{self.name}(query="{query}", roles={list(effective)})'
