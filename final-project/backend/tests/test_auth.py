"""Граница доверия: права приходят из подписи, а не из тела запроса (ADR-0016).

До этого слоя обязательный сценарий ТЗ «User B не получает закрытый документ»
держался на честном клиенте: роли брались из тела `/ask`, и «User B» мог просто
прислать `roles: ["legal"]`. Здесь проверяется, что так больше нельзя.

Негативные случаи — не формальность: `alg: none` и подмена `RS256 → HS256`
(публичный ключ выдаётся за секрет HMAC) — это первое, что пробует red teaming
по [методике занятия 33](../../sessions/33-konsultaciya.md), и ровно тот класс
ошибок, из-за которого валидация JWT «есть», но не работает.
"""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from sufler.auth import AuthError, JwksCache, TokenVerifier
from sufler.config import Settings

KID = "test-key-1"
RESTRICTED = "dostup-pdn"
PDN_QUESTION = "Как обрабатываются персональные данные командированного работника?"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid=KID, use="sig", alg="RS256")
    return key, {"keys": [jwk]}


@pytest.fixture
def settings_jwt():
    return Settings(oidc_jwks_url="https://keycloak.internal/realms/corp/protocol/openid-connect/certs",
                    oidc_roles_claim="groups")


@pytest.fixture
def verifier(monkeypatch, keypair, settings_jwt):
    """Верификатор с подменённым источником ключей: сети в тестах нет."""
    _, jwks = keypair
    calls = {"n": 0}

    def fake_fetch(self):
        calls["n"] += 1
        return jwks

    monkeypatch.setattr(JwksCache, "_fetch", fake_fetch)
    v = TokenVerifier(settings_jwt)
    v.fetch_calls = calls
    return v


def forge_hs256(payload: dict, secret: str, kid: str = KID) -> str:
    """Подделка RS256 → HS256 вручную.

    Через `jwt.encode` её не собрать: PyJWT отказывается использовать PEM как
    секрет HMAC. Атакующий такой заботой не связан — поэтому токен собирается
    побайтово, и проверяется именно сторона валидации, а не чужая защита.
    """
    import base64
    import hashlib
    import hmac

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid},
                            separators=(",", ":")).encode())
    body = b64(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = header + b"." + body
    sig = b64(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + sig).decode()


def make_token(key, *, groups=("all",), subject="user-b", ttl=300, kid=KID, **extra):
    claims = {"sub": subject, "preferred_username": subject, "groups": list(groups),
              "iat": int(time.time()), "exp": int(time.time()) + ttl, **extra}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


# --------------------------------------------------------------------------- #
#  Нормальный путь
# --------------------------------------------------------------------------- #
def test_roles_come_from_signed_claim(verifier, keypair):
    key, _ = keypair
    ctx = verifier.context("Bearer " + make_token(key, groups=["legal", "security"], subject="user-a"))
    assert ctx.roles == ("legal", "security")
    assert ctx.subject == "user-a"          # атрибуция действия для аудита


def test_keycloak_group_paths_are_flattened(verifier, keypair):
    """Keycloak отдаёт группы путями; метки ACL в корпусе плоские (ADR-0016)."""
    key, _ = keypair
    ctx = verifier.context("Bearer " + make_token(key, groups=["/legal", "/hr"]))
    assert set(ctx.roles) == {"legal", "hr"}


def test_empty_groups_fall_back_to_public(verifier, keypair):
    """Токен без групп — это «только общедоступное», а не «всё» (deny-by-default)."""
    key, _ = keypair
    assert verifier.context("Bearer " + make_token(key, groups=[])).roles == ("all",)


def test_jwks_is_cached(verifier, keypair):
    """Ключи не тянутся на каждый запрос: JWKS на горячем пути — точка отказа."""
    key, _ = keypair
    for _ in range(3):
        verifier.context("Bearer " + make_token(key))
    assert verifier.fetch_calls["n"] == 1


# --------------------------------------------------------------------------- #
#  Негативные случаи
# --------------------------------------------------------------------------- #
def test_missing_and_malformed_headers_rejected(verifier, keypair):
    key, _ = keypair
    for header in ("", "Basic dXNlcjpwYXNz", "Bearer", "Bearer не-токен"):
        with pytest.raises(AuthError):
            verifier.context(header)


def test_expired_token_rejected(verifier, keypair):
    key, _ = keypair
    with pytest.raises(AuthError):
        verifier.context("Bearer " + make_token(key, ttl=-10))


def test_token_without_exp_rejected(verifier, keypair):
    """Бессрочный токен — это отозванный доступ, который продолжает работать."""
    key, _ = keypair
    claims = {"sub": "user-b", "groups": ["legal"], "iat": int(time.time())}
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})
    with pytest.raises(AuthError):
        verifier.context("Bearer " + token)


def test_foreign_signature_rejected(verifier):
    """Подпись чужим ключом того же алгоритма."""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        verifier.context("Bearer " + make_token(other, groups=["legal"]))


def test_algorithm_confusion_rs256_to_hs256_rejected(verifier, keypair):
    """Классика: публичный ключ выдаётся за секрет HMAC.

    Отсекается нашим фиксированным списком алгоритмов (сообщение «недопустимый
    алгоритм подписи»), и это первая линия. Вторая — сам PyJWT: ключ приходит
    объектом `RSAPublicKey`, и HMAC его не принимает даже если HS256 внести в
    список. Тест фиксирует результат, а не то, какая из двух линий сработала
    первой: при смене библиотеки останется только наша.
    """
    key, _ = keypair
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    forged = forge_hs256({"sub": "attacker", "groups": ["legal", "security"],
                          "exp": int(time.time()) + 300}, pub_pem)
    with pytest.raises(AuthError):
        verifier.context("Bearer " + forged)


