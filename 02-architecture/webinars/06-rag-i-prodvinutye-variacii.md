---
module: 02-architecture
lesson: 6
date:
lecturer:
tags: [RAG, retrieval, embeddings, reranking]
status: todo
---

# 06. Архитектурные паттерны: RAG и его продвинутые вариации

## TL;DR

## Контекст и проблема
_Когда нужен RAG, какие проблемы он решает и какие создаёт._

## Базовый RAG
```mermaid
flowchart LR
  Q[Запрос] --> EMB[Embedding]
  EMB --> RET[Retrieval из vector store]
  RET --> CTX[Контекст]
  CTX --> LLM[LLM]
  LLM --> A[Ответ]
```

## Продвинутые вариации
| Вариация | Идея | Когда применять | Цена |
|---|---|---|---|
| Hybrid search (BM25 + vector) |  |  |  |
| HyDE |  |  |  |
| Multi-query / fusion |  |  |  |
| Reranking (cross-encoder) |  |  |  |
| Parent-document / hierarchical |  |  |  |
| Graph RAG |  |  |  |
| Self-RAG / CRAG |  |  |  |
| Agentic RAG |  |  |  |

## Ключевые тезисы
-
-
-

## Метрики качества
- Faithfulness
- Answer relevance
- Context precision / recall
- Latency p95
- Cost per query

## Примеры / кейсы

## Вопросы и ответы

## Что почитать / посмотреть

## Мои выводы
