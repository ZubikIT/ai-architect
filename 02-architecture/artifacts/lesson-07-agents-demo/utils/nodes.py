import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import convert_to_messages
from langchain_openai import ChatOpenAI
from langgraph.graph import END
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from utils.state import MultiAgentState
from utils.tools import (
    get_or_create_notes_file,
    keyword_source_search_tool,
    read_notes,
    top_keywords_sources_tool,
    trending_keywords_sources_tool,
    write_notes,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

today = datetime.now().strftime("%Y-%m-%d")
logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv(
    "LLM_PROVIDER",
    "yandex" if os.getenv("YANDEX_API_KEY") else "openai",
).strip().lower()
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))


def _yandex_model_uri(model_name: str, folder_id: str) -> str:
    if model_name.startswith("gpt://"):
        return model_name

    normalized = model_name.strip("/")
    if "/" not in normalized:
        normalized = f"{normalized}/latest"

    return f"gpt://{folder_id}/{normalized}"


def _build_llm(role_env_var: str, default_model_name: str) -> ChatOpenAI:
    if LLM_PROVIDER == "yandex":
        api_key = os.getenv("YANDEX_API_KEY")
        folder_id = os.getenv("YANDEX_FOLDER_ID")
        base_url = os.getenv("YANDEX_BASE_URL", "https://ai.api.cloud.yandex.net/v1")
        model_name = os.getenv(role_env_var, os.getenv("YANDEX_MODEL", default_model_name))

        if not api_key:
            raise RuntimeError(
                "YANDEX_API_KEY is required when LLM_PROVIDER=yandex."
            )
        if not folder_id:
            raise RuntimeError(
                "YANDEX_FOLDER_ID is required when LLM_PROVIDER=yandex."
            )

        return ChatOpenAI(
            model=_yandex_model_uri(model_name, folder_id),
            api_key=api_key,
            base_url=base_url,
            default_headers={"OpenAI-Project": folder_id},
            temperature=0,
            request_timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required when LLM_PROVIDER=openai."
        )

    return ChatOpenAI(
        model=os.getenv(role_env_var, os.getenv("OPENAI_MODEL", default_model_name)),
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0,
        request_timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


llm = _build_llm("SUPERVISOR_MODEL", "gpt-4o-mini")
llm_big = _build_llm("WORKER_MODEL", "gpt-4o-mini")
llm_even_bigger = _build_llm("SUMMARY_MODEL", "gpt-4o-mini")


def _announce_node(node_name: str) -> None:
    print(f"[node] {node_name}", flush=True)


def make_top_level_supervisor_node(
    members: list[str], system_prompt: str
):
    def supervisor(state: MultiAgentState) -> Command:
        _announce_node("supervisor")
        user_request = _get_original_user_request(state)

        if not _team_completed(state, "RESEARCH"):
            instruction = _build_research_instruction(user_request)
            return Command(
                goto="research_supervisor",
                update={
                    "next": "research_supervisor",
                    "messages": state["messages"]
                    + [
                        HumanMessage(
                            content=f"[INSTRUCTION FROM MAIN SUPERVISOR]\n{instruction}",
                            name="supervisor",
                        )
                    ],
                },
            )

        if not _notes_section_exists("Final Summary"):
            instruction = _build_editing_instruction(user_request)
            return Command(
                goto="editing_supervisor",
                update={
                    "next": "editing_supervisor",
                    "messages": state["messages"]
                    + [
                        HumanMessage(
                            content=f"[INSTRUCTION FROM MAIN SUPERVISOR]\n{instruction}",
                            name="supervisor",
                        )
                    ],
                },
            )

        if _notes_section_exists("Final Summary"):
            final_summary = extract_final_summary()
            final_message = (
                "Research and editing are complete.\n\n"
                f"# FINAL RESEARCH SUMMARY\n\n{final_summary}"
            )
            return Command(
                goto=END,
                update={
                    "next": END,
                    "messages": state["messages"]
                    + [AIMessage(content=final_message, name="supervisor")],
                },
            )

        return Command(goto=END, update={"next": END, "messages": state["messages"]})

    return supervisor


def make_team_supervisor_node(
    members: list[str], parent: str, system_prompt: str, team: str
):
    options = ["FINISH"] + members

    class Router(TypedDict):
        next: str
        instruction: str

    def supervisor(state: MultiAgentState) -> Command:
        _announce_node(f"{team.lower()}_supervisor")
        messages = prepare_supervisor_messages(system_prompt, state["messages"])
        response = llm.with_structured_output(
            Router, method="function_calling"
        ).invoke(messages)
        goto = response["next"]
        instruction = response.get(
            "instruction", "Please perform your task clearly without questions."
        )

        if goto not in options:
            logger.warning(
                "Unexpected %s-team route '%s'. Falling back to FINISH.",
                team,
                goto,
            )
            goto = "FINISH"

        if goto == "FINISH":
            return Command(
                goto=parent,
                update={
                    "next": parent,
                    "messages": state["messages"]
                    + [
                        AIMessage(
                            content=(
                                f"{team} team complete. Supervisor summary: {instruction}"
                            ),
                            name=f"{team.lower()}_supervisor",
                        )
                    ],
                },
            )

        return Command(
            goto=goto,
            update={
                "next": goto,
                "messages": state["messages"]
                + [
                    HumanMessage(
                        content=f"[INSTRUCTION FROM {team} TEAM SUPERVISOR]\n{instruction}",
                        name="supervisor",
                    )
                ],
            },
        )

    return supervisor


trending_keywords_prompt_template = """You are an agent that fetches trending keywords for tech social media platforms.

You can choose from these categories: companies, ai, tools, platforms, hardware, people, frameworks, languages, concepts, websites, subjects.
You can choose from these periods: daily, weekly, monthly, quarterly.

Required workflow:
1. Use trending_keywords_sources_tool exactly once.
2. Save the findings with write_notes under the section "Trending Keywords Analysis".
3. After saving the findings, reply with a short completion message.

Important rules:
- Never call trending_keywords_sources_tool twice in the same task.
- Do not ask follow-up questions.
- Save the research to the shared notes document before you finish.
"""

trending_keywords_agent = create_react_agent(
    llm_big,
    tools=[trending_keywords_sources_tool, write_notes],
    prompt=trending_keywords_prompt_template,
)


def trending_keywords_node(state: MultiAgentState) -> Command:
    _announce_node("trending_keywords_agent")
    filtered_state = optimize_agent_state(state)
    result = trending_keywords_agent.invoke(filtered_state)
    agent_messages = [msg for msg in result["messages"] if str(msg.content).strip()]
    agent_content = agent_messages[-1].content if agent_messages else "No valid results."

    return Command(
        update={
            "messages": state["messages"]
            + [
                AIMessage(
                    content=f"[COMPLETED trending_keywords_agent]\n{agent_content}",
                    name="trending_keywords_agent",
                )
            ]
        },
        goto="research_supervisor",
    )


top_keywords_prompt_template = """You are an agent that fetches the most-mentioned tech keywords across social media sources.

You can choose from these categories: companies, ai, tools, platforms, hardware, people, frameworks, languages, concepts, websites, subjects.
You can choose from these periods: daily, weekly, monthly, quarterly.

Required workflow:
1. Use top_keywords_sources_tool exactly once.
2. Save the findings with write_notes under the section "Top Keywords Analysis".
3. After saving the findings, reply with a short completion message.

Important rules:
- Never call top_keywords_sources_tool twice in the same task.
- Do not ask follow-up questions.
- Save the research to the shared notes document before you finish.
"""

top_keywords_agent = create_react_agent(
    llm_big,
    tools=[top_keywords_sources_tool, write_notes],
    prompt=top_keywords_prompt_template,
)


def top_keywords_node(state: MultiAgentState) -> Command:
    _announce_node("top_keywords_agent")
    filtered_state = optimize_agent_state(state)
    result = top_keywords_agent.invoke(filtered_state)
    agent_messages = [msg for msg in result["messages"] if str(msg.content).strip()]
    agent_content = agent_messages[-1].content if agent_messages else "No valid results."

    return Command(
        update={
            "messages": state["messages"]
            + [
                AIMessage(
                    content=f"[COMPLETED top_keywords_agent]\n{agent_content}",
                    name="top_keywords_agent",
                )
            ]
        },
        goto="research_supervisor",
    )


search_keywords_prompt_template = """You are an agent for searching specific technology keywords in social media sources.

You can choose from these periods: daily, weekly, monthly, quarterly.
You can choose from these sources: reddit, hackernews, github, medium.

Required workflow:
1. Use keyword_source_search_tool exactly once for the requested keywords.
2. Save the findings with write_notes under the section "Specific Keyword Search Results".
3. After saving the findings, reply with a short completion message.

Important rules:
- Never call keyword_source_search_tool twice in the same task.
- Do not ask follow-up questions.
- Save the research to the shared notes document before you finish.
"""

search_keywords_agent = create_react_agent(
    llm_big,
    tools=[keyword_source_search_tool, write_notes],
    prompt=search_keywords_prompt_template,
)


def search_keywords_node(state: MultiAgentState) -> Command:
    _announce_node("keyword_search_agent")
    filtered_state = optimize_agent_state(state)
    result = search_keywords_agent.invoke(filtered_state)
    agent_messages = [msg for msg in result["messages"] if str(msg.content).strip()]
    agent_content = agent_messages[-1].content if agent_messages else "No valid results."

    return Command(
        update={
            "messages": state["messages"]
            + [
                AIMessage(
                    content=f"[COMPLETED keyword_search_agent]\n{agent_content}",
                    name="keyword_search_agent",
                )
            ]
        },
        goto="research_supervisor",
    )


github_trending_repos_prompt_template = """You are an agent that searches GitHub discussions and repositories for requested keywords.

Use only these periods: weekly, monthly, quarterly.

Required workflow:
1. Use keyword_source_search_tool exactly once with source="github".
2. Save the findings with write_notes under the section "Trending GitHub Repositories for Keywords".
3. After saving the findings, reply with a short completion message.

Important rules:
- Never call keyword_source_search_tool twice in the same task.
- Always specify source="github".
- Save the research to the shared notes document before you finish.
"""

trending_github_repos_agent = create_react_agent(
    llm_big,
    tools=[keyword_source_search_tool, write_notes],
    prompt=github_trending_repos_prompt_template,
)


def github_keywords_node(state: MultiAgentState) -> Command:
    _announce_node("trending_github_repos_agent")
    filtered_state = optimize_agent_state(state)
    result = trending_github_repos_agent.invoke(filtered_state)
    agent_messages = [msg for msg in result["messages"] if str(msg.content).strip()]
    agent_content = agent_messages[-1].content if agent_messages else "No valid results."

    return Command(
        update={
            "messages": state["messages"]
            + [
                AIMessage(
                    content=f"[COMPLETED trending_github_repos_agent]\n{agent_content}",
                    name="trending_github_repos_agent",
                )
            ]
        },
        goto="research_supervisor",
    )


RESEARCH_SUPERVISOR_PROMPT = f"""You are a supervisor coordinating these research agents within the technology social-media space:

- trending_keywords_agent: Finds trending keywords by category and period.
- top_keywords_agent: Finds the most-mentioned keywords by category and period.
- keyword_search_agent: Tracks specific keywords and what people are saying about them.
- trending_github_repos_agent: Searches GitHub activity for requested keywords.

Strategy:
1. Start with trending_keywords_agent or top_keywords_agent.
2. Use keyword_search_agent when the user mentions specific keywords to track.
3. Use trending_github_repos_agent when GitHub projects or repository activity are relevant.
4. Use at least two different research agents before finishing.

Available categories: companies, ai, tools, platforms, hardware, people, frameworks, languages, concepts, websites, subjects.
Available periods: daily, weekly, monthly, quarterly.
Available sources: reddit, hackernews, github, medium.

Rules:
- Never ask trending_keywords_agent or top_keywords_agent to repeat the same task.
- When an agent already completed a task, move to a different agent or finish.
- Always give explicit instructions with categories, periods, keywords, and source constraints when needed.

Return strictly:
- "next": an agent name or FINISH
- "instruction": a clear next instruction

Today's date: {today}.
"""

research_supervisor_node = make_team_supervisor_node(
    members=[
        "trending_keywords_agent",
        "top_keywords_agent",
        "keyword_search_agent",
        "trending_github_repos_agent",
    ],
    parent="supervisor",
    system_prompt=RESEARCH_SUPERVISOR_PROMPT,
    team="RESEARCH",
)


fact_checker_prompt_template = """You are a diligent fact checker reviewing a shared technology research document.

Your tools:
1. read_notes
2. write_notes

Required workflow:
1. Use read_notes first.
2. Write a short assessment of the research quality under the section "Fact Check Report".
3. Keep the assessment to 1-2 short paragraphs and focus on overall reliability, not line-by-line verification.
4. Return the same short assessment to the supervisor.
"""

fact_checker_agent = create_react_agent(
    llm_big,
    tools=[read_notes, write_notes],
    prompt=fact_checker_prompt_template,
)


def fact_checker_node(state: MultiAgentState) -> Command:
    _announce_node("fact_checker")
    filtered_state = optimize_agent_state(state)
    result = fact_checker_agent.invoke(filtered_state)
    agent_messages = [msg for msg in result["messages"] if str(msg.content).strip()]
    agent_content = agent_messages[-1].content if agent_messages else "No valid results."

    if agent_content and not _notes_section_exists("Fact Check Report"):
        write_notes.invoke(
            {"content": str(agent_content), "section": "Fact Check Report"}
        )

    return Command(
        update={
            "messages": state["messages"]
            + [
                AIMessage(
                    content=f"[COMPLETED fact_checker]\n{agent_content}",
                    name="fact_checker",
                )
            ]
        },
        goto="editing_supervisor",
    )


summarizer_prompt_template = """You are an expert content summarizer creating the final technology research report.

Your tools:
1. read_notes
2. write_notes

Required workflow:
1. Use read_notes first and review the complete document.
2. Create a focused summary with:
   - Key Happenings
   - Why It Matters
   - Notable Conversations
   - Interesting Tidbits
   - Sources
3. Save the final report under the section "Final Summary".
4. Keep the report concise, specific, and useful for a student demo.
5. Return the same summary to the supervisor.
"""

summarizer_agent = create_react_agent(
    llm_even_bigger,
    tools=[read_notes, write_notes],
    prompt=summarizer_prompt_template,
)


def summarizer_node(state: MultiAgentState) -> Command:
    _announce_node("summarizer")
    result = summarizer_agent.invoke(state)
    agent_messages = [msg for msg in result["messages"] if str(msg.content).strip()]
    agent_content = agent_messages[-1].content if agent_messages else "No valid results."

    if agent_content and not _notes_section_exists("Final Summary"):
        write_notes.invoke(
            {"content": str(agent_content), "section": "Final Summary"}
        )

    return Command(
        update={
            "messages": state["messages"]
            + [
                AIMessage(
                    content=f"[COMPLETED summarizer]\n{agent_content}",
                    name="summarizer",
                )
            ]
        },
        goto="editing_supervisor",
    )


EDITING_SUPERVISOR_PROMPT = """You are the editing team supervisor managing these workers:
- fact_checker
- summarizer

Workflow:
1. First use fact_checker.
2. Then use summarizer to create the final polished report.
3. Finish only after the final report is complete.

Always return:
- "next": the next worker or FINISH
- "instruction": a complete, explicit instruction
"""

def editing_supervisor_node(state: MultiAgentState) -> Command:
    _announce_node("editing_supervisor")

    if not _agent_completed(state, "fact_checker"):
        instruction = (
            "Read the shared research notes, assess the overall quality of the research, "
            "and save the assessment under 'Fact Check Report'."
        )
        return Command(
            goto="fact_checker",
            update={
                "next": "fact_checker",
                "messages": state["messages"]
                + [
                    HumanMessage(
                        content=(
                            "[INSTRUCTION FROM EDITING TEAM SUPERVISOR]\n"
                            f"{instruction}"
                        ),
                        name="supervisor",
                    )
                ],
            },
        )

    if not _notes_section_exists("Final Summary"):
        instruction = (
            "Read the full shared notes document, create the final concise report, "
            "save it under 'Final Summary', and return the same summary."
        )
        return Command(
            goto="summarizer",
            update={
                "next": "summarizer",
                "messages": state["messages"]
                + [
                    HumanMessage(
                        content=(
                            "[INSTRUCTION FROM EDITING TEAM SUPERVISOR]\n"
                            f"{instruction}"
                        ),
                        name="supervisor",
                    )
                ],
            },
        )

    return Command(
        goto="supervisor",
        update={
            "next": "supervisor",
            "messages": state["messages"]
            + [
                AIMessage(
                    content=(
                        "EDITING team complete. Supervisor summary: "
                        "The final summary has been written to the shared notes document."
                    ),
                    name="editing_supervisor",
                )
            ],
        },
    )


MAIN_SUPERVISOR_PROMPT = """You are the main supervisor coordinating two teams:
- research_supervisor
- editing_supervisor

Workflow:
1. Always start with research_supervisor.
2. Once research is complete, hand off to editing_supervisor.
3. Finish only after the final edited report is available.

Always return:
- "next": the next team or FINISH
- "instruction": a clear instruction for that team
"""

supervisor_node = make_top_level_supervisor_node(
    ["research_supervisor", "editing_supervisor"],
    MAIN_SUPERVISOR_PROMPT,
)


def prepare_supervisor_messages(
    system_prompt: str, state_messages: List[Any]
) -> List[BaseMessage]:
    """Normalize state messages so the supervisor model receives only plain text."""
    history = convert_to_messages(state_messages or [])
    normalized_history: List[BaseMessage] = []

    for message in history:
        content_text = _coerce_message_content_to_text(message.content)
        if not content_text:
            continue
        normalized_history.append(message.model_copy(update={"content": content_text}))

    if not normalized_history:
        logger.warning(
            "Supervisor invoked without usable messages; injecting placeholder instruction."
        )
        normalized_history.append(
            HumanMessage(
                content=(
                    "No user context was available. Provide a concise plan for how the "
                    "teams should gather and summarize the latest technology signals."
                ),
                name="system-fallback",
            )
        )

    return [SystemMessage(content=system_prompt), *normalized_history]


def _coerce_message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: List[str] = []
        for part in content:
            if isinstance(part, str):
                chunks.append(part)
                continue
            if isinstance(part, dict):
                text_value = None
                for key in ("text", "input_text", "output_text", "content"):
                    value = part.get(key)
                    if isinstance(value, str) and value.strip():
                        text_value = value
                        break
                if text_value:
                    chunks.append(text_value)
                elif part.get("type") == "image_url" and part.get("image_url"):
                    chunks.append(f"[image:{part['image_url']}]")
                else:
                    chunks.append(json.dumps(part))
                continue
            chunks.append(str(part))
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    if content is None:
        return ""
    return str(content).strip()


def extract_final_summary(notes_file=None):
    try:
        if notes_file is None:
            notes_file = get_or_create_notes_file()

        with open(notes_file, "r", encoding="utf-8") as file:
            content = file.read()

        lines = content.split("\n")
        final_summary = []
        in_final_summary = False
        final_summary_level = 0

        for line in lines:
            if not in_final_summary and any(
                header in line.lower()
                for header in ["# final summary", "## final summary", "final summary"]
            ):
                in_final_summary = True
                final_summary_level = line.count("#") if "#" in line else 2
                final_summary.append("# Tech Research Summary\n")
                continue

            if in_final_summary and line.strip().startswith("#"):
                current_level = line.count("#")
                if (
                    current_level <= final_summary_level
                    and "final summary" not in line.lower()
                ):
                    in_final_summary = False
                    continue

            if in_final_summary:
                final_summary.append(line)

        formatted_summary = "\n".join(final_summary)
        if not formatted_summary.strip():
            return (
                "No final summary found. Please check whether the summarizer agent "
                "successfully wrote a 'Final Summary' section."
            )

        return formatted_summary
    except Exception as exc:
        return f"Error retrieving final summary: {exc}"


def optimize_agent_state(state: MultiAgentState):
    """Keep only the original user request and the latest supervisor instruction."""
    original_message = state["messages"][0] if state["messages"] else None
    supervisor_messages = [
        msg
        for msg in state["messages"]
        if msg.type == "human" and "SUPERVISOR" in str(msg.content)
    ]
    latest_supervisor = supervisor_messages[-1] if supervisor_messages else None

    filtered_messages = []
    if original_message:
        filtered_messages.append(original_message)
    if latest_supervisor:
        filtered_messages.append(latest_supervisor)

    return {"messages": filtered_messages}


def _get_original_user_request(state: MultiAgentState) -> str:
    if not state.get("messages"):
        return "Prepare a technology research report."
    return _coerce_message_content_to_text(state["messages"][0].content)


def _build_research_instruction(user_request: str) -> str:
    return (
        "Gather research for the user's request using the research team.\n\n"
        f"User request: {user_request}\n\n"
        "Use at least two different research agents. Cover AI tools, companies, and "
        "GitHub trends when relevant. Save all findings to the shared notes document."
    )


def _build_editing_instruction(user_request: str) -> str:
    return (
        "Use the shared research notes to produce the final deliverable.\n\n"
        f"User request: {user_request}\n\n"
        "First run the fact checker, then run the summarizer, and ensure the final "
        "summary is written under the 'Final Summary' section."
    )


def _agent_completed(state: MultiAgentState, agent_name: str) -> bool:
    completion_marker = f"[COMPLETED {agent_name}]"
    for message in state.get("messages", []):
        if getattr(message, "name", "") == agent_name and completion_marker in str(
            message.content
        ):
            return True
    return False


def _team_completed(state: MultiAgentState, team_name: str) -> bool:
    team_marker = f"{team_name.upper()} team complete."
    supervisor_name = f"{team_name.lower()}_supervisor"
    for message in state.get("messages", []):
        if getattr(message, "name", "") != supervisor_name:
            continue
        if team_marker in str(message.content):
            return True
    return False


def _notes_section_exists(section_name: str) -> bool:
    notes_file = get_or_create_notes_file()
    try:
        with open(notes_file, "r", encoding="utf-8") as file:
            content = file.read().lower()
    except OSError:
        return False

    normalized = section_name.strip().lower()
    return f"## {normalized}" in content or f"# {normalized}" in content
