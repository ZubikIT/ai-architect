#!/usr/bin/env bash
# Второе действие демонстрации: наблюдаемость и граф — те кадры, которые ТЗ
# требует показать в Neo4j Browser, Jaeger и Grafana.
#
#   asciinema rec --cols 100 --rows 34 -c "bash final-project/docs/demo/demo-obs.sh" \
#       final-project/docs/demo/demo-obs.cast
#
# Отличие от demo.sh: тот поднимает свой сервер офлайн и ничего не требует
# снаружи. Здесь наоборот — работаем по **развёрнутому** стеку
# (`docker compose --profile core --profile obs`): смысл кадров именно в том,
# что данные пришли из настоящих Neo4j, Jaeger и VictoriaMetrics, а не из
# процесса, поднятого на время записи.
#
# Честная граница: это терминальное представление тех же данных, а не снимок
# интерфейса. Кадр с логами vLLM сюда не входит — GPU-бокс доступен только со
# своей консоли, снаружи в него хода нет по построению.
#
# Команды здесь выполняются напрямую, а не через `eval` строки: в первой
# редакции сложные вложенные кавычки ломались молча, и в кадр попадал текст
# jq-фильтра вместо его вывода.
set -u
API="${API:-http://localhost:8080}"
JAEGER="${JAEGER:-http://localhost:16686}"
VM="${VM:-http://localhost:8428}"
HERE="$(cd "$(dirname "$0")" && pwd)"
INFRA="${INFRA:-$HERE/../../infra}"

B=$'\e[1m'; C=$'\e[36m'; G=$'\e[32m'; D=$'\e[2m'; N=$'\e[0m'
say()  { printf "\n${B}${C}%s${N}\n" "$*"; sleep 1.2; }
note() { printf "${D}# %s${N}\n" "$*"; sleep 0.8; }
cmd()  { printf "\n${G}\$ %s${N}\n" "$*"; sleep 0.9; }

NEO_PW="$(grep -E '^NEO4J_(PASSWORD|AUTH)' "$INFRA/.env" | head -1 | sed 's/.*[=/]//')"
cypher() {
  sudo docker compose -f "$INFRA/docker-compose.yml" exec -T neo4j \
       cypher-shell -u neo4j -p "$NEO_PW" --format plain "$1" 2>&1
}
ask() {  # $1 — вопрос, $2 — роль
  curl -s -m 180 -X POST "$API/ask" -H 'Content-Type: application/json' \
       -d "{\"question\":\"$1\",\"roles\":[\"$2\"]}"
}
metric() {
  printf "  %-32s " "$1"
  curl -s -m 15 --get --data-urlencode "query=$2" "$VM/api/v1/query" \
    | jq -r '.data.result[0].value[1] // "—"'
  sleep 0.5
}

clear
printf "${B}${C}Наблюдаемость закрытого контура${N}\n"
note "развёрнутый стек: Neo4j, Jaeger, VictoriaMetrics, Grafana"
note "данные настоящие — ничего не поднимается на время записи"

say "1. Граф связей живёт в самой Neo4j, а не в памяти процесса"
cmd "cypher-shell 'MATCH ()-[r]->() RETURN type(r), count(*)'"
cypher 'MATCH ()-[r]->() RETURN type(r) AS ребро, count(*) AS сколько ORDER BY сколько DESC;'
sleep 1.5
note "ОТМЕНЯЕТ всего одно — но именно оно меняет ответ"

say "2. Ребро, которое меняет ответ"
cmd "cypher-shell 'MATCH (a:Чанк)-[:ОТМЕНЯЕТ]->(b:Чанк) RETURN ...'"
cypher "MATCH (a:Чанк)-[:ОТМЕНЯЕТ]->(b:Чанк) RETURN a.doc_code + ' · ' + a.section AS отменяющий, b.doc_code + ' · ' + b.section AS отменённый;"
sleep 1.5
note "ЛПА-04 отменяет норму ЛПА-01 — текстуально эти куски непохожи"
note "поэтому гарантии попасть в top-k у отмены нет, её приносит обход"

