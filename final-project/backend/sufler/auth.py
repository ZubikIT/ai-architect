"""Граница доверия: контекст субъекта из проверенного JWT, а не из тела запроса (ADR-0016).

До этого модуля роли приходили в теле `/ask` — то есть клиент сам объявлял, что
ему можно. Это Spoofing из STRIDE-таблицы [методики занятия 33] и прямое
расхождение с ADR-0016: «контекст субъекта берётся из проверенного токена, а не
из тела запроса» (урок 26). Здесь это расхождение закрывается.

Правила, каждое из которых закрывает конкретную атаку:

1. **Только асимметричные алгоритмы.** Список разрешённых фиксирован и не
   берётся из заголовка токена. Классическая подмена `RS256 → HS256`, где
   публичный ключ выдаётся за секрет HMAC, не проходит: HS* просто нет в списке.
   `alg: none` не проходит по той же причине. (PyJWT отвергает такой токен и
   сам — ключ приходит объектом, а не байтами, — но полагаться на защиту чужой
   библиотеки вместо своей проверки нельзя: она переживёт смену библиотеки.)
2. **Ключ выбирается по `kid` из JWKS Keycloak**, а не из токена. При неизвестном
   `kid` кэш обновляется один раз — это ротация ключей, а не повод доверять.
3. **Проверяются `exp`/`nbf`/`iat`**, а при заданных значениях — `aud` и `iss`.
   Токен соседнего клиента того же realm не должен открывать наш контур.
4. **Роли берутся из claim'а токена** (по умолчанию `groups`, ADR-0016). Тело
   запроса на доступ не влияет вообще — не «влияет меньше», а не влияет.

Без `OIDC_JWKS_URL` сервис остаётся в dev-режиме (роли из тела) — и говорит об
этом в `/healthz`. Молчаливый dev-режим в проде опаснее отсутствующего.
"""
import json
import threading
import time
import urllib.request

from .access import RequestContext

# Асимметричные подписи Keycloak. HS*/none отсутствуют намеренно — см. правило 1.
ALLOWED_ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "ES256", "ES384")


class AuthError(Exception):
    """Отказ в аутентификации. Наверх уходит как 401 — без подробностей клиенту:
    сообщение о том, какая именно проверка не прошла, помогает подбирать токен."""


class JwksCache:
    """Ключи Keycloak с TTL. Сеть в air-gapped-контуре дешёвая, но не бесплатная:
    ходить в JWKS на каждый запрос — это лишняя точка отказа на горячем пути."""

    def __init__(self, url: str, ttl: int = 300, timeout: float = 3.0):
        self.url, self.ttl, self.timeout = url, ttl, timeout
        self._keys, self._fetched_at = {}, 0.0
        self._lock = threading.Lock()

    def _fetch(self) -> dict:
        with urllib.request.urlopen(self.url, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def get(self, kid: str, refresh: bool = False):
        """Ключ по `kid`. `refresh=True` — однократное обновление на ротацию."""
        with self._lock:
            stale = time.time() - self._fetched_at > self.ttl
            if refresh or stale or not self._keys:
                try:
                    jwks = self._fetch()
                except Exception as e:
                    if not self._keys:      # первый запуск и провайдер недоступен
                        raise AuthError(f"JWKS недоступен: {type(e).__name__}") from e
                    return self._keys.get(kid)   # переживаем сбой на кэше
                self._keys = {k["kid"]: k for k in jwks.get("keys", []) if "kid" in k}
                self._fetched_at = time.time()
            return self._keys.get(kid)


def _claim(claims: dict, path: str):
    """Значение claim'а по точечному пути: `groups` или `realm_access.roles`."""
    node = claims
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class TokenVerifier:
    """Проверка access token и сборка `RequestContext` — единственная точка,
    где внешний ввод превращается в права."""

    def __init__(self, settings):
        import jwt                     # импорт здесь: в dev-режиме зависимость не нужна
        from jwt import PyJWKClient     # noqa: F401  (проверка, что установлен crypto-экстра)
        self._jwt = jwt
        self.settings = settings
        self.jwks = JwksCache(settings.oidc_jwks_url, ttl=settings.oidc_jwks_ttl)

    def _key_for(self, token: str):
        try:
            header = self._jwt.get_unverified_header(token)
        except Exception as e:
            raise AuthError("повреждённый токен") from e
        if header.get("alg") not in ALLOWED_ALGORITHMS:
            # Отсекаем до обращения к ключам: alg из заголовка — это заявление
            # атакующего о том, как его проверять.
            raise AuthError("недопустимый алгоритм подписи")
        kid = header.get("kid")
        if not kid:
            raise AuthError("в токене нет kid")
        jwk = self.jwks.get(kid) or self.jwks.get(kid, refresh=True)
        if jwk is None:
            raise AuthError("ключ подписи неизвестен")
        return self._jwt.PyJWK(jwk).key

    def claims(self, token: str) -> dict:
        options, kwargs = {"require": ["exp"]}, {}
        if self.settings.oidc_audience:
            kwargs["audience"] = self.settings.oidc_audience
        else:
            options["verify_aud"] = False
        if self.settings.oidc_issuer:
            kwargs["issuer"] = self.settings.oidc_issuer
        try:
            return self._jwt.decode(token, self._key_for(token),
                                    algorithms=list(ALLOWED_ALGORITHMS),
                                    options=options, **kwargs)
        except AuthError:
            raise
        except Exception as e:
            raise AuthError(f"токен отклонён: {type(e).__name__}") from e

    def context(self, authorization: str) -> RequestContext:
        """`Authorization: Bearer <token>` → контекст субъекта."""
        if not authorization or not authorization.lower().startswith("bearer "):
            raise AuthError("нужен заголовок Authorization: Bearer")
        claims = self.claims(authorization.split(None, 1)[1].strip())

        raw = _claim(claims, self.settings.oidc_roles_claim)
        if isinstance(raw, str):
            raw = [raw]
        # Keycloak отдаёт группы путями («/hr», «/legal/senior») — берём последний
        # сегмент: метки ACL в корпусе плоские (ADR-0016, материализация прав).
        roles = [str(r).rsplit("/", 1)[-1].strip() for r in (raw or []) if str(r).strip()]

        subject = claims.get("preferred_username") or claims.get("sub") or "anonymous"
        return RequestContext.of(roles, subject=subject)


def build_verifier(settings):
    """Верификатор при заданном `OIDC_JWKS_URL`, иначе None (dev-режим)."""
    return TokenVerifier(settings) if settings.oidc_jwks_url else None
