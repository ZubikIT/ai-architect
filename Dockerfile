# Structurizr Lite через новый structurizr/structurizr local, с зашитой DSL «Суфлёр БФТ».
# Деплоится на Fly.io (см. fly.toml в корне). Сборка идёт из корня репо.
FROM structurizr/structurizr:latest

# Имя файла строго `workspace.dsl` — конвенция Structurizr Lite/local.
COPY 02-architecture/artifacts/lesson-05-workspace.dsl /usr/local/structurizr/workspace.dsl

# Fly.io прокидывает свой PORT через env. Образ читает его в entrypoint (-Dserver.port=${PORT}).
ENV PORT=8080
EXPOSE 8080

# Subcommand `local` поднимает встроенный веб-сервер с UI и просмотрщиком C4-диаграмм.
CMD ["local"]
