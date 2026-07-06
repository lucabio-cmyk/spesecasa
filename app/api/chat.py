from fastapi import APIRouter

from app.config import settings
from app.deps import DB, CurrentUser
from app.enums import UserRole
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import ratelimit

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest, user: CurrentUser, db: DB):
    # Ogni messaggio può innescare più chiamate a Claude (loop di tool) e la
    # ricerca web: limita per utente per contenere abusi e costi.
    await ratelimit.enforce(
        f"chat:{user.id}", settings.rate_limit_chat, settings.rate_limit_chat_window
    )
    from app.agent.runner import chat as agent_chat

    answer = await agent_chat(
        db,
        user.household_id,
        user.id,
        [m.model_dump() for m in body.history],
        body.message,
        is_admin=user.role == UserRole.ADMIN,
    )
    return ChatResponse(answer=answer)
