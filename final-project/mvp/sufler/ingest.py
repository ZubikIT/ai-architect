"""Этап 1 — формирование базы знаний: загрузка ЛПА, чанкинг, метаданные (RBAC)."""
import glob
import os
import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    id: int
    doc: str
    section: str
    text: str
    acl: list = field(default_factory=lambda: ["all"])


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
    m = re.search(r"acl:\s*([^\n>]+)", text)
    if m:
        return [r.strip() for r in m.group(1).split(",") if r.strip()]
    return ["all"]


def chunk_documents(docs):
    """Recursive-чанкинг по заголовкам markdown с сохранением раздела (для цитирования)."""
    chunks, cid = [], 0
    for name, text in docs:
        acl = _parse_acl(text)
        parts = re.split(r"\n(?=#{1,3}\s)", text)
        for part in parts:
            part = part.strip()
            if not part or part.startswith("<!--"):
                continue
            hm = re.match(r"#{1,3}\s+(.*)", part)
            section = hm.group(1).strip() if hm else "—"
            chunks.append(Chunk(id=cid, doc=name, section=section, text=part, acl=acl))
            cid += 1
    return chunks
