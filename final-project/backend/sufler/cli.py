"""CLI: python -m sufler.cli [--roles legal,hr] "вопрос"  либо интерактивно (stdin).

Роли задаются флагом только для локальной отладки и демо. В проде они приходят
исключительно из проверенного JWT (ADR-0016) — CLI не является точкой входа
пользователя и обходит границу доверия осознанно.
"""
import argparse
import sys

from .graph import CANCELLED_BY, CANCELS
from .rag import Sufler

MARKS = {CANCELLED_BY: "  ← ОТМЕНЁН", CANCELS: "  ← действующая редакция"}


def _fmt(res: dict) -> str:
    lines = []
    for s in res["sources"]:
        mark = MARKS.get(s["relation"], "")
        via = f"  [по графу: {s['relation']} ← {s['via']}]" if s["relation"] not in ("ВЕКТОР", *MARKS) else ""
        lines.append(f"  - {s['doc']} · {s['section']}{mark}{via}")
    src = "\n".join(lines) or "  (нет)"
    return f"{res['answer']}\n\nИсточники:\n{src}\n\nrequest_id: {res['request_id']}"


def main():
    ap = argparse.ArgumentParser(description="Суфлёр — GraphRAG по ЛПА")
    ap.add_argument("question", nargs="*", help="вопрос; без него — интерактивный режим")
    ap.add_argument("--roles", default="all", help="роли субъекта через запятую (демо)")
    ap.add_argument("--stats", action="store_true", help="показать статистику графа и выйти")
    args = ap.parse_args()

    eng = Sufler()
    if args.stats:
        print(eng.graph_stats())
        return

    roles = tuple(r.strip() for r in args.roles.split(",") if r.strip())
    if args.question:
        print(_fmt(eng.answer(" ".join(args.question), roles=roles)))
        return

    print(f"Суфлёр готов (роли: {', '.join(roles)}). Введите вопрос (Ctrl-D для выхода):")
    for line in sys.stdin:
        q = line.strip()
        if q:
            print(_fmt(eng.answer(q, roles=roles)))


if __name__ == "__main__":
    main()
