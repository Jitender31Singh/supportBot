from dataclasses import dataclass
from typing import Any
from trackobit_assistant.config.settings import Settings
from trackobit_assistant.ports.interfaces import SessionStore, VehicleApiClient, TicketClient, CommandRegistry, KnowledgeBase
from trackobit_assistant.services.prompt_repository import PromptRepository
from trackobit_assistant.formatters.message_renderer import MessageRenderer

@dataclass
class Runtime:
    settings: Settings
    session_store: SessionStore
    vehicle_client: VehicleApiClient
    ticket_client: TicketClient
    command_registry: CommandRegistry
    knowledge_base: KnowledgeBase
    llm: Any = None
    vision_llm: Any = None
    prompts: PromptRepository | None = None
    messages: MessageRenderer | None = None
