# 7-agents Demo

> _Архив-пример к уроку 07 (AI-агенты и MAS, Илья Ящук). Положен в `02-architecture/artifacts/lesson-07-agents-demo/`. README ниже — оригинальный из архива; пути в нём (`practice/7-agents/...`) даны для другой раскладки — здесь запускать **из этой папки**:_
>
> ```bash
> cd 02-architecture/artifacts/lesson-07-agents-demo
> python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> cp .env.example .env   # вписать YANDEX_API_KEY и YANDEX_FOLDER_ID
> python3 agent.py --prompt "Prepare a weekly overview of AI tools, companies, and GitHub trends"
> ```
>
> `.env` и `__pycache__/` репо игнорирует глобально (см. корневой `.gitignore`).
>
> ---

This folder contains a hierarchical multi-agent demo built with LangGraph.
It is configured to work with YandexGPT by default through Yandex AI Studio's OpenAI-compatible API.

## What it does

The workflow has two layers of supervisors:

- A main supervisor routes work between a research team and an editing team.
- The research team gathers trend data and source material.
- The editing team reviews the notes and produces a final summary.

All agents share a common notes file in `practice/7-agents/notes/`.

## Setup

Create and activate a virtual environment, then install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r practice/7-agents/requirements.txt
```

Copy the example environment file:

```bash
cp practice/7-agents/.env.example practice/7-agents/.env
```

Then open `practice/7-agents/.env` and fill in:

- `YANDEX_API_KEY`: your Yandex Cloud service account API key
- `YANDEX_FOLDER_ID`: the folder ID where that service account was created

By default, the demo uses:

- `LLM_PROVIDER=yandex`
- `YANDEX_BASE_URL=https://ai.api.cloud.yandex.net/v1`
- `YANDEX_MODEL=yandexgpt-lite`

If you want to switch back to OpenAI later, set `LLM_PROVIDER=openai` and add `OPENAI_API_KEY`.

## Run

Run the demo from the repository root:

```bash
python3 practice/7-agents/agent.py --prompt "Prepare a weekly overview of AI tools, companies, and GitHub trends"
```

You can also omit `--prompt` and enter it interactively:

```bash
python3 practice/7-agents/agent.py
```

## Output

- The final response is printed to the terminal.
- The shared research notes are saved in `practice/7-agents/notes/`.

## Notes

- The Yandex model name can be short, such as `yandexgpt-lite`. The code will convert it to a full model URI using your folder ID.
- If you want a different model, set `YANDEX_MODEL`, `SUPERVISOR_MODEL`, `WORKER_MODEL`, or `SUMMARY_MODEL`.
