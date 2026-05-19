workspace "Суфлёр БФТ — Voice AI Assistant" "Голосовой AI-ассистент для обзвона клиентов по бронированиям (БФТ-кейс из урока 2)" {

    model {
        # ---------- Акторы ----------
        guest = person "Клиент / Гость" "Получатель исходящего звонка с напоминанием о платеже"
        operator = person "Оператор КЦ" "Принимает эскалации от бота (отказ, агрессия, рассрочка)"
        manager = person "Менеджер отдела продаж" "Работает со сделками в Б24, видит таймлайн и транскрипцию"

        dataScientist = person "Data Scientist" "Мониторит метрики NLU, переобучает классификатор интентов" {
            tags "Internal_Technical_User"
        }
        annotator = person "Annotator" "Размечает диалоги (golden set), валидирует распознанные интенты" {
            tags "Internal_Operations_User"
        }

        # ---------- Внешние системы ----------
        b24 = softwareSystem "Bitrix24 (Б24)" "Корпоративный портал заказчика. Источник сделок и webhook'ов" {
            tags "External System"
        }
        ext1c = softwareSystem "1С" "Хранит статус оплаты по сделкам. Опрашивается перед звонком" {
            tags "External System"
        }
        sipTrunk = softwareSystem "SIP-Trunk (Asterisk)" "Телефония заказчика. Исходящие вызовы и SIP-REFER на КЦ" {
            tags "External System"
        }
        smsProvider = softwareSystem "SMS Provider" "Шлюз отправки SMS при недозвоне" {
            tags "External System"
        }
        llmProvider = softwareSystem "LLM Provider (RU)" "Self-hosted LLM (152-ФЗ). Классификация интентов и генерация фраз" {
            tags "External System"
        }
        sttProvider = softwareSystem "STT/TTS Provider" "SaluteSpeech / Yandex SpeechKit (RU-DC). Распознавание и синтез речи" {
            tags "External System"
        }

        # ---------- Наша система ----------
        sufler = softwareSystem "Суфлёр БФТ" "Голосовой AI-ассистент: обзвон, диалог, эскалация" {
            tags "Target System"

            # ----- Контейнеры (Level 2) -----
            adminUi = container "Admin Web UI" "Кабинет менеджера/аналитика: статусы кампаний, прослушивание, отчёты" "React / TypeScript" {
                tags "Web Browser"
            }

            backend = container "Backend (Orchestrator)" "API Gateway: приём webhook от Б24, постановка в очередь обзвона, бизнес-правила (BR-01..04)" "Python / FastAPI"

            aiService = container "AI Service (Dialog Engine)" "Управление голосовым диалогом: STT → NLU → диалог → TTS. Endpoint /get_recommendation" "Python / FastAPI"

            voiceGateway = container "Voice Gateway" "Медиа-мост: SIP/RTP с АТС, стримит аудио в AI Service, проигрывает синтез, делает SIP-REFER" "Python + pjsua2 / Asterisk ARI"

            scheduler = container "Call Scheduler" "Очередь и тайминги: окно 10:00–19:00 по локали отеля, лимит 30 СЛ / 5 CPS, ретраи через час" "Python Worker · Celery beat"

            reporter = container "Reporter" "Ежедневный Excel-отчёт в 08:00 МСК на email заказчика, метрика Hold Time" "Python Worker"

            sqlDb = container "Operational DB" "Сделки, звонки, транскрипции, статусы, метрики Hold Time" "PostgreSQL 15" {
                tags "Database"
            }

            vectorDb = container "Vector DB (Intents & Phrases)" "Семантический поиск похожих реплик клиента; банк фраз 'возражения'" "Qdrant" {
                tags "Database"
            }

            audioStore = container "Audio Storage" "WAV/OPUS-аудиозаписи звонков (TTL 30 дней по NFR-Security)" "S3-совместимое (RU-DC)" {
                tags "Database"
            }

            # ----- Компоненты AI Service (Level 3) -----
            aiService {
                controller = component "Controller (HTTP/WS)" "FastAPI: /get_recommendation, /healthz, WS для стрим-аудио. Валидация, auth, rate-limit" "FastAPI Router"

                sttClient = component "STT Client" "Стрим аудио во внешний STT, partial+final гипотезы, VAD-фильтр" "Async client · gRPC/WS"

                nluClassifier = component "NLU / Intent Classifier" "Классификация интентов FR-3.1..3.7 (согласие / отсрочка / отказ / за рулём / дорого / агрессия / вызов человека)" "Fine-tuned RU encoder + rules fallback"

                ragManager = component "RAG Manager" "Для интентов 'дорого' / 'отсрочка' / 'возражение' — поиск похожего возражения и подбор фразы-ответа" "Python orchestrator"

                retriever = component "Retriever" "k-NN поиск в Vector DB по embeddings реплики клиента, фильтры по интенту" "Qdrant client"

                promptFactory = component "Prompt Template Factory" "Сборка системного промпта под интент: контекст сделки {hotel,city,cost}, токен поведения (вежливо/коротко)" "Jinja2"

                llmClient = component "LLM Client" "Вызов RU-LLM для перефразирования / удержания. Таймауты, ретраи, circuit breaker" "httpx + tenacity + pybreaker"

                dialogManager = component "Dialogue Manager" "FSM сценария: что говорить дальше с учётом интента, истории, BR-01..04" "State machine (transitions lib)"

                ttsClient = component "TTS Client" "Синтез голосом 'Елена', SSML-склонение {hotel}/{city}/{cost}" "Async client · gRPC/WS"

                postprocessor = component "Response Postprocessor" "PII-маска перед логом, нормализация фразы, добавление silence/breaks, формат для VoiceGateway" "Python"

                # Внутренние связи компонентов
                controller -> sttClient "Передаёт PCM-аудио, получает гипотезы"
                sttClient -> nluClassifier "Final transcript"
                nluClassifier -> dialogManager "Интент + confidence"
                dialogManager -> ragManager "Запрос фразы (если возражение)"
                dialogManager -> promptFactory "Шаблон под интент"
                ragManager -> retriever "Похожие фразы / возражения"
                retriever -> ragManager "Top-k контекст"
                ragManager -> llmClient "Перефраз / удержание"
                promptFactory -> llmClient "Промпт с контекстом сделки"
                dialogManager -> ttsClient "Финальный текст ответа"
                llmClient -> postprocessor "Сырой ответ LLM"
                postprocessor -> ttsClient "Очищенный текст"
                ttsClient -> controller "Аудио-стрим / URI"
            }

            # ----- Связи компонентов AI Service с внешним миром / другими контейнерами -----
            sttClient -> sttProvider "Streaming recognize" "gRPC/WS"
            ttsClient -> sttProvider "Streaming synthesize" "gRPC/WS"
            llmClient -> llmProvider "Inference" "HTTPS/JSON"
            retriever -> vectorDb "k-NN search" "gRPC"
            controller -> sqlDb "Лог реплик, интент, confidence" "asyncpg"
            postprocessor -> audioStore "Заливает синтез (cache)" "S3 API"
        }

        # ---------- Связи на уровне контейнеров ----------

        # Триггер кампании (Б24 → orchestrator)
        b24 -> backend "Webhook 'Напоминание о платеже' (FR-1.1)" "HTTPS/JSON"
        backend -> ext1c "Pre-flight check статуса оплаты (BR-03)" "HTTPS/JSON"
        backend -> sqlDb "Сохраняет сделку, ставит в очередь" "asyncpg"
        backend -> scheduler "Постановка задачи на обзвон с учётом окна 10–19" "Redis queue"

        # Обзвон
        scheduler -> voiceGateway "Команда: позвонить по {phone}" "Internal HTTP"
        voiceGateway -> sipTrunk "Origination, RTP-стрим" "SIP / RTP"
        voiceGateway -> aiService "Стрим клиентского аудио" "WS / PCM"
        aiService -> voiceGateway "Стрим синтезированного аудио / команды (HANGUP, TRANSFER)" "WS / PCM"
        voiceGateway -> sipTrunk "SIP-REFER на КЦ (FR-3.7)" "SIP"

        # Постобработка
        aiService -> sqlDb "Транскрипция, интенты, Hold Time" "asyncpg"
        aiService -> audioStore "Аудиозапись звонка (TTL 30 дней)" "S3 API"
        backend -> b24 "Запись в Таймлайн (FR-4.1): транскрипт + ссылка на аудио" "HTTPS/JSON"
        backend -> smsProvider "SMS при недозвоне (FR-1.2)" "HTTPS/JSON"

        # Отчётность
        reporter -> sqlDb "Агрегаты за сутки" "asyncpg"
        reporter -> manager "Excel-отчёт в 08:00 МСК (FR-4.2)" "Email"

        # Админка
        manager -> adminUi "Просмотр сделок, прослушивание звонков"
        adminUi -> backend "REST API" "HTTPS/JSON"
        operator -> sipTrunk "Принимает переведённый звонок (SIP-REFER)"

        # AI-команда
        dataScientist -> aiService "Метрики, трейсы NLU"
        dataScientist -> vectorDb "Анализ распределения возражений"
        annotator -> adminUi "Разметка реплик (golden set)"

        # ---------- Deployment ----------
        deploymentEnvironment "Production" {
            deploymentNode "User's Device" "Браузер менеджера / аналитика" "macOS / Windows" {
                deploymentNode "Web Browser" "Chrome / Safari / Firefox" {
                    containerInstance adminUi
                }
            }

            deploymentNode "RU Cloud (Yandex Cloud)" "Yandex Managed Kubernetes — DC RU-Central" "k8s 1.29" {

                deploymentNode "Services Namespace" "Синхронные сервисы" {
                    deploymentNode "Backend Pod" "ReplicaSet ×3" { containerInstance backend }
                    deploymentNode "AI Service Pod" "ReplicaSet ×4 · GPU A100" { containerInstance aiService }
                    deploymentNode "Voice Gateway Pod" "ReplicaSet ×3 · хост-сеть для RTP" { containerInstance voiceGateway }
                }

                deploymentNode "Workers Namespace" "Фоновые задачи" {
                    deploymentNode "Scheduler Pod" "ReplicaSet ×2 · Celery beat + workers" { containerInstance scheduler }
                    deploymentNode "Reporter Pod" "CronJob 08:00 MSK" { containerInstance reporter }
                }
            }

            deploymentNode "Managed Data Infrastructure" "Управляемые сервисы YC (RU-DC)" {
                deploymentNode "Managed PostgreSQL" "YC Managed PG 15 · HA" { containerInstance sqlDb }
                deploymentNode "Managed Qdrant" "YC k8s Operator" { containerInstance vectorDb }
                deploymentNode "Object Storage" "YC S3 · TTL-rules" { containerInstance audioStore }
            }

            deploymentNode "External Systems" {
                softwareSystemInstance b24
                softwareSystemInstance ext1c
                softwareSystemInstance sipTrunk
                softwareSystemInstance smsProvider
                softwareSystemInstance llmProvider
                softwareSystemInstance sttProvider
            }
        }
    }

    views {
        systemContext sufler "ContextDiagram" {
            include *
            autoLayout lr
            title "C4 Level 1: System Context — Суфлёр БФТ"
            description "Голосовой ассистент: триггер из Б24, проверка 1С, звонок через SIP, эскалация на КЦ."
        }

        container sufler "ContainerDiagram" {
            include *
            autoLayout lr
            title "C4 Level 2: Containers — Суфлёр БФТ"
            description "Frontend (Admin UI), Backend, AI Service, Voice Gateway, Scheduler, Reporter, SQL DB (PostgreSQL), Vector DB (Qdrant), Audio Storage."
        }

        component aiService "AIService_Components_View" {
            include *
            autoLayout lr
            title "C4 Level 3: Components — AI Service (Dialog Engine)"
            description "Controller / STT / NLU / Dialogue Manager / RAG Manager + Retriever / Prompt Factory / LLM Client / TTS / Postprocessor."
        }

        deployment sufler "Production" "DeploymentDiagram" {
            include *
            autoLayout lr
            title "C4 Deployment — Суфлёр БФТ (Yandex Cloud, RU-DC)"
            description "Соответствие 152-ФЗ: все ПДн и аудиозаписи в RU-DC; LLM — self-hosted RU."
        }

        styles {
            element "Person"           { shape Person      background #08427b color #ffffff }
            element "Target System"    { background #1168bd color #ffffff }
            element "External System"  { background #999999 color #ffffff }
            element "Database"         { shape Cylinder }
            element "Web Browser"      { shape WebBrowser }
            element "Component"        { background #85bbf0 color #000000 shape Component }
            element "Internal_Technical_User"  { background #438dd5 shape Robot  color #ffffff }
            element "Internal_Operations_User" { background #08427b shape Person color #ffffff }
        }
    }
}
