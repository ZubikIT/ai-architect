# Fly.io — деплой интерактивного Structurizr Lite

Публикует интерактивную копию `lesson-05-workspace.dsl` на постоянный URL `https://ai-architect.fly.dev/workspace/1/diagrams`.

## Где что лежит

- `/Dockerfile` (в корне репо) — `structurizr/structurizr:latest` + COPY `lesson-05-workspace.dsl` → `/usr/local/structurizr/workspace.dsl`, запускает `local`.
- `/fly.toml` (в корне репо) — app `ai-architect`, регион `fra`, 256 MB shared-cpu, auto-stop при простое.
- DSL остаётся источником правды в `02-architecture/artifacts/lesson-05-workspace.dsl`.

Файлы в корне специально — Fly GitHub auto-deploy ищет `Dockerfile`+`fly.toml` именно там.

## Деплой

Два варианта.

### Вариант 1. GitHub auto-deploy (настроено)

Fly подписан на GitHub-репо `ZubikIT/ai-architect`. Каждый push в `main` → Fly сам собирает образ и катит. Никаких локальных команд не надо.

Чтобы это работало, рабочий цикл такой:

```bash
git push origin main          # GitLab
git push github main          # GitHub → триггерит Fly auto-deploy
```

### Вариант 2. CLI деплой с локалки

```bash
cd /Users/zubik/www/artcloud/ai/architect
flyctl deploy
```

flyctl возьмёт `fly.toml` и `Dockerfile` из текущей папки.

## Полезные команды

```bash
flyctl status -a ai-architect      # состояние машин
flyctl logs -a ai-architect        # логи Lite
flyctl open -a ai-architect        # открыть в браузере
flyctl auth token                  # вывести API token (для GitLab CI/GitHub Actions)
flyctl scale memory 512 -a ai-architect   # если 256 МБ не хватит
flyctl destroy ai-architect -y     # удалить приложение
```

## Тарификация

Free-tier Fly.io 2026:
- shared-cpu-1x VM 256 MB с auto-stop фактически бесплатна — машина «спит» без трафика и стартует за 2 сек на первый запрос.
- 3 GB исходящего трафика в месяц — для C4-диаграмм с запасом.

## Если хочется автодеплой из GitLab вместо GitHub

```yaml
fly-deploy:
  stage: deploy
  image: ghcr.io/superfly/flyctl:latest
  script:
    - flyctl deploy --remote-only --access-token "$FLY_API_TOKEN"
  rules:
    - if: $CI_COMMIT_BRANCH == "main" && $FLY_API_TOKEN
```

`FLY_API_TOKEN` берётся через `flyctl auth token` и кладётся в GitLab → Settings → CI/CD → Variables (masked + protected).
