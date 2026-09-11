"""Этап 1 — формирование базы знаний: загрузка ЛПА, чанкинг, метаданные (ACL, провенанс, связи).

Каскад разбора по ADR-0014 реализован здесь первой ступенью (текстовый слой):
у markdown-исходников он детерминирован, поэтому `extracted_by='text'` и
`confidence=1.0`. Ступени layout-парсера и VL-модели подключаются на этом же
контракте: меняются только значения провенанса у чанка.
"""
import glob
import os
import re
from dataclasses import dataclass, field

from .links import clause_number, doc_code_of, extract_references, parse_cancels


@dataclass
class Document:
    name: str                 # имя файла-источника
    code: str                 # ЛПА-01
    title: str
    acl: list = field(default_factory=lambda: ["all"])
    cancels: list = field(default_factory=list)   # [(код документа, номер пункта|None)]


@dataclass
class Chunk:
    id: int
    doc: str
    section: str
    text: str
    acl: list = field(default_factory=lambda: ["all"])
    doc_code: str = ""
    ordinal: str = ""                              # номер пункта: «1», «3.1»
    references: list = field(default_factory=list)  # коды ЛПА, на которые ссылается пункт
    extracted_by: str = "text"                     # text | ocr | vl (ADR-0014)
    confidence: float = 1.0


def load_documents(data_dir: str):
    """Читает все *.md из каталога ЛПА."""
    docs = []
    for path in sorted(glob.glob(os.path.join(data_dir, "*.md"))):
        with open(path, encoding="utf-8") as f:
            docs.append((os.path.basename(path), f.read()))
    if not docs:
        raise FileNotFoundError(f"Нет .md документов в {data_dir}")
    return docs


def _parse_acl(text: str):
    """Права доступа из строки-комментария: <!-- acl: hr, legal -->."""
    # только слова и запятые, чтобы не захватить хвост коммента "-->"
    m = re.search(r"acl:\s*([\w,\s]+)", text)
    if m:
        return [r.strip() for r in m.group(1).split(",") if r.strip()]
    return ["all"]


def chunk_documents(docs):
    """Чанкинг по заголовкам markdown → (документы, чанки).

    Раздел сохраняется для цитирования, номер пункта — для рёбер графа,
    ACL материализуется на каждом чанке (ADR-0016: метка живёт в данных).
    """
    documents, chunks, cid = [], [], 0
    for name, text in docs:
        acl = _parse_acl(text)
        title_m = re.search(r"^#\s+(.*)$", text, re.M)
        title = title_m.group(1).strip() if title_m else name
        code = doc_code_of(title) or name
        documents.append(Document(name=name, code=code, title=title,
                                  acl=acl, cancels=parse_cancels(text)))

        parts = re.split(r"\n(?=#{1,3}\s)", text)
        for part in parts:
            part = part.strip()
            if not part or part.startswith("<!--"):
                continue
            hm = re.match(r"#{1,3}\s+(.*)", part)
            section = hm.group(1).strip() if hm else "—"
            chunks.append(Chunk(
                id=cid, doc=name, section=section, text=part, acl=acl,
                doc_code=code, ordinal=clause_number(section),
                references=extract_references(part, code),
            ))
            cid += 1
    return documents, chunks
