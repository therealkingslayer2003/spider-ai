from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder
from app.services.asset_snapshot_service import AssetSnapshotService
from app.services.chat_service import ChatService


def get_ollama_client() -> OllamaChatClient:
    return OllamaChatClient()


def get_prompt_builder() -> AssetSnapshotPromptBuilder:
    return AssetSnapshotPromptBuilder()


def get_chat_service() -> ChatService:
    return ChatService(llm_client=get_ollama_client())


def get_asset_snapshot_service() -> AssetSnapshotService:
    return AssetSnapshotService(
        llm_client=get_ollama_client(),
        prompt_builder=get_prompt_builder(),
    )
