# Sequence и ER — корпоративная AI-платформа

> Дополняют [C4-диаграммы](c4.md). Стек — из ADR-пакета [`../docs/adr/`](../docs/adr/).

## Sequence — обработка сложного запроса (персональный агентный чат)

Поток по брифу: `User → Guardrails → Rerank → Agent Loop → Tool Execution → Response`. Плоскость — Open WebUI + LangGraph-агент; общий LLM — Qwen3.6 (vLLM).

```mermaid
sequenceDiagram
  autonumber
  actor U as Пользователь
  participant W as Open WebUI
  participant G as Guardrails (Pipeline)
  participant A as Agent (LangGraph)
  participant R as Retriever (hybrid+rerank)
  participant Q as Qdrant
  participant M as MCP-серверы
  participant L as vLLM · Qwen3.6
  participant P as Postgres (state/logs)

  U->>W: запрос (SSO-сессия)
  W->>G: input-проверка
  G->>G: PII / prompt-injection
  alt запрос отклонён
    G-->>W: блок + причина
    W-->>U: вежливый отказ
  else запрос допущен
    G->>A: очищенный запрос
    A->>A: Planner (ReAct / Plan-and-Execute)
    A->>P: создать run, checkpoint

    loop Agent Loop (до ответа или лимита шагов/бюджета)
      A->>R: hybrid search (dense + BM25)
      R->>Q: kNN + sparse (RBAC pre-filter)
      Q-->>R: кандидаты
      R->>R: rerank (cross-encoder)
      R-->>A: top-k чанки
      opt нужен инструмент/действие
        A->>M: вызов инструмента (MCP)
        opt необратимое действие
          A->>U: запрос подтверждения (HITL)
          U-->>A: подтверждено
        end
        M-->>A: результат
      end
      A->>L: generate(промпт + контекст + tool-results)
      L-->>A: следующий шаг / черновик ответа
      A->>P: checkpoint + лог шага (tokens, latency)
    end

    A->>G: output-проверка (черновик)
    G->>G: PII-маска, toxicity, faithfulness
    G-->>W: финальный ответ
    W-->>U: ответ (streaming)
    W-)P: лог сессии/реплики (async)
  end
```

## ER — модель данных

Векторы физически живут в **Qdrant** (ADR-0004); реляционная модель хранит метаданные, RBAC-права (permission-aware retrieval), сессии и аудит. `EMBEDDING.vector_ref` ссылается на point id в Qdrant.

```mermaid
erDiagram
  USER ||--o{ USER_ROLE : has
  ROLE ||--o{ USER_ROLE : grants
  USER ||--o{ SESSION : opens
  USER ||--o{ AUDIT_LOG : generates
  SESSION ||--o{ MESSAGE : contains
  SESSION ||--o{ AGENT_RUN : triggers
  AGENT_RUN ||--o{ TOOL_CALL : invokes
  DOCUMENT ||--o{ CHUNK : split_into
  CHUNK ||--|| EMBEDDING : has
  DOCUMENT ||--o{ DOCUMENT_ACL : protected_by
  ROLE ||--o{ DOCUMENT_ACL : allows

  USER {
    uuid id PK
    string sso_subject
    string email
    string display_name
    timestamp created_at
  }
  ROLE {
    uuid id PK
    string name
  }
  USER_ROLE {
    uuid user_id FK
    uuid role_id FK
  }
  DOCUMENT {
    uuid id PK
    string source
    string external_id
    string title
    string acl_ref
    timestamp updated_at
  }
  CHUNK {
    uuid id PK
    uuid document_id FK
    int ordinal
    text content
    int token_count
  }
  EMBEDDING {
    uuid id PK
    uuid chunk_id FK
    string model
    int dim
    string vector_ref
    jsonb sparse_terms
  }
  DOCUMENT_ACL {
    uuid document_id FK
    uuid role_id FK
    string permission
  }
  SESSION {
    uuid id PK
    uuid user_id FK
    string channel
    timestamp started_at
  }
  MESSAGE {
    uuid id PK
    uuid session_id FK
    string role
    text content
    timestamp created_at
  }
  AGENT_RUN {
    uuid id PK
    uuid session_id FK
    uuid message_id FK
    string status
    int steps
    int tokens_total
    int latency_ms
    timestamp created_at
  }
  TOOL_CALL {
    uuid id PK
    uuid agent_run_id FK
    string tool
    jsonb input
    jsonb output
    uuid approved_by FK
    timestamp created_at
  }
  AUDIT_LOG {
    uuid id PK
    uuid user_id FK
    string action
    string resource
    timestamp ts
  }
```

### Заметки к модели
- **RBAC / permission-aware (№ 99-З):** `DOCUMENT_ACL` + `USER_ROLE` → pre-filter в Qdrant по правам (пользователь не видит чужое); `AUDIT_LOG` — учёт доступа.
- **Vectors / chunks:** `DOCUMENT → CHUNK → EMBEDDING`; вектор в Qdrant, метаданные и payload-фильтры — в реляционке (синхронизированы).
- **Sessions / logs:** `SESSION → MESSAGE`, `AGENT_RUN → TOOL_CALL` — трейс агента (steps/tokens/latency) для отладки, FinOps и аудита; `TOOL_CALL.approved_by` фиксирует HITL.
- **Onyx** ведёт собственную модель индекса для общих БЗ (ADR-0008); эта ER — для персональной/агентной плоскости (Qdrant + состояние).
