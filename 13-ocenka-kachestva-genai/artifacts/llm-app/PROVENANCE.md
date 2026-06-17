# Происхождение снапшота

- **Источник:** <https://github.com/Ilia2704/llm-app> — LIVE-демо лектора Ивана Четверикова (Raft) к уроку 13 «Оценка качества и тестирование GenAI-компонентов».
- **Зафиксированный коммит:** `b4cdc197c060c09e3145054266bdd4aef1a033c5`
- **Дата снятия снапшота:** 2026-06-17
- **Лицензия:** в исходном репозитории файла LICENSE нет (на момент снятия). Копия сохранена **в учебных целях** как архив материала занятия; авторство — за владельцем оригинального репозитория.

## Что внутри (как разбиралось на вебинаре)
- `pre_deploy_test.py` — pre-deploy сравнение **4 моделей** на RAG-задаче: Qwen 0.6B/4B/8B (Ollama) + YandexGPT Lite; метрики **RAGAS** (faithfulness, answer_relevancy, context_precision/recall, qa_semantic_correctness); логирование в **MLflow** (сравнение с baseline) и **Langfuse**.
- `run_ragas_demo_test.py` — одиночный прогон RAGAS.
- `toxic_test.py` — judge-оценка токсичности/грубости.
- `docker-compose.yaml` — локальные MLflow + Langfuse.
- `.github/workflows/main.yml` — пример CI (self-hosted runner).
- `practice.ipynb`, `practice_m2_local_llm.ipynb` — ноутбуки практики.
- `requirements.txt`, `check.py`, `publish_model_placeholder.py`.

## Обновить снапшот
```bash
git clone https://github.com/Ilia2704/llm-app.git /tmp/llm-app
# скопировать содержимое (кроме .git) сюда, обновить коммит/дату выше
```
