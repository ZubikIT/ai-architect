#!/usr/bin/env bash
#
# md-to-pdf.sh — конвертация markdown в PDF через pandoc.
# Поддерживает русский язык, таблицы, fenced code, mermaid (как код).
#
# Использование:
#   ./scripts/md-to-pdf.sh <file.md> [output.pdf]
#
#   --toc          добавить оглавление (по умолчанию выключено)
#   --no-numbers   убрать номера страниц
#
# Зависимости (одно из):
#   pandoc + typst       (рекомендуется): brew install pandoc typst
#   pandoc + xelatex     (классика):       brew install pandoc && brew install --cask basictex
#
set -euo pipefail

usage() {
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

WITH_TOC=0
WITH_NUMBERS=1
ARGS=()
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage 0 ;;
    --toc) WITH_TOC=1 ;;
    --no-numbers) WITH_NUMBERS=0 ;;
    *) ARGS+=("$arg") ;;
  esac
done

[ "${#ARGS[@]}" -lt 1 ] && usage 1

INPUT="${ARGS[0]}"
[ -f "$INPUT" ] || { echo "✗ file not found: $INPUT" >&2; exit 1; }

OUTPUT="${ARGS[1]:-${INPUT%.md}.pdf}"

# --- проверяем зависимости ---
if ! command -v pandoc >/dev/null 2>&1; then
  cat >&2 <<EOF
✗ pandoc не установлен.

Установка (рекомендуется):
  brew install pandoc typst

Альтернатива (LaTeX):
  brew install pandoc
  brew install --cask basictex
  eval "\$(/usr/libexec/path_helper)"   # подхватить xelatex без релогина
EOF
  exit 1
fi

# --- выбираем движок ---
if command -v typst >/dev/null 2>&1; then
  ENGINE=typst
elif command -v xelatex >/dev/null 2>&1; then
  ENGINE=xelatex
else
  cat >&2 <<EOF
✗ Нужен PDF-движок. Поставьте один из:
  brew install typst             # рекомендуется
  brew install --cask basictex   # LaTeX
EOF
  exit 1
fi

echo "→ engine: $ENGINE"
echo "→ input:  $INPUT"
echo "→ output: $OUTPUT"

# --- собираем флаги ---
COMMON_OPTS=(
  --from=gfm+yaml_metadata_block
  -V geometry:margin=2cm
  -V lang=ru
  -V mainfont="Helvetica"
  -V monofont="Menlo"
  -V fontsize=11pt
  -V colorlinks=true
  -V linkcolor=blue
)

[ "$WITH_TOC" = 1 ] && COMMON_OPTS+=(--toc --toc-depth=2)
[ "$WITH_NUMBERS" = 0 ] && COMMON_OPTS+=(-V pagestyle=empty)

if [ "$ENGINE" = "typst" ]; then
  pandoc "$INPUT" -o "$OUTPUT" \
    --pdf-engine=typst \
    "${COMMON_OPTS[@]}"
else
  pandoc "$INPUT" -o "$OUTPUT" \
    --pdf-engine=xelatex \
    -V documentclass=article \
    -V CJKmainfont="Helvetica" \
    "${COMMON_OPTS[@]}"
fi

echo "✓ done: $OUTPUT"
