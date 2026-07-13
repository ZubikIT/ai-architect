# Происхождение снапшота

- **Источник:** <https://github.com/NickOsipov/otus-mlops-terraform-nov> — практический репозиторий к уроку 18 «Инфраструктура как код (IaC) и CI/CD» (live-деплой в Yandex Cloud).
- **Зафиксированный коммит:** `ef6daaa9a09d8269d6b8417ae4f9fb4b662cca52`
- **Дата снятия снапшота:** 2026-07-13
- **Лицензия:** в исходном репозитории файла LICENSE нет (на момент снятия). Копия сохранена **в учебных целях** как архив материала занятия; авторство — за владельцем оригинального репозитория.

## Что внутри (как разбиралось на вебинаре)
- `infra/main.tf` — весь словарь лекции на одном экране: `yandex_compute_disk` + `yandex_compute_instance` (nat, ssh-keys через metadata), `yandex_vpc_network`/`subnet`, SA + роль `storage.admin` + static access key, `yandex_storage_bucket`.
- `infra/provider.tf` — пустой в снапшоте (заполнялся live: провайдер `yandex-cloud/yandex`, OAuth-токен/cloud_id/folder_id).
- `infra/variables.tf` + `infra/terraform.tfvars.example` — параметризация; реальный tfvars с токеном в .gitignore.
- `commands.sh` — `yc compute image list` для выбора image_id.
- `README.md` — план практики: init → plan → apply → ssh-проверка → destroy.

## Обновить снапшот
```bash
git clone https://github.com/NickOsipov/otus-mlops-terraform-nov.git /tmp/otus-tf
# скопировать содержимое (кроме .git) сюда, обновить коммит/дату выше
```
