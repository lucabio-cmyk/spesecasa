from fastapi import APIRouter

from app.deps import DB, CurrentUser
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest, user: CurrentUser, db: DB):
    from app.agent.runner import chat as agent_chat

    answer = await agent_chat(
        db,
        user.household_id,
        user.id,
        [m.model_dump() for m in body.history],
        body.message,
    )
    return ChatResponse(answer=answer)
