# Происхождение снапшота

- **Источник:** <https://github.com/Ilia2704/llm-app> — репозиторий лектора, указан в материалах урока 18 «IaC и CI/CD» как объект пайплайна (то же приложение разбиралось на уроке 13).
- **Зафиксированный коммит:** `3c6d4bc4c31651c23cb11badf4c377aa32561c49` («made order», 2026-07-07)
- **Дата снятия снапшота:** 2026-07-13
- **Лицензия:** в исходном репозитории файла LICENSE нет (на момент снятия). Копия сохранена **в учебных целях** как архив материала занятия; авторство — за владельцем оригинального репозитория.

> Отличие от снапшота урока 13 (`13-ocenka-kachestva-genai/artifacts/llm-app`, коммит `b4cdc19`): репозиторий с тех пор реорганизован — скрипты разложены по пакетам `testing/`, `rag/`, `agent/`; добавлены RAG-демо на Qdrant и кредитный агент-демо.

## Что внутри
- `testing/` — материал урока 13: `pre_deploy_test.py` (сравнение 4 моделей, RAGAS + MLflow + Langfuse), `run_ragas_demo_test.py`, `toxic_test.py`, `check.py`, `publish_model_placeholder.py`.
- `rag/` — RAG-демо: `seed_qdrant_demo.py`, `run_rag_chat_demo.py`, `rag_demo_common.py`.
- `agent/` — `run_agent_credit_demo.py` (демо агента).
- `docker-compose.yaml` — локальные MLflow + Langfuse.
- `practice.ipynb`, `practice_m2_local_llm.ipynb`, `requirements.txt`.

## Обновить снапшот
```bash
git clone https://github.com/Ilia2704/llm-app.git /tmp/llm-app
# скопировать содержимое (кроме .git) сюда, обновить коммит/дату выше
```
