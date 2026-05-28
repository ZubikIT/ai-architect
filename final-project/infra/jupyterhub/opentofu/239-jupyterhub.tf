# JupyterHub — отдельная ВМ для интерактивной проверки notebook'ов курса
# (ДЗ-07 «TripBuddy» и будущие ДЗ). За Keycloak (vm 219) через OAuth, DockerSpawner.
# ЧЕРНОВИК — сверить перед `tofu plan/apply`:
#   - vm_id 239 свободен; IP 10.100.1.47 свободен (см. CLAUDE.md → «Проверка занятых IP»);
#   - compose живёт в репо artcloud/devops/jupyterhub (клонится cloud-init'ом в /opt/jupyterhub);
#   - в Keycloak realm `artcloud` создан client `jupyterhub`, secret лежит в Vault.
# Паттерн повторяет 238-qdrant.tf.

# Прокси-токен для configurable-http-proxy (внутренняя коммуникация hub ↔ proxy).
resource "random_password" "jupyterhub_proxy_token" {
  length  = 64
  special = false # уходит в HTTP-заголовок Authorization — без спецсимволов спокойнее
}

# Client secret и whitelist лежат в Vault — кладёт администратор Keycloak.
# Ожидаемые поля в secret/jupyterhub/keycloak-oauth:
#   client_id        — Keycloak client ID, обычно "jupyterhub"
#   client_secret    — confidential client secret
#   realm_base_url   — например https://keycloak.example.lan/realms/artcloud/protocol/openid-connect
#   whitelist        — CSV preapproved-email'ов: "teacher@otus.ru,alexzub2009@gmail.com"
data "vault_kv_secret_v2" "jupyterhub_keycloak" {
  mount = "secret"
  name  = "jupyterhub/keycloak-oauth"
}

module "jupyterhub" {
  source = "./modules/vms"
  common = local.common # тот же общий local.common, что у боевых ВМ (qdrant исп. свой qdrant_common из-за миграции pve-нод; если миграция к моменту apply ещё идёт — продублировать аналогично)

  name      = "jupyterhub"
  vm_id     = "239"
  node      = "pve"
  ip        = "10.100.1.47/24" # сверить, что свободен
  cpu_cores = 2
  memory    = 4096 # 4 ГБ — 1-5 одновременных юзеров; поднять при росте
  disk_size = 30   # singleuser home'ы лежат тут; рост — отдельный диск

  image_file_id = proxmox_virtual_environment_download_file.ubuntu_24_noble_20260518_img.id

  # cloud-init: ./cloud-init/239-jupyterhub.yaml
  template_vars = {
    keycloak_client_id     = data.vault_kv_secret_v2.jupyterhub_keycloak.data["client_id"]
    keycloak_client_secret = data.vault_kv_secret_v2.jupyterhub_keycloak.data["client_secret"]
    keycloak_realm_url     = data.vault_kv_secret_v2.jupyterhub_keycloak.data["realm_base_url"]
    whitelist              = data.vault_kv_secret_v2.jupyterhub_keycloak.data["whitelist"]
    proxy_token            = random_password.jupyterhub_proxy_token.result
  }
}
