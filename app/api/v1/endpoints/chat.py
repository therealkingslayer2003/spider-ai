from fastapi import APIRouter

from app.domain.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService


router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    service = ChatService()
    result = await service.chat(
        message=request.message,
        asset=request.asset,
    )

    return ChatResponse(**result)
