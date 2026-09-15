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
export SUFLER_USE_LLM=0 PYTHONWARNINGS=ignore TRANSFORMERS_VERBOSITY=error \
       HF_HUB_DISABLE_PROGRESS_BARS=1 SUFLER_MAS=1

B=$'\e[1m'; C=$'\e[36m'; G=$'\e[32m'; Y=$'\e[33m'; D=$'\e[2m'; N=$'\e[0m'
say()  { printf "\n${B}${C}%s${N}\n" "$*"; sleep 1; }
note() { printf "${D}# %s${N}\n" "$*"; sleep 0.7; }
# Предупреждение HF Hub про анонимные запросы в кадре только шумит:
# веса берутся из локального кеша, токен здесь не нужен.
run()  { printf "\n${G}\$ %s${N}\n" "$1"; sleep 0.8; \
         eval "$1" 2>&1 | grep -v "HF Hub\|HF_TOKEN\|^$" | head -${2:-40}; sleep 1.2; }

clear
printf "${B}${C}Мультиагентная платформа цифровых корпоративных сотрудников${N}\n"
note "закрытый контур: свои модели, свой инференс, нулевой egress"
note "демонстрация офлайн — GPU не нужен, граф и права работают полностью"

say "1. Поднимаем сервис"
printf "\n${G}\$ uvicorn sufler.api:app --port $PORT${N}\n"
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
note "auth=dev — режим доступа виден снаружи намеренно:"
note "dev-режим, о котором не знают, это открытый контур, который считают закрытым"

say "2. Граф связей собран поверх корпуса"
run "curl -s $API/graph/stats | jq -c"
note "4 ребра на 19 узлах: одна отмена и три ссылки"

say "3. Вопрос, на котором вектор ошибается"
run "curl -s $API/ask -H 'Content-Type: application/json' \\
    -d '{\"question\":\"Сколько дней основной ежегодный отпуск?\"}' \\
    | jq '{answer: .answer[0:200], graph_notes, sources: [.sources[].doc_code]}'" 25
note "вектор нашёл ЛПА-01 с 28 днями — пометку об отмене принёс обход графа"

say "4. Контрольный замер: тот же вопрос без графа"
note "граф выключается переменной окружения, остальной путь не меняется"
run "SUFLER_GRAPH=0 $PY -c \"
from sufler.rag import Sufler
r = Sufler().answer('Сколько дней основной ежегодный отпуск?', ['all'], 'demo')
print('пометок:', r['graph_notes'] or 'НЕТ')
print(r['answer'][:150])\"" 8
note "пометки нет — ответ выглядит так же уверенно и он неверен"

say "5. Критерий ТЗ: пользователь B не получает закрытый документ"
note "ЛПА-03 «Регламент доступа к ПДн» закрыт: acl = legal, security"
Q='Как обрабатываются персональные данные командированного работника?'
run "curl -s $API/ask -H 'Content-Type: application/json' \\
    -d '{\"question\":\"$Q\",\"roles\":[\"all\"]}' \\
    | jq -c '[.sources[] | .doc_code + \" \" + .ordinal]'" 6
note "роль all: ЛПА-03 в выдаче НЕТ — и не приходит транзитом по ссылке"
run "curl -s $API/ask -H 'Content-Type: application/json' \\
    -d '{\"question\":\"$Q\",\"roles\":[\"legal\"]}' \\
    | jq -c '[.sources[] | .doc_code + \" \" + .ordinal]'" 6
note "роль legal: тот же вопрос, ЛПА-03 в выдаче ЕСТЬ"
note "предикат доступа стоит на КАЖДОМ узле обхода, а не на финальной выдаче"

say "6. Потоковый ответ: источники раньше текста"
run "curl -sN $API/ask/stream -H 'Content-Type: application/json' \\
    -d '{\"question\":\"Сколько дней основной ежегодный отпуск?\"}' \\
    | head -14" 16
note "sources уходят раньше первого token — цитата важнее скорости текста"

say "7. Штат цифровых сотрудников"
run "curl -s $API/agents | jq -c '.agents[] | {id, title, grants}'" 8
note "права агента = права пользователя ∩ мандат роли, пересечение в инструменте"

say "8. Мультиагентный путь: маршрут и израсходованный бюджет"
run "curl -s $API/agents/ask -H 'Content-Type: application/json' \\
    -d '{\"question\":\"$Q\",\"roles\":[\"legal\"]}' \\
    | jq -c '{route, budget, agents: [.agents[] | {id, effective_roles, found}]}'" 10

say "9. OpenAI-совместимость: подключается как модель"
run "curl -s $API/v1/chat/completions -H 'Content-Type: application/json' \\
    -d '{\"model\":\"sufler\",\"messages\":[{\"role\":\"user\",
         \"content\":\"За сколько дней подаётся заявление на отпуск?\"}]}' \\
    | jq -c '{model, answer: .choices[0].message.content[0:110]}'" 6

say "10. Проверки, которые всё это удерживают"
run "$PY -m pytest -q tests/test_graphrag.py tests/test_auth.py tests/test_mas.py" 6
note "тест на ACL проверяет контекст модели, а не текст ответа"

printf "\n${B}${C}Итого${N}\n"
note "граф меняет ответ · права на каждом узле · всё внутри контура"
note "request_id из ответа открывает трейс в Jaeger — разложение по шагам"
sleep 2
