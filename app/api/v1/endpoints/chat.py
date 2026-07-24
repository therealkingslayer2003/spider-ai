from fastapi import APIRouter, Depends

from app.api.dependencies import get_chat_service
from app.domain.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    result = await service.chat(
        message=request.message,
        asset=request.asset,
    )

    return ChatResponse(**result)
