"""CLI: python -m sufler.cli "вопрос"  либо интерактивно (stdin)."""
import sys

from .rag import Sufler


def _fmt(res: dict) -> str:
    src = "\n".join(f"  - {s['doc']} · {s['section']}" for s in res["sources"]) or "  (нет)"
    return f"{res['answer']}\n\nИсточники:\n{src}"


def main():
    eng = Sufler()
    args = sys.argv[1:]
    if args:
        print(_fmt(eng.answer(" ".join(args))))
        return
    print("Суфлёр готов. Введите вопрос (Ctrl-D для выхода):")
    for line in sys.stdin:
        q = line.strip()
        if q:
            print(_fmt(eng.answer(q)))


if __name__ == "__main__":
    main()
