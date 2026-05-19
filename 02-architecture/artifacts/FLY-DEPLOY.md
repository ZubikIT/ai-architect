# Деплой Structurizr Lite на Fly.io

Публикует интерактивную копию `lesson-05-workspace.dsl` на постоянный URL `https://<app-name>.fly.dev/`.

## Файлы

- `Dockerfile.structurizr` — образ на основе `structurizr/structurizr:latest`, с зашитой `lesson-05-workspace.dsl` под именем `workspace.dsl` (конвенция Lite).
- `fly.toml` — Fly app config: регион `fra`, 256 MB RAM, shared CPU, auto-stop при простое.

## Разовая настройка

```bash
# 1. Поставить flyctl
brew install flyctl                   # macOS
# или: curl -L https://fly.io/install.sh | sh

# 2. Логин (создаст аккаунт если нет; нужна почта + привязка карты для подтверждения, free-tier не списывается)
flyctl auth signup                    # если ещё нет аккаунта
flyctl auth login                     # если уже есть

# 3. Создать приложение под именем из fly.toml (или своим — поменяй `app` в fly.toml)
cd 02-architecture/artifacts
flyctl apps create sufler-bft-otus    # имя должно быть глобально уникальным
```

## Деплой

```bash
cd 02-architecture/artifacts
flyctl deploy
```

flyctl автоматически:
1. Соберёт `Dockerfile.structurizr` (контекст = текущая папка → `lesson-05-workspace.dsl` попадает внутрь).
2. Запушит образ в Fly registry.
3. Поднимет VM в регионе `fra` с auto-stop при простое (бесплатно «спит» — стартует за ~2 сек при первом запросе).

После завершения откроется `https://sufler-bft-otus.fly.dev/workspace/1/diagrams`.

## Обновление DSL

Любая правка `lesson-05-workspace.dsl` → `flyctl deploy` → новая версия за минуту.

Чтобы автоматизировать через GitLab CI:

```yaml
fly-deploy:
  stage: deploy
  image: ghcr.io/superfly/flyctl:latest
  script:
    - cd 02-architecture/artifacts
    - flyctl deploy --remote-only --access-token "$FLY_API_TOKEN"
  rules:
    - if: $CI_COMMIT_BRANCH == "main" && $FLY_API_TOKEN
```

`FLY_API_TOKEN` берётся командой `flyctl auth token` и кладётся в GitLab → Settings → CI/CD → Variables (masked + protected).

## Тарификация

Free-tier Fly.io 2026:
- До 3 shared-CPU-1x VM 256 MB бесплатно (если суммарное время работы — в пределах квоты ~3000 часов/мес).
- Auto-stop в `fly.toml` (`auto_stop_machines = "stop"`, `min_machines_running = 0`) гарантирует, что VM засыпает без трафика → деньги не уходят, даже если кто-то посмотрит ссылку раз в неделю.

## Проверка

```bash
flyctl status -a sufler-bft-otus      # состояние машин
flyctl logs -a sufler-bft-otus        # логи Lite
flyctl open -a sufler-bft-otus        # открыть в браузере
flyctl destroy sufler-bft-otus -y     # удалить приложение и забыть
```
