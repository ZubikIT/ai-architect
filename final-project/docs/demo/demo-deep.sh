#!/usr/bin/env bash
# Третье действие: то, что нельзя показать кликами — замеры, на которых стоят
# архитектурные решения. Deep Dive в смысле ТЗ.
#
#   asciinema rec --cols 100 --rows 34 -c "bash final-project/docs/demo/demo-deep.sh" \
#       final-project/docs/demo/demo-deep.cast
#
# Требует развёрнутого стека (Neo4j и PostgreSQL из профиля core) и доступа к
# шлюзу моделей. Замеры настоящие и считаются в кадре — ни одна цифра здесь не
# зачитывается из файла, кроме отчёта о прогоне гейтов, который честно помечен
# как сохранённый.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/../../.."
BACKEND="$ROOT/final-project/backend"
INFRA="$ROOT/final-project/infra"
GW="${GW:-http://10.100.1.200:80}"

B=$'\e[1m'; C=$'\e[36m'; G=$'\e[32m'; Y=$'\e[33m'; D=$'\e[2m'; N=$'\e[0m'
say()  { printf "\n${B}${C}%s${N}\n" "$*"; sleep 1.2; }
note() { printf "${D}# %s${N}\n" "$*"; sleep 0.8; }
cmd()  { printf "\n${G}\$ %s${N}\n" "$*"; sleep 0.9; }

cd "$BACKEND"
DSN="$(sudo docker compose -f "$INFRA/docker-compose.yml" exec -T backend env 2>/dev/null \
      | grep '^DATABASE_URL=' | cut -d= -f2- | sed 's/@postgres:/@localhost:/')"
set -a; . "$INFRA/.env" 2>/dev/null; set +a
export NEO4J_URI=bolt://localhost:7687 QDRANT_URL=http://localhost:6333 \
       SUFLER_GRAPH_DSN="$DSN" PYTHONWARNINGS=ignore

clear
printf "${B}${C}Под капотом: замеры, на которых стоят решения${N}\n"
note "ни одной цифры из презентации — всё считается здесь и сейчас"

say "1. Какие веса на самом деле отвечают"
cmd "curl -s \$GW/v1/models | jq '.data[] | {id, root}'"
curl -s -m 15 "$GW/v1/models" | jq -c '.data[] | {id, root}'
sleep 1.5
note "два идентификатора — одни веса: zubr-2 это продуктовое имя того же файла"
note "имена живут своей жизнью: сегодня утром здесь был алиас qwen3.6-35b"
cmd "curl -s \$GW/v1/chat/completions -d '{\"model\":\"qwen3.6-35b\", ...}'"
curl -s -m 30 -X POST "$GW/v1/chat/completions" -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.6-35b","messages":[{"role":"user","content":"ок"}],"max_tokens":5}' \
  | jq -c '.error | {message, code}'
sleep 1.5
note "его переименовали — и всякий, кто просил модель по имени, получил 404"
note "вывод: имя модели не идентифицирует веса и не гарантирует даже своего существования"
note "источник истины — поле root, и только оно"

say "2. Смена весов: перемер, а не допущение"
note "все цифры приёмки сняты до обновления модели — значит их надо перемерить"
note "ниже сохранённый отчёт прогона в развёрнутой конфигурации"
cmd "python3 - < docs/eval/raw-qwen38.json    # сравнение с прогоном до свопа"
python3 - <<'PY'
import json, pathlib
d = pathlib.Path("../docs/eval")
old = json.load(open(d / "raw-rerank-local.json"))["summary"]
new = json.load(open(d / "raw-qwen38.json"))["summary"]
def g(s, *k):
    for kk in k:
        s = s.get(kk, {}) if isinstance(s, dict) else {}
    return s if isinstance(s, (int, float)) else float("nan")
rows = [("context recall", ("context_recall", "rag")),
        ("context precision", ("context_precision", "rag")),
        ("нарушений ACL", ("acl_violations",)),
        ("пометка об отмене", ("cancellation_pass",)),
        ("маршрутизация", ("routing_accuracy_exact",)),
        ("токенов на запрос", ("cost_mas", "tokens_per_request"))]
print(f"  {'метрика':22} {'MoE 3.6':>10} {'dense 3.8':>10}")
for name, path in rows:
    a, b = g(old, *path), g(new, *path)
    mark = "" if abs(a - b) < 1e-6 else "   ← изменилось"
    print(f"  {name:22} {a:>10.3f} {b:>10.3f}{mark}")
PY
sleep 2.5
note "совпадение поразрядное — и это не удача: recall, precision, ACL и"
note "маршрутизация считаются без LLM, из совпадения с эталонными пунктами"
note "изменилось единственное, что зависит от генерации, — расход токенов"

say "3. Три графовых бэкенда на одном хосте — основание ADR-0028"
note "один корпус, один вызов, 30 повторов; вектор и реранк в замер не входят"
cmd "python -m tools.graph_compare"
.venv/bin/python -m tools.graph_compare 2>&1 | grep -v "^$"
sleep 2.5
note "качество не разделило: расхождений ноль у обоих — значит выбирать по нему нельзя"

say "4. Где они всё-таки расходятся — на глубине"
note "на демо-корпусе цепочка отмен одна и в один хоп, разница не проявляется"
note "поэтому строится заведомо глубокая цепочка и меряется обход по глубине"
cmd "python -m tools.graph_depth"
.venv/bin/python -m tools.graph_depth 2>&1 | grep -v "^$"
sleep 2.5
note "Neo4j линеен: Cypher не принимает *1..\$hops параметром, round-trip на каждый хоп"
note "рекурсивный CTE плоский: глубина — параметр запроса, поход в базу один"
note "решение приняла не эта таблица, а изоляция окружений и цена второго хранилища"
note "но без замера это было бы рассуждение, а не вывод"

say "5. Где система упирается — замер, а не ощущение"
note "закрытая петля: воркер шлёт запрос, ждёт ответ и шлёт следующий"
note "открытая петля выше насыщения меряет терпение генератора, а не сервис"
cmd "python -m tools.loadtest --scenarios ask --concurrency 1 2 4 --duration 8"
.venv/bin/python -m tools.loadtest --scenarios ask --concurrency 1 2 4 --duration 8 --warmup 2 2>&1 | grep -v "^$"
sleep 2.5
note "RPS перестаёт расти уже на четырёх клиентах, а p50 уходит вчетверо"
note "причина не в приложении: инференс один на всех, очередь стоит перед ним"
note "отсюда и вывод отчёта — масштабировать надо карты, а не реплики сервиса"

printf "\n${B}${G}Готово.${N}\n"
sleep 2.5
