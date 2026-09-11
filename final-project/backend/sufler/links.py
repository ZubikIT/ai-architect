"""Экстракция связей между документами и пунктами ЛПА (ADR-0013, ADR-0014).

Приоритет правил над моделью: номера документов, пунктов и отмены ловятся
регулярными выражениями — детерминированно и воспроизводимо. LLM-экстрактор
в проде дополняет этот результат, но не переопределяет его.
"""
import re

DOC_CODE = re.compile(r"\bЛПА-(\d{2})\b")
# явные метаданные документа: <!-- cancels: ЛПА-01 § 1 -->
CANCELS_META = re.compile(r"cancels:\s*ЛПА-(\d{2})\s*(?:§|п\.?)?\s*([\d.]+)?", re.I)
# текстовое правило: «Пункт 1 Положения ЛПА-01 ... отменяется»
CANCELS_TEXT = re.compile(
    r"[Пп]ункт\s+([\d.]+)\s+[^.]{0,80}?ЛПА-(\d{2})[^.]{0,120}?отмен", re.S
)
# внутридокументная ссылка: «п. 4.2», «пункт 3»
CLAUSE_REF = re.compile(r"\bп(?:ункт[ауе]?|\.)\s*([\d]+(?:\.[\d]+)?)", re.I)


def doc_code_of(title: str) -> str:
    """Код документа из заголовка: «# ЛПА-01. Положение …» → ЛПА-01."""
    m = DOC_CODE.search(title or "")
    return f"ЛПА-{m.group(1)}" if m else ""


def parse_cancels(text: str):
    """Отмены, объявленные документом: [(код документа, номер пункта|None), …].

    Источник истины — явные метаданные; текстовое правило подхватывает случаи,
    где метаданных нет. Дубли схлопываются.
    """
    found = []
    for m in CANCELS_META.finditer(text):
        found.append((f"ЛПА-{m.group(1)}", (m.group(2) or "").strip() or None))
    for m in CANCELS_TEXT.finditer(text):
        found.append((f"ЛПА-{m.group(2)}", m.group(1)))
    seen, out = set(), []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def extract_references(text: str, self_code: str = ""):
    """Ссылки чанка на другие ЛПА: [(код, номер пункта|None), …].

    Номер пункта ищется в окне вокруг упоминания документа — «ЛПА-01 п. 3»,
    «Пункт 1 Положения ЛПА-01». Без номера ссылка ведёт на карточку документа,
    а не на все его пункты: иначе обход тащит в контекст весь документ.
    """
    out, seen = [], set()
    for m in DOC_CODE.finditer(text):
        code = f"ЛПА-{m.group(1)}"
        if code == self_code:
            continue
        window = text[max(0, m.start() - 60): m.end() + 60]
        cm = CLAUSE_REF.search(window)
        item = (code, cm.group(1) if cm else None)
        if item not in seen:
            seen.add(item)
            out.append(item)
    return sorted(out, key=lambda x: (x[0], x[1] or ""))


def clause_number(section: str) -> str:
    """Номер пункта из заголовка раздела: «3.1. Обработка данных» → 3.1."""
    m = re.match(r"\s*([\d]+(?:\.[\d]+)*)", section or "")
    return m.group(1) if m else ""
