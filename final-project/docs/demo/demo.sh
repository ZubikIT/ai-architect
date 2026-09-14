#!/usr/bin/env bash
# Демонстрация закрытого контура из терминала — офлайн-режим, без GPU.
# Запись: asciinema rec -c "bash docs/demo/demo.sh" demo.cast (из final-project/backend)
set -u
PY=.venv/bin/python
export SUFLER_USE_LLM=0 PYTHONWARNINGS=ignore TRANSFORMERS_VERBOSITY=error HF_HUB_DISABLE_PROGRESS_BARS=1

B=$'\e[1m'; C=$'\e[36m'; G=$'\e[32m'; Y=$'\e[33m'; N=$'\e[0m'
say()  { printf "\n${B}${C}%s${N}\n" "$*"; sleep 1; }
note() { printf "${Y}%s${N}\n" "$*"; sleep 1; }
run()  { printf "\n${G}\$ %s${N}\n" "$*"; sleep 1; eval "$@" 2>&1 | grep -v "Loading weights\|HF_TOKEN"; sleep 1; }

clear
say "Мультиагентная платформа цифровых корпоративных сотрудников"
note "Закрытый контур: свои модели, свой инференс, нулевой egress."
note "Демонстрация идёт в офлайн-режиме (SUFLER_USE_LLM=0): retrieval и граф работают полностью."

say "1. Граф связей ЛПА собран поверх корпуса"
run "$PY -m sufler.cli --stats"
note "19 узлов, 4 документа, 4 ребра: одна отмена и три ссылки."

say "2. Вопрос, на котором вектор ошибается"
run "$PY -m sufler.cli 'Сколько дней основной ежегодный отпуск?'"
note "Вектор нашёл ЛПА-01 с 28 днями. Пометку об отмене принёс обход графа."

say "3. Контрольный замер: выключаем граф"
run "SUFLER_GRAPH=0 $PY -m sufler.cli 'Сколько дней основной ежегодный отпуск?'"
note "Пометки об отмене нет. Ответ выглядит так же уверенно — и он неверен."

say "4. Критерий ТЗ: пользователь B не получает закрытый документ"
note "ЛПА-03 «Регламент доступа к ПДн» закрыт: acl = legal, security."
run "$PY -m sufler.cli --roles all 'Как обрабатываются персональные данные командированного работника?'"
note "Роль all: ЛПА-03 в выдаче отсутствует — и не приходит транзитом по ссылке."
run "$PY -m sufler.cli --roles legal 'Как обрабатываются персональные данные командированного работника?'"
note "Роль legal: тот же вопрос, ЛПА-03 в выдаче есть."

say "5. Проверки, которые это удерживают"
run "$PY -m pytest -q tests/test_graphrag.py tests/test_auth.py"
note "Тест на ACL проверяет контекст модели, а не текст ответа."

say "Итого: граф меняет ответ, права стоят на каждом узле обхода, всё внутри контура."
sleep 2
