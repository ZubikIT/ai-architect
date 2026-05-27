# Суфлёр RAG-сервис (FastAPI). Образ self-contained: модели эмбеддера и
# реранкера запекаются на сборке → готов к air-gapped-запуску без интернета.
FROM python:3.11-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false \
    SUFLER_EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2 \
    SUFLER_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2 \
    SUFLER_DATA_DIR=/app/data/lpa

COPY requirements.txt .
RUN pip install -r requirements.txt

# Пред-загрузка моделей в образ (чтобы в проде не ходить в интернет).
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; import os; SentenceTransformer(os.environ['SUFLER_EMBED_MODEL']); CrossEncoder(os.environ['SUFLER_RERANK_MODEL'])"

COPY sufler ./sufler
COPY data ./data

EXPOSE 8080

# healthcheck — /healthz
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz').status==200 else 1)"

CMD ["uvicorn", "sufler.api:app", "--host", "0.0.0.0", "--port", "8080"]