say "3. Права лежат на узлах графа, а не поверх готовой выдачи"
cmd "cypher-shell 'MATCH (c:Чанк {doc_code:\"ЛПА-03\"})-[:ДОСТУПЕН_РОЛИ]->(r:Роль) ...'"
cypher "MATCH (c:Чанк {doc_code:'ЛПА-03'})-[:ДОСТУПЕН_РОЛИ]->(r:Роль) RETURN c.section AS раздел, collect(r.name) AS роли;"
sleep 1.5
note "роли all среди них нет — для неё этих узлов не существует"

say "4. Критерий ТЗ: один вопрос, две роли"
Q="Как обрабатываются персональные данные командированного работника?"
for ROLE in all legal; do
  cmd "curl -s \$API/ask -d '{\"question\":\"…ПДн командированного…\",\"roles\":[\"$ROLE\"]}'"
  # Кириллица в ключе объекта jq обязана быть в кавычках: без них парсер
  # принимает её за недопустимый символ и валится на compile error.
  ask "$Q" "$ROLE" | jq -c --arg r "$ROLE" '{"роль":$r, "источники":([.sources[].doc_code]|unique)}'
  sleep 1.2
done
note "закрытый ЛПА-03 появился только у legal — и не транзитом по ссылке"

say "5. Тот же запрос в Jaeger: request_id это и есть trace_id"
RID="$(curl -s -m 180 -X POST "$API/ask" -H 'Content-Type: application/json' \
        -d '{"question":"Сколько дней основной ежегодный отпуск?"}' | jq -r .request_id)"
printf "\n${G}\$ request_id = %s${N}\n" "$RID"
printf "${D}# ждём, пока спаны доедут до Jaeger${N}\n"
for _ in $(seq 1 20); do
  python3 "$HERE/jaeger_tree.py" "$RID" "$JAEGER" >/dev/null 2>&1 && break
  printf "."; sleep 2
done
printf "\n"
cmd "python3 jaeger_tree.py \$request_id     # то же дерево, что рисует UI"
python3 "$HERE/jaeger_tree.py" "$RID" "$JAEGER"
sleep 2
note "время съедают реранк и генерация; обход графа — единицы миллисекунд"
note "содержимое запроса в трейс не пишется: там имена шагов и длительности"

say "6. Метрики, на которых стоят алерты"
cmd "VictoriaMetrics /api/v1/query"
metric "пометка об отмене, доля" 'sum(increase(sufler_answers_total{cancellation="yes"}[24h])) / clamp_min(sum(increase(sufler_answers_total[24h])),1)'
metric "вклад графа, доля"       'sum(increase(sufler_answers_total{graph_contribution="yes"}[24h])) / clamp_min(sum(increase(sufler_answers_total[24h])),1)'
metric "обход графа p95, с"      'histogram_quantile(0.95, sum by (le) (increase(sufler_graph_expand_seconds_bucket[24h])))'
metric "ответ p95, с (без /healthz)" 'histogram_quantile(0.95, sum by (le) (increase(sufler_request_latency_seconds_bucket{endpoint!="/healthz"}[24h])))'
metric "доля ошибок"             '(sum(rate(sufler_requests_total{status=~"5.."}[15m])) or vector(0)) / clamp_min(sum(rate(sufler_requests_total[15m])),0.0001)'
metric "нарушений ACL"           'sum(sufler_acl_denials_total)'
metric "честных отказов"         'sum(sufler_low_relevance_total)'
sleep 1.5
note "первые две ловят «граф перестал работать» — падение доли видно раньше жалоб"
note "в демо-корпусе она около единицы: он построен вокруг отменённой нормы"
note "отказы в знаменатель не входят — отказ не считается ответом"
note "p95 считается без /healthz: 171 проверка против 21 запроса занижала его в 58 раз"

say "7. Чего здесь нет и почему"
note "guardrails и отклонённые токены — счётчики слоя платформы, не контура"
note "пустая панель это не ноль, и выдавать её за ноль нельзя"
note "логи vLLM снимаются с GPU-бокса: снаружи в него хода нет по построению"
printf "\n${B}${G}Готово.${N}\n"
sleep 2.5
