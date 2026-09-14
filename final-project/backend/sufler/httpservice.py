"""Общий транспорт к сервисам моделей платформы (Infinity).

Ранжирование и эмбеддинги живут в одном сервисе, за одним ключом, и отказывают
одинаково. Политика повторов у них тоже обязана быть одна: расхождение здесь
означает, что один компонент добивает падающий сервис повторами, пока второй
корректно сдаётся, — и разбирать такой инцидент невозможно.

Поэтому HTTP-вызов и решение «повторять или нет» живут в одном месте, а
специфика остаётся в наследниках: свой путь, своё тело запроса, свой разбор
ответа и свой тип исключения.
"""
import json
import urllib.error
import urllib.request


class ServiceUnavailable(RuntimeError):
    """Сервис моделей недоступен — и это НЕ «ответа нет в корпусе».

    Отдельный тип существует ради одного: не дать сбою инфраструктуры выдать
    себя за пустую выдачу. Пользователь, получивший «не нашёл релевантных
    пунктов» при лежащем сервисе, уйдёт с выводом, что регламента не существует.
    """


class RemoteModelService:
    """Базовый вызов сервиса: один повтор, и только там, где он осмыслен."""

    #: Человекочитаемое имя для текста ошибки — задаётся наследником.
    service_name = "сервис моделей"
    #: Тип исключения наследника; обязан быть подклассом ServiceUnavailable.
    error = ServiceUnavailable

    def __init__(self, url: str, path: str, model: str, api_key: str = "",
                 timeout: float = 20.0):
        self.url = url.rstrip("/") + path
        self.model_name = model
        self.api_key = api_key
        self.timeout = timeout
        #: Последний известный исход. Читается `/healthz` — чтобы недоступность
        #: внешней зависимости была видна снаружи, а не только в логах.
        self.healthy = True

    def _call(self, payload):
        req = urllib.request.Request(self.url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

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
          а продолжать на мусорных числах нельзя: результат молча станет
          случайным, и никто этого не заметит.
        """
        try:
            return self._call(payload)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise self.error(f"{self.service_name} отклонил запрос: HTTP {e.code}") from e
            retry_reason = f"HTTP {e.code}"
        except TimeoutError as e:                      # socket.timeout — его алиас
            raise self.error(f"таймаут: {self.service_name} ({self.timeout} с)") from e
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), TimeoutError):
                raise self.error(f"таймаут: {self.service_name} ({self.timeout} с)") from e
            retry_reason = str(e.reason)
        except (ValueError, KeyError) as e:            # JSONDecodeError — подкласс ValueError
            raise self.error(f"неожиданный ответ: {self.service_name}: {e}") from e

        try:
            return self._call(payload)
        except Exception as e:
            raise self.error(
                f"{self.service_name} недоступен ({retry_reason}, повтор: {e})") from e

    def _request(self, payload):
        """Вызов с отметкой здоровья: её читает `/healthz`."""
        try:
            data = self._retrying_call(json.dumps(payload).encode())
        except ServiceUnavailable:
            self.healthy = False
            raise
        self.healthy = True
        return data
