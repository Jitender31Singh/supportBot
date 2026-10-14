import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trackobit_assistant.config.settings import get_settings
from trackobit_assistant.adapters.session_store_json import JsonSessionStore
from trackobit_assistant.adapters.vehicle_api import HttpVehicleApiClient
from trackobit_assistant.adapters.ticket_client import LoggingTicketClient
from trackobit_assistant.adapters.command_registry import YamlCommandRegistry
from trackobit_assistant.adapters.knowledge_base import FileKnowledgeBase
from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.graph.builder import build_graph
from trackobit_assistant.llm.factory import create_chat_model
from trackobit_assistant.services.prompt_repository import PromptRepository


def main() -> None:
    settings = get_settings()
    runtime = Runtime(
        settings=settings,
        session_store=JsonSessionStore(settings.session_dir),
        vehicle_client=HttpVehicleApiClient(settings),
        ticket_client=LoggingTicketClient(),
        command_registry=YamlCommandRegistry(settings.commands_dir),
        knowledge_base=FileKnowledgeBase(settings.knowledge_dir),
        llm=create_chat_model(settings),
        vision_llm=create_chat_model(settings, vision=True),
        prompts=PromptRepository(ROOT / "prompts"),
    )

    # Graph compilation must succeed before exporting either file.
    compiled_graph = build_graph(runtime)
    mermaid_source = compiled_graph.get_graph().draw_mermaid()

    docs_dir = ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = docs_dir / "graph.md"
    mermaid_path = docs_dir / "graph.mmd"

    markdown_content = (
        "# Compiled TrackoBit Support Graph\n\n"
        "```mermaid\n"
        f"{mermaid_source.rstrip()}\n"
        "```\n"
    )

    markdown_path.write_text(markdown_content, encoding="utf-8")
    mermaid_path.write_text(mermaid_source.rstrip() + "\n", encoding="utf-8")

    print(f"Markdown written to: {markdown_path}")
    print(f"Mermaid source written to: {mermaid_path}")
    print(f"Mermaid source length: {len(mermaid_source)} characters")
    print("To create a PDF (with Node.js installed), run:")
    print("npx -y @mermaid-js/mermaid-cli -i docs/graph.mmd -o docs/graph.pdf")


if __name__ == "__main__":
    main()
