---
module: 02-architecture
lesson: 6
date: 2026-05-19
lecturer: Денис Лавров
tags: [RAG, retrieval, embeddings, reranking, hybrid-search, graph-rag, self-rag, crag]
status: todo
---

# 06. Архитектурные паттерны: RAG и его продвинутые вариации

> **Анонс занятия** · 19 мая (вт), 20:00 · 90 мин · преподаватель Денис Лавров
>
> **Цели:** проектировать и реализовывать системы на паттерне RAG; анализировать и применять продвинутые техники (реранжирование, гибридный поиск) для повышения качества ответов.
>
> **Содержание:** детальный разбор RAG-пайплайнов; продвинутые паттерны Self-RAG, CRAG, Knowledge/Cache Augmented Generation; практика — проектирование **гибридной RAG-архитектуры на Vector DB + Knowledge Graph**.
>
> **Результаты:** конспект лекции · практическое задание · Colab notebook с кодом.
>
> **Компетенция:** проектировать гибридные RAG-архитектуры с использованием Vector DB и Knowledge Graph.

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
