#!/usr/bin/env bash
# Демонстрация закрытого контура: поднимаем свой сервер и раскрываем всё
# через его API — как это делает демо ZuBrIQ Gateway на витрине.
#
#   asciinema rec --cols 100 --rows 34 -c "bash ../docs/demo/demo.sh" demo.cast
#
# Офлайн-режим (SUFLER_USE_LLM=0): retrieval, граф, права и стриминг работают
# полностью, генерация собирается экстрактивно — демонстрация не требует GPU.
set -u
PY=.venv/bin/python
PORT="${PORT:-$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')}"
API="http://127.0.0.1:$PORT"
# Узкий кадр (64 колонки): в командах показываем короткий $A, а не полный URL.
A="\$A"
export SUFLER_USE_LLM=0 PYTHONWARNINGS=ignore TRANSFORMERS_VERBOSITY=error \
       HF_HUB_DISABLE_PROGRESS_BARS=1 SUFLER_MAS=1

B=$'\e[1m'; C=$'\e[36m'; G=$'\e[32m'; Y=$'\e[33m'; D=$'\e[2m'; N=$'\e[0m'
say()  { printf "\n${B}${C}%s${N}\n" "$*"; sleep 1; }
note() { printf "${D}# %s${N}\n" "$*"; sleep 0.7; }
# Предупреждение HF Hub про анонимные запросы в кадре только шумит:
# веса берутся из локального кеша, токен здесь не нужен.
# Вывод режется по ширине кадра: горизонтальная прокрутка в плеере витрины
# есть, но строка, уезжающая за край, на мобильном не читается.
run()  { printf "\n${G}\$ %s${N}\n" "${1//$API/\$A}"; sleep 0.8; \
         eval "$1" 2>&1 | grep -v "HF Hub\|HF_TOKEN\|^$" \
         | cut -c1-62 | head -${2:-40}; sleep 1.2; }

clear
printf "${B}${C}Цифровые корпоративные сотрудники${N}\n"
note "закрытый контур · нулевой egress"
note "офлайн: GPU не нужен, граф и права работают"

say "1. Поднимаем сервис"
printf "\n${G}\$ uvicorn sufler.api:app --port \$PORT${N}\n"
  printf "${D}# A=http://127.0.0.1:\$PORT${N}\n"
$PY -m uvicorn sufler.api:app --port "$PORT" --log-level warning >/tmp/sufler-demo.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

printf "${D}# ждём готовности${N} "
for _ in $(seq 1 90); do
  curl -sf "$API/healthz" >/dev/null 2>&1 && break
  printf "."; sleep 1
done
printf "\n"
run "curl -s $API/healthz | jq -c"
note "auth=dev — режим доступа виден снаружи"
note "режим, о котором не знают, = открытый контур"

say "2. Граф связей собран поверх корпуса"
run "curl -s $API/graph/stats | jq -c"
note "4 ребра на 19 узлах: одна отмена и три ссылки"

say "3. Вопрос, где вектор ошибается"
run "curl -s $API/ask -H 'Content-Type: application/json' \\
    -d '{\"question\":\"Сколько дней основной ежегодный отпуск?\"}' \\
    | jq -c '{notes: .graph_notes, src: [.sources[].doc_code]}'" 8
note "28 дней нашёл вектор · отмену принёс граф"

say "4. Контрольный замер: без графа"
note "граф off, остальной путь тот же"
run "SUFLER_GRAPH=0 $PY -c \"
from sufler.rag import Sufler
r = Sufler().answer('Сколько дней основной ежегодный отпуск?', ['all'], 'demo')
print('пометок:', r['graph_notes'] or 'НЕТ')
print(r['answer'][:90])\"" 6
note "пометки нет — ответ уверенный и неверный"

say "5. Критерий ТЗ: пользователь B"
note "ЛПА-03 закрыт: acl = legal, security"
Q='Как обрабатываются ПДн командированного работника?'
run "curl -s $API/ask -H 'Content-Type: application/json' \\
    -d '{\"question\":\"$Q\",\"roles\":[\"all\"]}' \\
    | jq -c '[.sources[] | .doc_code + \" \" + .ordinal]'" 6
note "роль all: ЛПА-03 НЕТ, и не транзитом"
run "curl -s $API/ask -H 'Content-Type: application/json' \\
    -d '{\"question\":\"$Q\",\"roles\":[\"legal\"]}' \\
    | jq -c '[.sources[] | .doc_code + \" \" + .ordinal]'" 6
note "роль legal: ЛПА-03 ЕСТЬ"
note "предикат — на КАЖДОМ узле обхода"

say "6. Поток: источники раньше текста"
run "curl -sN $API/ask/stream -H 'Content-Type: application/json' \\
    -d '{\"question\":\"Сколько дней основной ежегодный отпуск?\"}' \\
    | head -8" 10
note "sources раньше первого token"

say "7. Штат цифровых сотрудников"
run "curl -s $API/agents | jq -c '.agents[] | {id, grants}'" 6
note "права агента = права юзера ∩ мандат роли"

say "8. Мультиагентный путь: маршрут и бюджет"
run "curl -s $API/agents/ask -H 'Content-Type: application/json' \\
    -d '{\"question\":\"$Q\",\"roles\":[\"legal\"]}' \\
    | jq -c '{route, budget}'" 6

say "9. OpenAI-совместимость"
run "curl -s $API/v1/chat/completions -H 'Content-Type: application/json' \\
    -d '{\"model\":\"sufler\",\"messages\":[{\"role\":\"user\",
         \"content\":\"Срок подачи заявления на отпуск?\"}]}' \\
    | jq -c '{model, answer: .choices[0].message.content[0:70]}'" 6

say "10. Проверки"
run "$PY -m pytest -q tests/test_graphrag.py tests/test_auth.py tests/test_mas.py" 6
note "тест на ACL проверяет контекст модели"

printf "\n${B}${C}Итого${N}\n"
note "граф меняет ответ · права на узлах · в контуре"
note "request_id открывает трейс в Jaeger"
sleep 2
