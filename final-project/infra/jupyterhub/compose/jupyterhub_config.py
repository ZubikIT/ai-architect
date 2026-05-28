"""
JupyterHub config — OAuth через Keycloak + DockerSpawner с ресурс-лимитами.

ENV-переменные приходят из .env (заполняется cloud-init'ом из template_vars OpenTofu):
  KEYCLOAK_CLIENT_ID, KEYCLOAK_CLIENT_SECRET, KEYCLOAK_REALM_URL,
  OAUTH_CALLBACK_URL, WHITELIST (CSV email'ов), CONFIGPROXY_AUTH_TOKEN.
"""
import os

# ====== базовые ======
c = get_config()  # noqa: F821 — JupyterHub инжектит при загрузке конфига

c.JupyterHub.bind_url = "http://:8000"
c.JupyterHub.hub_ip = "jupyterhub"           # имя контейнера в сети jupyterhub_net
c.JupyterHub.hub_connect_ip = "jupyterhub"

# DB hub'а лежит на volume jupyterhub_data → переживёт docker compose down.
c.JupyterHub.db_url = "sqlite:////srv/jupyterhub/jupyterhub.sqlite"
c.JupyterHub.cookie_secret_file = "/srv/jupyterhub/jupyterhub_cookie_secret"

# токен для configurable-http-proxy — из .env (генерим в OpenTofu)
c.ConfigurableHTTPProxy.auth_token = os.environ["CONFIGPROXY_AUTH_TOKEN"]

# Между рестартами хаба пользовательские контейнеры **не** убиваем — потом подцепимся.
c.JupyterHub.cleanup_servers = False


# ====== аутентификация: Keycloak via OAuth ======
from oauthenticator.generic import GenericOAuthenticator  # noqa: E402

c.JupyterHub.authenticator_class = GenericOAuthenticator

keycloak_base = os.environ["KEYCLOAK_REALM_URL"].rstrip("/")
c.GenericOAuthenticator.client_id = os.environ["KEYCLOAK_CLIENT_ID"]
c.GenericOAuthenticator.client_secret = os.environ["KEYCLOAK_CLIENT_SECRET"]
c.GenericOAuthenticator.oauth_callback_url = os.environ["OAUTH_CALLBACK_URL"]
c.GenericOAuthenticator.authorize_url = f"{keycloak_base}/auth"
c.GenericOAuthenticator.token_url    = f"{keycloak_base}/token"
c.GenericOAuthenticator.userdata_url = f"{keycloak_base}/userinfo"
c.GenericOAuthenticator.username_claim = "email"
c.GenericOAuthenticator.login_service = "Keycloak"
c.GenericOAuthenticator.scope = ["openid", "email", "profile"]

# КРИТИЧНО: без whitelist любой Keycloak-юзер сможет логиниться.
allowed = {e.strip().lower() for e in os.environ.get("WHITELIST", "").split(",") if e.strip()}
c.Authenticator.allowed_users = allowed
c.Authenticator.admin_users = {"alexzub2009@gmail.com"}   # сверить с твоим email в Keycloak


# ====== spawner: per-user Docker container ======
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"

c.DockerSpawner.image = os.environ.get("DOCKER_NOTEBOOK_IMAGE", "tripbuddy-singleuser:latest")
c.DockerSpawner.network_name = os.environ.get("DOCKER_NETWORK_NAME", "jupyterhub_net")
c.DockerSpawner.notebook_dir = "/home/jovyan/work"
c.DockerSpawner.volumes = {
    "jupyterhub-user-{username}": "/home/jovyan/work",
}
c.DockerSpawner.extra_host_config = {
    "mem_limit": "2g",
    "cpu_quota": 100_000,    # = 1.0 CPU (cpu_period 100_000 по умолчанию)
}
c.DockerSpawner.remove = True        # удаляем контейнер по stop — не копим грязь
c.DockerSpawner.debug = True
c.DockerSpawner.environment = {
    # дефолт mock-режима, чтобы ноутбук работал «cold» без ключей
    "TRIPBUDDY_MODE": "mock",
}

# мягкий лимит на запуск (если образ ещё не закэширован — pull может быть долгим)
c.Spawner.start_timeout = 300
c.Spawner.http_timeout = 120
