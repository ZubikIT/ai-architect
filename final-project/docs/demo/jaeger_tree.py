"""Трейс из Jaeger как дерево спанов — то же, что рисует UI, только в терминале.

    python3 jaeger_tree.py <trace_id> [jaeger_url]

Вынесено отдельным файлом намеренно: внутри demo-obs.sh этот разбор жил
многострочной питон-вставкой в двойных кавычках, и экранирование ломалось
молча — в кадре оказывался текст программы вместо её вывода.
"""
import json
import sys
import urllib.request

trace_id = sys.argv[1]
base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:16686"

with urllib.request.urlopen(f"{base}/api/traces/{trace_id}", timeout=15) as r:
    data = json.load(r).get("data") or []

if not data:
    print(f"трейс {trace_id} ещё не доехал до Jaeger")
    raise SystemExit(1)

spans = data[0]["spans"]
children = {}
for s in spans:
    parent = next((ref["spanID"] for ref in s.get("references", [])
                   if ref["refType"] == "CHILD_OF"), None)
    children.setdefault(parent, []).append(s)

known = {s["spanID"] for s in spans}
roots = children.get(None, []) + [s for p, group in children.items()
                                  if p is not None and p not in known
                                  for s in group]


def walk(span, depth=0):
    pad = "  " * depth
    print(f"{pad}{span['operationName']:<{24 - len(pad)}} {span['duration'] / 1000:9.1f} мс")
    for kid in sorted(children.get(span["spanID"], []), key=lambda x: x["startTime"]):
        walk(kid, depth + 1)


for root in sorted(roots, key=lambda x: x["startTime"]):
    walk(root)
