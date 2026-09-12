"""Прогон golden set: качество retrieval, соблюдение прав, точность маршрутизации.

Чем это отличается от тестов. Тесты отвечают «сломано или нет» и обязаны быть
детерминированными. Здесь измеряется **качество**, у которого нет порога «истина»,
зато есть цифра, которую можно сравнивать между версиями. Поэтому прогон выдаёт
отчёт, а не зелёную полоску — и отдельно проверяет гейты, на которых можно
останавливать выкладку ([ADR-0018](../../docs/adr/0018-security-testing.md), урок 13).

**Метрики считаются без LLM.** Context recall и precision выводятся из совпадения
с эталонными пунктами, нарушения ACL — из факта появления закрытого документа,
точность маршрутизации — из решения супервизора. Всё это объективно и
воспроизводимо, в отличие от оценки моделью. LLM-as-a-Judge подключается
опционально (`SUFLER_JUDGE_MODEL`) и только для faithfulness — того единственного,
что без модели не измерить; судья обязан отличаться от отвечающей модели
([ADR-0017](../../docs/adr/0017-observability.md), правило 5: судья ≠ подсудимый).

Попутно закрываются критерии приёмки [ADR-0015](../../docs/adr/0015-topologiya-mas-cifrovye-sotrudniki.md):
точность маршрутизации и **прирост качества мультиагентного пути против
одиночного на одном и том же наборе** — то есть ответ на вопрос, окупается ли
топология, цифрой, а не рассуждением.

    python -m tools.eval --out ../docs/eval/raw.json
"""
import argparse
import json
import os
import sys

import yaml

# Гейты приёмки. ACL — единственный, где порог абсолютный: одно нарушение прав
# это не «качество просело», а инцидент (ADR-0016).
GATES = {
    "acl_violations": 0,
    "context_recall": 0.85,
    "cancellation_pass": 1.0,
    "routing_accuracy_lenient": 0.9,
    # Отказ — такой же результат, как ответ. Без гейта метрика поощряет систему,
    # которая всегда что-нибудь выдаёт: шум с цитатами выглядит работой.
    "refusal_pass": 1.0,
}


def load_golden(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["cases"]


def clause(source: dict) -> tuple:
    """Устойчивый адрес пункта: код документа + номер."""
    return (source.get("doc_code", ""), source.get("ordinal", ""))


def score_case(case: dict, result: dict) -> dict:
    """Метрики одного кейса по выдаче одного из путей."""
    retrieved = [clause(s) for s in result["sources"]]
    expected = [tuple(x) for x in case.get("relevant", [])]

    hit = [c for c in expected if c in retrieved]
    recall = len(hit) / len(expected) if expected else None
    precision = len(hit) / len(retrieved) if retrieved and expected else None

    # Нарушение прав — это чанк ИЗ закрытого документа в выдаче. Проверяется по
    # `doc_code` источников, и этого достаточно: `contexts` параллелен `sources`,
    # то есть контекст модели состоит ровно из тех же чанков.
    #
    # Сканировать текст контекста на код документа — ошибка, и она здесь была:
    # ЛПА-02 § 3.1 легально ссылается на ЛПА-03 по коду («в порядке, установленном
    # ЛПА-03»), и наивная проверка объявляла утечкой ровно то поведение, которого
    # мы добивались. Упоминание существования закрытого документа в разрешённом
    # пункте — не утечка; утечка — его содержимое.
    forbidden = set(case.get("forbidden_docs", []))
    violation = any(s.get("doc_code") in forbidden for s in result["sources"])

    checks = {}
    if case.get("expect_cancellation"):
        checks["cancellation"] = bool(result["graph_notes"])
    if case.get("expect_empty") is True:
        checks["empty"] = not result["sources"]
    elif case.get("expect_empty") is False:
        checks["not_empty_required"] = True   # информативно, гейтом не является

    return {"recall": recall, "precision": precision,
            "acl_violation": violation, "checks": checks,
            "retrieved": ["·".join(c) for c in retrieved]}


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def evaluate(cases: list, engine, platform, judge=None) -> dict:
    rows = []
    for case in cases:
        roles = tuple(case.get("roles", ["all"]))
        rag = engine.answer(case["question"], roles=roles, subject="eval")
        mas = platform.answer(case["question"], roles=roles, subject="eval")

        row = {
            "id": case["id"],
            "roles": list(roles),
            "rag": score_case(case, rag),
            "mas": score_case(case, mas),
            "route": mas["route"],
            "route_expected": case.get("route"),
            "budget": mas["budget"],
        }
        if case.get("route"):
            expected, got = set(case["route"]), set(mas["route"])
            row["routing_exact"] = expected == got
            row["routing_covered"] = expected <= got   # веер шире эталона — не ошибка
        if judge is not None and rag["sources"]:
            row["faithfulness"] = judge(case["question"], rag["contexts"], rag["answer"])
        rows.append(row)

    routed = [r for r in rows if "routing_exact" in r]
    summary = {
        "cases": len(rows),
        "context_recall": {"rag": _mean([r["rag"]["recall"] for r in rows]),
                           "mas": _mean([r["mas"]["recall"] for r in rows])},
        "context_precision": {"rag": _mean([r["rag"]["precision"] for r in rows]),
                              "mas": _mean([r["mas"]["precision"] for r in rows])},
        "acl_violations": sum(r["rag"]["acl_violation"] or r["mas"]["acl_violation"] for r in rows),
        "routing_accuracy_exact": _mean([float(r["routing_exact"]) for r in routed]),
        "routing_accuracy_lenient": _mean([float(r["routing_covered"]) for r in routed]),
        "cost_mas": {
            "steps_per_request": _mean([r["budget"]["steps"] for r in rows]),
            "tool_calls_per_request": _mean([r["budget"]["tool_calls"] for r in rows]),
            "tokens_per_request": _mean([r["budget"]["tokens_estimate"] for r in rows]),
        },
    }

    checks = [(name, ok) for r in rows for name, ok in r["rag"]["checks"].items()
              if name in ("cancellation", "empty")]
    summary["cancellation_pass"] = _mean(
        [float(ok) for name, ok in checks if name == "cancellation"])
    summary["refusal_pass"] = _mean([float(ok) for name, ok in checks if name == "empty"])
    faith = [r["faithfulness"] for r in rows if r.get("faithfulness") is not None]
    summary["faithfulness"] = _mean(faith) if faith else None
    return {"summary": summary, "rows": rows}


def build_judge(settings):
    """LLM-as-a-Judge для faithfulness. Без отдельной модели — не судим вовсе."""
    model = os.getenv("SUFLER_JUDGE_MODEL", "")
    if not model:
        return None
    if model == settings.llm_model and os.getenv("SUFLER_JUDGE_BASE_URL", "") in ("", settings.openai_base_url):
        # Оценка собственного ответа той же моделью систематически завышена:
        # судья и подсудимый — одна сущность (урок 13, ADR-0017 правило 5).
        print("SUFLER_JUDGE_MODEL совпадает с отвечающей моделью — судья отключён",
              file=sys.stderr)
        return None

    from openai import OpenAI
    # Судья может жить на другом эндпоинте: у платформы это отдельный сервинг
    # (например, VL-модель на соседнем порту). Без своей переменной судьёй
    # оказалась бы та же модель на том же адресе — то есть подсудимый.
    base = os.getenv("SUFLER_JUDGE_BASE_URL", settings.openai_base_url)
    client = OpenAI(base_url=base, api_key=settings.openai_api_key)
    system = ("Ты — строгий проверяющий. Ответь одним числом от 0 до 1: какая доля утверждений "
              "ответа подтверждается контекстом. Только число, без пояснений.")

    def judge(question, contexts, answer):
        try:
            r = client.chat.completions.create(
                model=model, temperature=0, max_tokens=8,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": f"Контекст:\n{chr(10).join(contexts)}\n\n"
                                                      f"Вопрос: {question}\nОтвет: {answer}"}])
            return max(0.0, min(1.0, float(r.choices[0].message.content.strip().replace(",", "."))))
        except Exception as e:            # судья недоступен — это не повод ронять прогон
            print(f"судья недоступен: {type(e).__name__}", file=sys.stderr)
            return None

    return judge


