#!/usr/bin/env bash
# Собирает docs/ для MkDocs из корня репозитория: README → главная страница,
# уроки (NN-*) и final-project — как есть. Навигация строится из дерева
# автоматически (mkdocs.yml), поэтому новый урок публикуется без правки конфига.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf docs
mkdir docs
cp README.md docs/index.md

for d in [0-9][0-9]-*/ final-project/ kurs/; do
  cp -R "$d" "docs/$d"
done

# Лендинг защиты — обычный html рядом с сайтом: mkdocs копирует не-md как есть,
# и страница доступна по /landing/. Отдельной сборки не требует.
cp -R landing docs/landing
