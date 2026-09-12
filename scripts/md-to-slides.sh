#!/usr/bin/env bash
#
# md-to-slides.sh — markdown → слайды (HTML + PDF), полностью локально.
#
#   ./scripts/md-to-slides.sh <file.md> [output-basename]
#
#     --notes    оставить заметки докладчика на слайдах (по умолчанию убраны)
#
# Что делает:
#   1. ```mermaid блоки рендерит в PNG локально (mmdc + Chrome for Testing);
#   2. строки «💬 …» убирает (или оставляет с --notes);
#   3. режет markdown по `---` на слайды, каждый прогоняет через pandoc;
#   4. собирает статический HTML со своим paged-CSS;
#   5. Chrome headless печатает его в PDF.
#
# Почему НЕ reveal.js. Пробовал `pandoc -t revealjs` + `?print-pdf`: работает
# ровно до тех пор, пока не добавишь свой стиль. С любым дополнительным
# stylesheet — хоть ссылкой, хоть инлайном — reveal измеряет раскладку раньше,
# чем стиль применился, и вся дека схлопывается в ОДНУ страницу PDF (проверено:
# 29 страниц без своего CSS против 1 с ним, причём содержимое стиля неважно).
# Статическая вёрстка без JS даёт тот же результат предсказуемо.
#
# Ничего не уходит во внешние сервисы — в отличие от mermaid.ink.
#
# Зависимости (ставятся один раз):
#   sudo apt-get install -y pandoc fonts-roboto poppler-utils
#   npm i -g @mermaid-js/mermaid-cli
#   PUPPETEER_CACHE_DIR=/opt/puppeteer npx puppeteer browsers install chrome
set -euo pipefail

CHROME="${CHROME:-$(ls -d /opt/puppeteer/chrome/linux-*/chrome-linux64/chrome 2>/dev/null | tail -1 || true)}"
MMDC="${MMDC:-$(command -v mmdc || ls /home/*/.local/opt/node-*/bin/mmdc 2>/dev/null | tail -1 || true)}"

SHOW_NOTES=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --notes) SHOW_NOTES=1 ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) ARGS+=("$a") ;;
  esac
done
[ "${#ARGS[@]}" -lt 1 ] && { echo "нужен входной .md" >&2; exit 1; }

INPUT="${ARGS[0]}"
BASE="${ARGS[1]:-${INPUT%.md}}"
[ -f "$INPUT" ] || { echo "нет файла: $INPUT" >&2; exit 1; }
command -v pandoc >/dev/null || { echo "нет pandoc" >&2; exit 1; }
[ -x "$CHROME" ] || { echo "нет Chrome: $CHROME" >&2; exit 1; }
[ -x "$MMDC" ] || { echo "нет mmdc: $MMDC" >&2; exit 1; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
IMG_DIR="$(dirname "$BASE")/$(basename "$BASE")-assets"
mkdir -p "$IMG_DIR"
cat > "$WORK/pptr.json" <<JSON
{"executablePath": "$CHROME", "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
JSON

HTML="$BASE.html"
SHOW_NOTES="$SHOW_NOTES" IMG_DIR="$IMG_DIR" MMDC="$MMDC" WORK="$WORK" \
CSS="$(dirname "$0")/slides.css" python3 - "$INPUT" "$HTML" <<'PY'
import base64, hashlib, os, pathlib, re, subprocess, sys

src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
img_dir, work = pathlib.Path(os.environ["IMG_DIR"]), pathlib.Path(os.environ["WORK"])
mmdc, show_notes = os.environ["MMDC"], os.environ["SHOW_NOTES"] == "1"
css = pathlib.Path(os.environ["CSS"]).read_text(encoding="utf-8")

text = src.read_text(encoding="utf-8")
# YAML-заголовок markdown в слайды не идёт — он метаданные файла, не слайд.
text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)

rendered = 0
def mermaid_to_img(match):
    global rendered
    code = match.group(1)
    name = "diagram-" + hashlib.sha1(code.encode()).hexdigest()[:10] + ".png"
    target = img_dir / name
    if not target.exists():                      # имя от содержимого → кэш
        (work / "d.mmd").write_text(code, encoding="utf-8")
        subprocess.run([mmdc, "-i", str(work / "d.mmd"), "-o", str(target),
                        "-p", str(work / "pptr.json"), "-b", "white",
                        "-w", "1600", "-H", "900", "-s", "2"],
                       check=True, stdout=subprocess.DEVNULL)
        rendered += 1
    data = base64.b64encode(target.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="">'

slides_html = []
for chunk in re.split(r"^---\s*$", text, flags=re.M):
    chunk = chunk.strip("\n")
    if not chunk.strip():
        continue
    if not show_notes:                            # «💬 …» — реплика докладчику
        chunk = "\n".join(l for l in chunk.splitlines() if not l.startswith("💬"))
    # Служебная врезка «как пользоваться файлом» на слайды не идёт.
    if chunk.lstrip().startswith("> **Как пользоваться"):
        continue
    images = []
    # Плейсхолдер без «@»: pandoc принимает `@IMG0` за цитату и оборачивает в span.
    chunk = re.sub(r"```mermaid\n(.*?)```",
                   lambda m: images.append(mermaid_to_img(m)) or f"IMGSLOT{len(images)-1}END",
                   chunk, flags=re.S)
    body = subprocess.run(["pandoc", "-f", "markdown+emoji", "-t", "html5"],
                          input=chunk, text=True, capture_output=True, check=True).stdout
    for i, img in enumerate(images):
        body = body.replace(f"<p>IMGSLOT{i}END</p>", f'<figure>{img}</figure>')
        body = body.replace(f"IMGSLOT{i}END", img)
    slides_html.append(f'<section class="slide">\n{body}</section>')

dst.write_text(f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>{src.stem}</title>
<style>
{css}
</style>
</head><body>
{chr(10).join(slides_html)}
</body></html>""", encoding="utf-8")
print(f"  слайдов: {len(slides_html)} · диаграмм отрендерено: {rendered} (кэш: {img_dir})")
PY

PDF="$BASE.pdf"
"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --virtual-time-budget=10000 --print-to-pdf="$PDF" "file://$(realpath "$HTML")" >/dev/null 2>&1

PAGES="$(pdfinfo "$PDF" 2>/dev/null | awk '/^Pages/{print $2}')"
echo "  HTML: $HTML"
echo "  PDF:  $PDF ($(du -h "$PDF" | cut -f1), страниц: ${PAGES:-?})"
