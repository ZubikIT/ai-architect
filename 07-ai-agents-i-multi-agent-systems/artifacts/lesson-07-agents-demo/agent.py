import argparse

from langchain_core.messages import HumanMessage
from langgraph.graph import START, StateGraph

from utils.nodes import (
    editing_supervisor_node,
    fact_checker_node,
    github_keywords_node,
    research_supervisor_node,
    search_keywords_node,
    summarizer_node,
    supervisor_node,
    top_keywords_node,
    trending_keywords_node,
)
from utils.state import MultiAgentState
from utils.tools import get_or_create_notes_file


def build_graph():
    """Assemble the hierarchical multi-agent workflow."""
    workflow = StateGraph(MultiAgentState)

    workflow.add_node("supervisor", supervisor_node)

    workflow.add_node("research_supervisor", research_supervisor_node)
    workflow.add_node("trending_keywords_agent", trending_keywords_node)
    workflow.add_node("top_keywords_agent", top_keywords_node)
    workflow.add_node("keyword_search_agent", search_keywords_node)
    workflow.add_node("trending_github_repos_agent", github_keywords_node)

    workflow.add_node("editing_supervisor", editing_supervisor_node)
    workflow.add_node("fact_checker", fact_checker_node)
    workflow.add_node("summarizer", summarizer_node)

    workflow.add_edge(START, "supervisor")

    return workflow.compile()


graph = build_graph()


def run(prompt: str, show_progress: bool = True):
    """Run the graph for a single user prompt."""
    initial_state = {"messages": [HumanMessage(content=prompt)]}
    config = {"recursion_limit": 50}

    if not show_progress:
        return graph.invoke(initial_state, config=config)

    last_state = initial_state
    seen_message_count = len(initial_state["messages"])

    print("\n=== Workflow Progress ===\n")

    for state in graph.stream(initial_state, config=config, stream_mode="values"):
        last_state = state
        messages = state.get("messages", [])
        new_messages = messages[seen_message_count:]

        for message in new_messages:
            speaker = getattr(message, "name", None) or getattr(message, "type", "agent")
            content = str(message.content).strip().replace("\n", " ")
            preview = content[:160]
            if len(content) > 160:
                preview += "..."
            print(f"[{speaker}] {preview}")

        seen_message_count = len(messages)

    return last_state


def _extract_final_output(result) -> str:
    messages = result.get("messages", [])
    if not messages:
        return "The workflow finished without producing any messages."
    return str(messages[-1].content).strip()


def main():
    parser = argparse.ArgumentParser(
        description="Run the 7-agents hierarchical LangGraph demo."
    )
    parser.add_argument(
        "--prompt",
        help="Prompt to send to the agent graph. If omitted, you will be prompted interactively.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable step-by-step workflow progress output.",
    )
    args = parser.parse_args()

    prompt = (args.prompt or "").strip()
    if not prompt:
        prompt = input("Enter a research prompt: ").strip()

    if not prompt:
        raise SystemExit("A prompt is required to run the demo.")

    result = run(prompt, show_progress=not args.quiet)

    print("\n=== Final Output ===\n")
    print(_extract_final_output(result))
    print(f"\nNotes file: {get_or_create_notes_file()}")


if __name__ == "__main__":
    main()