def check_gates(summary: dict) -> list:
    """Проверка порогов. Метрики, посчитанные по обоим путям, гейтятся по
    худшему: выкладку нельзя пропускать, если просел хотя бы один из них."""
    failed = []
    for name, threshold in GATES.items():
        value = summary.get(name)
        if isinstance(value, dict):
            value = min(v for v in value.values() if v is not None)
        if value is None:
            continue
        if name == "acl_violations":
            if value > threshold:
                failed.append(f"{name}: {value} > {threshold}")
        elif value < threshold:
            failed.append(f"{name}: {value} < {threshold}")
    return failed


def render(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"Кейсов: {s['cases']}",
        "",
        f"{'метрика':28} {'одиночный':>12} {'мультиагентный':>16}",
        f"{'context recall':28} {str(s['context_recall']['rag']):>12} {str(s['context_recall']['mas']):>16}",
        f"{'context precision':28} {str(s['context_precision']['rag']):>12} {str(s['context_precision']['mas']):>16}",
        "",
        f"нарушений ACL:              {s['acl_violations']}",
        f"пометка об отмене:          {s['cancellation_pass']}",
        f"честный отказ:              {s['refusal_pass']}",
        f"маршрутизация (точно):      {s['routing_accuracy_exact']}",
        f"маршрутизация (с веером):   {s['routing_accuracy_lenient']}",
        f"шагов на запрос:            {s['cost_mas']['steps_per_request']}",
        f"вызовов инструментов:       {s['cost_mas']['tool_calls_per_request']}",
        f"токенов на запрос (оценка): {s['cost_mas']['tokens_per_request']}",
    ]
    if s.get("faithfulness") is not None:
        lines.append(f"faithfulness (судья):       {s['faithfulness']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Прогон golden set по корпусу ЛПА")
    ap.add_argument("--golden", default=os.path.join(os.path.dirname(__file__), "..",
                                                     "eval", "golden.yaml"))
    ap.add_argument("--out", help="куда сложить сырой отчёт (JSON)")
    ap.add_argument("--no-gates", action="store_true", help="не проверять гейты приёмки")
    args = ap.parse_args()

    from sufler.config import settings
    from sufler.mas import Platform
    from sufler.rag import Sufler

    engine = Sufler()
    try:
        report = evaluate(load_golden(args.golden), engine, Platform(engine=engine),
                          build_judge(settings))
    finally:
        engine.close()

    print(render(report))
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nсырой отчёт: {args.out}")

    if not args.no_gates:
        failed = check_gates(report["summary"])
        if failed:
            print("\nГЕЙТЫ НЕ ПРОЙДЕНЫ:\n  " + "\n  ".join(failed), file=sys.stderr)
            sys.exit(1)
        print("\nгейты приёмки пройдены")


if __name__ == "__main__":
    main()
