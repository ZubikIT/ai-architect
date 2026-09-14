"""Эмбеддинги: локальная модель на CPU или сервис платформы на GPU.

История та же, что у ранжирования ([ADR-0027](../../docs/adr/0027-konveyer-ranzhirovaniya.md)),
и вывод тот же. После переноса реранка на сервис платформы эмбеддер стал вторым
по стоимости шагом ответа: было 3,6 % времени, стало **11,9 %** — не потому, что
он замедлился, а потому, что ушло то, что его заслоняло.

Но главное здесь не скорость. Локальная модель — `paraphrase-multilingual-MiniLM-L12-v2`,
384 измерения, — выбиралась под CPU, а не по качеству. Тот же сервис платформы
отдаёт **`bge-m3` на 1024 измерения**, и именно им считались все замеры качества
на боевом корпусе (A/B якоря статьи, `docs/eval/ab-anchor.md`). То есть замеры
проводились одним эмбеддером, а сервис работал на другом — расхождение, которое
делает выводы замеров условными.

Две реализации за одним протоколом — `encode(texts) -> ndarray`, как у
`sentence_transformers`: вызывающий код не знает, где считается модель.

**Смена эмбеддера — не переключение URL.** Размерность меняется с 384 на 1024,
значит коллекция Qdrant пересоздаётся, а порог отказа по косинусу пересчитывается:
у разных моделей разный масштаб близости, и старое значение на новой модели
означает другое. Порог живёт в `SUFLER_MIN_RELEVANCE`, замер — в `docs/eval-report.md`.
"""
import numpy as np

from .config import settings
from .httpservice import RemoteModelService, ServiceUnavailable


class EmbedUnavailable(ServiceUnavailable):
    """Сервис эмбеддингов недоступен.

    Отдельный тип, а не общий: отказ эмбеддера и отказ реранкера означают разное
    для пользователя. Без реранка выдача деградирует до векторной, без эмбеддера
    её нет вовсе — запрос не во что превратить.
    """


class LocalEmbedder:
    """Модель в процессе. Медленно и слабее, зато без сети и без ключей."""

    #: Размерность известна только после первой кодировки — модель грузится лениво.
    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer
        self.model_name = model
        self._model = SentenceTransformer(model)
        self.healthy = True

    def encode(self, texts, normalize_embeddings=True):
        return self._model.encode(list(texts), normalize_embeddings=normalize_embeddings)


class RemoteEmbedder(RemoteModelService):
    """Сервис эмбеддингов платформы (Infinity, OpenAI-совместимый `/embeddings`).

    Батчинг делает сервис: один вызов на весь набор текстов, а не по одному.
    Именно в этом выигрыш — один поход в сеть против прогона модели на CPU.
    """

    service_name = "сервис эмбеддингов"
    error = EmbedUnavailable

    #: Пустой ввод сетью не гоняем: у индексации это нормальный крайний случай
    #: (документ без чанков), и поход за ответом на него — лишний отказ.
    def __init__(self, url: str, model: str, api_key: str = "", timeout: float = 30.0,
                 batch: int = 64):
        super().__init__(url, "/embeddings", model, api_key, timeout)
        self.batch = batch

    def encode(self, texts, normalize_embeddings=True):
        texts = list(texts)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        vectors = []
        # Набор режется на порции: на индексации их тысячи, и одним телом
        # запроса это упирается в лимиты сервиса, а не в его скорость.
        for start in range(0, len(texts), self.batch):
            chunk = texts[start:start + self.batch]
            data = self._request({"model": self.model_name, "input": chunk})
            items = data.get("data", [])
            if len(items) != len(chunk):
                self.healthy = False
                raise EmbedUnavailable(
                    f"сервис эмбеддингов вернул {len(items)} векторов на {len(chunk)} текстов")
            # Порядок в ответе не гарантирован контрактом — раскладываем по index.
            ordered = [None] * len(chunk)
            for item in items:
                ordered[int(item["index"])] = item["embedding"]
            vectors.extend(ordered)

        arr = np.asarray(vectors, dtype=np.float32)
        if normalize_embeddings:
            # bge-m3 отдаёт уже нормированные векторы, но полагаться на это
            # нельзя: протокол этого не обещает, а косинусный порог сломается
            # молча — выдача просто станет другой.
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            arr = arr / np.where(norms == 0, 1.0, norms)
        return arr


def build_embedder(cfg=settings):
    """Сервис платформы при заданном `EMBEDDINGS_URL`, иначе локальная модель.

    Переменная называется так же, как у консоли платформы: сервис один, и
    настраиваться он должен одним комплектом кредов.
    """
    if cfg.embed_url:
        return RemoteEmbedder(cfg.embed_url, cfg.embed_model_remote, cfg.embed_api_key)
    return LocalEmbedder(cfg.embed_model)
