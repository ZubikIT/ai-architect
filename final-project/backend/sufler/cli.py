"""CLI: python -m sufler.cli [--mas] [--trace] [--roles legal,hr] "вопрос" либо интерактивно.

Роли задаются флагом только для локальной отладки и демо. В проде они приходят
исключительно из проверенного JWT (ADR-0016) — CLI не является точкой входа
пользователя и обходит границу доверия осознанно.
"""
import argparse
import sys

from .graph import CANCELLED_BY, CANCELS
from .rag import Sufler

MARKS = {CANCELLED_BY: "  ← ОТМЕНЁН", CANCELS: "  ← действующая редакция"}


def _fmt(res: dict, show_trace: bool = False) -> str:
    lines = []
    for s in res["sources"]:
        mark = MARKS.get(s["relation"], "")
        via = f"  [по графу: {s['relation']} ← {s['via']}]" if s["relation"] not in ("ВЕКТОР", *MARKS) else ""
        who = f"  ({s['agent']})" if s.get("agent") else ""
        lines.append(f"  - {s['doc']} · {s['section']}{mark}{via}{who}")
    src = "\n".join(lines) or "  (нет)"
    out = f"{res['answer']}\n\nИсточники:\n{src}"

    if "route" in res:      # мультиагентный путь
        staff = ", ".join(f"{a['title']} → {a['found']} п. правами {a['effective_roles']}"
                          for a in res["agents"]) or "(никто не опрошен)"
        b = res["budget"]
        out += (f"\n\nМаршрут ({res['routing']['mode']}, уверенность "
                f"{res['routing']['confidence']}): {staff}"
                f"\nБюджет: шагов {b['steps']}, вызовов инструментов {b['tool_calls']}, "
                f"~{b['tokens_estimate']} токенов" + (f" · {b['degraded']}" if b["degraded"] else ""))
        if show_trace:
            # ReAct-trace: то же, что уйдёт в трейсы OTel и в видео-демо (ADR-0015).
            steps = "\n".join(
                f"  [{t['step']}] {t.get('agent_title') or t['agent']}\n"
                f"      Thought: {t['thought']}\n"
                f"      Action: {t['action']}\n"
                f"      Observation: {t['observation']}" for t in res["trace"])
            out += f"\n\nReAct-trace:\n{steps}"

    return out + f"\n\nrequest_id: {res['request_id']}"


def _run(args, eng):
    if args.stats:
        print(eng.graph_stats())
        return

    if args.mas:
        from .mas import Platform
        eng = Platform(engine=eng)   # тот же индекс и тот же граф, другой путь исполнения

    roles = tuple(r.strip() for r in args.roles.split(",") if r.strip())
    if args.question:
        print(_fmt(eng.answer(" ".join(args.question), roles=roles), args.trace))
        return

    who = "Платформа цифровых сотрудников" if args.mas else "Суфлёр"
    print(f"{who} готова (роли: {', '.join(roles)}). Введите вопрос (Ctrl-D для выхода):")
    for line in sys.stdin:
        q = line.strip()
        if q:
            print(_fmt(eng.answer(q, roles=roles), args.trace))


def main():
    ap = argparse.ArgumentParser(description="Суфлёр — GraphRAG по ЛПА")
    ap.add_argument("question", nargs="*", help="вопрос; без него — интерактивный режим")
    ap.add_argument("--roles", default="all", help="роли субъекта через запятую (демо)")
    ap.add_argument("--stats", action="store_true", help="показать статистику графа и выйти")
    ap.add_argument("--mas", action="store_true",
                    help="мультиагентный путь: супервизор + роли-агенты (ADR-0015)")
    ap.add_argument("--trace", action="store_true", help="показать ReAct-trace (с --mas)")
    args = ap.parse_args()

    eng = Sufler()
    try:
        _run(args, eng)
    finally:
        eng.close()   # драйвер графа закрывает тот, кто его открыл


if __name__ == "__main__":
    main()
