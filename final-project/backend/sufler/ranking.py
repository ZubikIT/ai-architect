"""Ранжирование: локальный cross-encoder или сервис ранжирования платформы.

Замер показал, что реранк — узкое место: 76 % времени ответа без генерации и
30 % с ней. Причина не в алгоритме, а в том, где он выполняется: cross-encoder
крутится на CPU этой машины, по 47–55 мс на кандидата.

У платформы ранжирование уже вынесено в отдельный сервис на GPU (Infinity,
`bge-reranker-v2-m3`), и его API Jina-совместим. Поэтому правильный ответ здесь
не «оптимизировать свою модель», а **перестать держать свою**: проект работает
на платформе, значит и ранжировать должен её сервисом.

Две реализации за одним протоколом:

* `LocalCrossEncoder` — офлайн-путь: тесты, демонстрация без сети, разработка.
* `RemoteReranker` — боевой путь: сервис платформы.

Протокол намеренно узкий — `predict(pairs) -> scores`, как у `sentence_transformers`:
вызывающий код не должен знать, где считается модель.

**Побочный, но важный результат.** Оценки `ms-marco-MiniLM` не калиброваны на
русском корпусе: вопрос «что приготовить из курицы» набирал больше, чем вопрос
про трансграничную передачу ПДн, и порог отказа пришлось ставить на косинус
эмбеддера. У `bge-reranker-v2-m3` разделение чистое (0,999 против 0,000), то есть
порог можно вернуть туда, где ему место, — на релевантность, а не на близость.
"""
import json
import urllib.error
import urllib.request

from .config import settings


class RerankUnavailable(RuntimeError):
    """Сервис ранжирования недоступен — и это НЕ «ответа нет в корпусе».

    Отдельный тип исключения существует ради одного: не дать сбою инфраструктуры
    выдать себя за пустую выдачу. Пользователю, получившему «не нашёл
    релевантных пунктов» при лежащем реранкере, система сообщает неправду о
    корпусе — и он уйдёт с выводом, что регламента не существует.
    """


class LocalCrossEncoder:
    """Cross-encoder в процессе. Медленно, зато без сети и без ключей."""

    #: Логиты ms-marco на русском корпусе не разделяют «в корпусе» и «вне»:
    #: замер дал худший свой 8.2658 против лучшего чужого 8.9686 — перекрытие.
    #: Поэтому порог отказа на этих оценках ставить нельзя.
    calibrated = False

    def __init__(self, model: str):
        from sentence_transformers import CrossEncoder
        self.model_name = model
        self._model = CrossEncoder(model)

    def predict(self, pairs):
        return self._model.predict(pairs)


class RemoteReranker:
    """Сервис ранжирования платформы (Infinity, Jina-совместимый `/rerank`).

    Вызов один на весь набор кандидатов, а не по паре: сервис батчит их сам, и
    именно в этом выигрыш — один поход в сеть против прогона модели на CPU.
    """

    #: Оценки в 0..1 и разделяют: 0.9919 худший свой против 0.0004 лучшего чужого.
    #: На таком зазоре порог отказа осмыслен.
    calibrated = True

    def __init__(self, url: str, model: str, api_key: str = "", timeout: float = 20.0):
        self.url = url.rstrip("/") + "/rerank"
        self.model_name = model
        self.api_key = api_key
        self.timeout = timeout
        #: Последний известный исход. Читается `/healthz` — чтобы недоступность
        #: внешней зависимости была видна снаружи, а не только в логах.
        self.healthy = True

    def _retrying_call(self, payload):
        """Один повтор — и только там, где он осмыслен.

        Что повторяем: обрыв соединения и ответы 5xx. Обрыв обычно означает
        закрытое keep-alive соединение или перезапуск пода, то есть состояние,
        которое вторая попытка застаёт уже исправленным.

        Что НЕ повторяем:

        * **таймаут** — он означает, что сервису тяжело, и повтор добавляет ему
          нагрузки ровно тогда, когда это хуже всего. Здесь повтор не чинит
          запрос, а ускоряет обвал;
        * **4xx** — это ошибка конфигурации, а не сбой: неверный ключ, неизвестная
          модель, кривой запрос. Вторая попытка вернёт ровно то же, потратив
          время пользователя;
        * **непонятный ответ** — если пришёл не тот JSON, повтор его не исправит,
          а продолжать на мусорных оценках нельзя: порядок кандидатов молча
          станет случайным, и никто этого не заметит.
        """
        try:
            return self._call(payload)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise RerankUnavailable(
                    f"сервис ранжирования отклонил запрос: HTTP {e.code}") from e
            retry_reason = f"HTTP {e.code}"
        except TimeoutError as e:                      # socket.timeout — его алиас
            raise RerankUnavailable(
                f"таймаут сервиса ранжирования ({self.timeout} с)") from e
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), TimeoutError):
                raise RerankUnavailable(
                    f"таймаут сервиса ранжирования ({self.timeout} с)") from e
            retry_reason = str(e.reason)
        except (ValueError, KeyError) as e:            # JSONDecodeError — подкласс ValueError
            raise RerankUnavailable(f"неожиданный ответ сервиса ранжирования: {e}") from e

        try:
            return self._call(payload)
        except Exception as e:
            raise RerankUnavailable(
                f"сервис ранжирования недоступен ({retry_reason}, повтор: {e})") from e

    def _call(self, payload):
        req = urllib.request.Request(self.url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def predict(self, pairs):
        if not pairs:
            return []
        query = pairs[0][0]                     # у всех пар запрос один и тот же
        documents = [text for _, text in pairs]
        payload = json.dumps({"model": self.model_name, "query": query,
                              "documents": documents, "top_n": len(documents)}).encode()

        try:
            data = self._retrying_call(payload)
        except RerankUnavailable:
            self.healthy = False
            raise

        self.healthy = True
        # Сервис возвращает результаты в порядке убывания оценки; вызывающему
        # коду нужен порядок ИСХОДНЫХ пар, иначе ранжирование поедет молча.
        scores = [0.0] * len(documents)
        for item in data.get("results", []):
            scores[int(item["index"])] = float(item["relevance_score"])
        return scores


def build_reranker(cfg=settings):
    """Сервис платформы при заданном `SUFLER_RERANK_URL`, иначе локальная модель."""
    if cfg.rerank_url:
        return RemoteReranker(cfg.rerank_url, cfg.rerank_model_remote, cfg.rerank_api_key)
    return LocalCrossEncoder(cfg.rerank_model)