def test_alg_none_rejected(verifier):
    """Токен без подписи вообще."""
    forged = jwt.encode({"sub": "attacker", "groups": ["legal"], "exp": int(time.time()) + 300},
                        key="", algorithm="none", headers={"kid": KID})
    with pytest.raises(AuthError):
        verifier.context("Bearer " + forged)


def test_unknown_kid_rejected(verifier, keypair):
    key, _ = keypair
    with pytest.raises(AuthError):
        verifier.context("Bearer " + make_token(key, kid="подменённый-kid"))


def test_audience_and_issuer_are_enforced(monkeypatch, keypair):
    """Токен соседнего клиента того же realm не открывает наш контур."""
    key, jwks = keypair
    monkeypatch.setattr(JwksCache, "_fetch", lambda self: jwks)
    v = TokenVerifier(Settings(oidc_jwks_url="https://kc/certs", oidc_roles_claim="groups",
                               oidc_audience="sufler", oidc_issuer="https://kc/realms/corp"))

    ok = make_token(key, groups=["legal"], aud="sufler", iss="https://kc/realms/corp")
    assert v.context("Bearer " + ok).roles == ("legal",)

    for bad in (make_token(key, groups=["legal"], aud="other-client", iss="https://kc/realms/corp"),
                make_token(key, groups=["legal"], aud="sufler", iss="https://evil/realms/corp")):
        with pytest.raises(AuthError):
            v.context("Bearer " + bad)


# --------------------------------------------------------------------------- #
#  Сквозной сценарий ТЗ через HTTP: «User B» больше не назначает себе роли
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(monkeypatch, keypair, engine):
    """API в режиме Keycloak, поверх уже построенного движка (модели не грузим заново)."""
    _, jwks = keypair
    monkeypatch.setattr(JwksCache, "_fetch", lambda self: jwks)

    from sufler import api
    from sufler.config import settings
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://kc/certs")
    monkeypatch.setattr(settings, "oidc_roles_claim", "groups")
    monkeypatch.setattr(api, "_engine", engine)
    monkeypatch.setattr(api, "_verifier", None)
    monkeypatch.setattr(api, "_verifier_built", False)
    yield TestClient(api.app)
    api._verifier, api._verifier_built = None, False


def test_healthz_admits_the_auth_mode(client):
    assert client.get("/healthz").json()["auth"] == "jwt"


def test_request_without_token_is_rejected(client):
    r = client.post("/ask", json={"question": PDN_QUESTION, "roles": ["legal"]})
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_body_roles_are_ignored_when_token_present(client, keypair):
    """Ключевая проверка: «User B» просит роль legal в теле, токен говорит иное."""
    key, _ = keypair
    token = make_token(key, groups=["all"], subject="user-b")
    r = client.post("/ask", json={"question": PDN_QUESTION, "roles": ["legal", "security"]},
                    headers={"Authorization": "Bearer " + token})
    assert r.status_code == 200
    body = r.json()
    assert all(RESTRICTED not in s["doc"] for s in body["sources"]), \
        "роли из тела запроса повлияли на доступ"
    assert "минимальных привилегий" not in " ".join(body["contexts"])


def test_token_roles_open_the_restricted_document(client, keypair):
    """User A с подписанной ролью legal получает ЛПА-03 — и только он."""
    key, _ = keypair
    token = make_token(key, groups=["legal"], subject="user-a")
    body = client.post("/ask", json={"question": PDN_QUESTION},
                       headers={"Authorization": "Bearer " + token}).json()
    assert any(RESTRICTED in s["doc"] for s in body["sources"])


def test_multi_agent_path_honours_the_token(client, keypair):
    """Мультиагентный путь проходит ту же границу доверия, а не более слабую."""
    key, _ = keypair
    forged = client.post("/agents/ask", json={"question": PDN_QUESTION, "roles": ["legal"]},
                         headers={"Authorization": "Bearer " + make_token(key, groups=["all"])})
    assert all(RESTRICTED not in s["doc"] for s in forged.json()["sources"])
    assert client.post("/agents/ask", json={"question": PDN_QUESTION}).status_code == 401


# --------------------------------------------------------------------------- #
#  Dev-режим: демо без Keycloak обязано продолжать работать
# --------------------------------------------------------------------------- #
def test_dev_mode_still_serves_demo(monkeypatch, engine):
    """Без OIDC_JWKS_URL роли берутся из тела — и сервис честно сообщает об этом."""
    from sufler import api
    from sufler.config import settings
    monkeypatch.setattr(settings, "oidc_jwks_url", "")
    monkeypatch.setattr(api, "_engine", engine)
    monkeypatch.setattr(api, "_verifier", None)
    monkeypatch.setattr(api, "_verifier_built", False)
    client = TestClient(api.app)

    assert client.get("/healthz").json()["auth"] == "dev"
    body = client.post("/ask", json={"question": PDN_QUESTION, "roles": ["legal"]}).json()
    assert any(RESTRICTED in s["doc"] for s in body["sources"])
    api._verifier, api._verifier_built = None, False
