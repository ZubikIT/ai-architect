# Происхождение снапшота

- **Источник:** <https://github.com/Ilia2704/llm-app> — LIVE-демо лектора к уроку 13 «Оценка качества и тестирование GenAI-компонентов»; тот же репозиторий указан в материалах урока 18 «IaC и CI/CD» как объект пайплайна.
- **Зафиксированный коммит:** `3c6d4bc4c31651c23cb11badf4c377aa32561c49` («made order», 2026-07-07)
- **Дата снятия снапшота:** 2026-07-13 (обновление; исходный снапшот урока 13 был на коммите `b4cdc197` от 2026-06-17 — с тех пор апстрим реорганизован: скрипты разложены по пакетам `testing/`, `rag/`, `agent/`, добавлены RAG-демо на Qdrant и кредитный агент)
- **Лицензия:** в исходном репозитории файла LICENSE нет (на момент снятия). Копия сохранена **в учебных целях** как архив материала занятия; авторство — за владельцем оригинального репозитория.

## Что внутри
- `testing/` — материал урока 13 (в исходном снапшоте эти скрипты лежали в корне):
  - `pre_deploy_test.py` — pre-deploy сравнение **4 моделей** на RAG-задаче: Qwen 0.6B/4B/8B (Ollama) + YandexGPT Lite; метрики **RAGAS** (faithfulness, answer_relevancy, context_precision/recall, qa_semantic_correctness); логирование в **MLflow** (сравнение с baseline) и **Langfuse**;
  - `run_ragas_demo_test.py` — одиночный прогон RAGAS;
  - `toxic_test.py` — judge-оценка токсичности/грубости;
  - `check.py`, `publish_model_placeholder.py`.
- `rag/` — RAG-демо (добавлено после урока 13): `seed_qdrant_demo.py`, `run_rag_chat_demo.py`, `rag_demo_common.py`.
- `agent/` — `run_agent_credit_demo.py`, демо агента (добавлено после урока 13).
- `docker-compose.yaml` — локальные MLflow + Langfuse.
- `.github/workflows/main.yml` — пример CI (self-hosted runner).
- `practice.ipynb`, `practice_m2_local_llm.ipynb`, `requirements.txt`.

## Обновить снапшот
```bash
git clone https://github.com/Ilia2704/llm-app.git /tmp/llm-app
# скопировать содержимое (кроме .git) сюда, обновить коммит/дату выше
```
