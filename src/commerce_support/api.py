from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import AuthenticationError, TokenService
from .config import Settings
from .models import ConversationState, RequestScope
from .rag import SemanticPolicyRetriever, production_policy_retriever
from .repository import IdempotencyConflict, NotFound, SQLiteRepository
from .runtime import CommerceRuntime


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    thread_id: str
    request_id: str
    message: str
    order_id: str | None = None
    reason: str | None = None


class DecisionRequest(BaseModel):
    approve: bool


def create_app(
    db_path: Path | str = "data/business.db",
    secret: str = "development-secret-change-me",
    *,
    checkpoint_path: Path | str | None = None,
    static_dir: Path | str | None = None,
    policy_retriever: SemanticPolicyRetriever | None = None,
) -> FastAPI:
    repository = SQLiteRepository(db_path)
    repository.seed()
    tokens = TokenService(secret)
    runtime = CommerceRuntime(repository, checkpoint_path, policy_retriever=policy_retriever)
    app = FastAPI(title="Recoverable Commerce Support Agent", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def current_user(authorization: Annotated[str | None, Header()] = None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail={"code": "invalid_token"})
        try:
            return tokens.verify(authorization.removeprefix("Bearer "))
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail={"code": "invalid_token"}) from error

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/login")
    def login(body: LoginRequest) -> dict[str, str]:
        user = repository.authenticate(body.username, body.password)
        if not user:
            raise HTTPException(status_code=401, detail={"code": "invalid_credentials"})
        return {"access_token": tokens.issue(user.id), "token_type": "bearer"}

    @app.get("/orders")
    def orders(user_id: str = Depends(current_user)) -> list[dict[str, object]]:
        return [order.model_dump(mode="json") for order in repository.list_orders(user_id)]

    @app.get("/orders/{order_id}")
    def order(order_id: str, user_id: str = Depends(current_user)) -> dict[str, object]:
        try:
            return repository.get_order(user_id, order_id).model_dump(mode="json")
        except NotFound as error:
            raise HTTPException(status_code=404, detail={"code": "order_not_found"}) from error

    @app.get("/orders/{order_id}/logistics")
    def logistics(order_id: str, user_id: str = Depends(current_user)) -> dict[str, object]:
        try:
            return repository.get_logistics(user_id, order_id).model_dump(mode="json")
        except NotFound as error:
            raise HTTPException(status_code=404, detail={"code": "order_not_found"}) from error

    @app.post("/chat")
    def chat(body: ChatRequest, user_id: str = Depends(current_user)) -> StreamingResponse:
        state = ConversationState(
            scope=RequestScope(
                user_id=user_id, thread_id=body.thread_id, request_id=body.request_id
            ),
            message=body.message,
            order_id=body.order_id,
            reason=body.reason,
        )

        def safe_stream() -> Iterator[str]:
            yield from runtime.sse(state)

        return StreamingResponse(safe_stream(), media_type="text/event-stream")

    @app.get("/chat/{thread_id}/events")
    def replay_events(thread_id: str, user_id: str = Depends(current_user)) -> StreamingResponse:
        events = runtime.sessions.list_events(user_id, thread_id)

        def replay() -> Iterator[str]:
            for item in events:
                yield f"event: {item.type}\ndata: {item.model_dump_json()}\n\n"

        return StreamingResponse(replay(), media_type="text/event-stream")

    @app.get("/threads/{thread_id}")
    def thread(thread_id: str, user_id: str = Depends(current_user)) -> dict[str, object]:
        active_agent = runtime.sessions.get(user_id, thread_id)
        if active_agent is None:
            raise HTTPException(status_code=404, detail={"code": "thread_not_found"})
        events = runtime.sessions.list_events(user_id, thread_id)
        return {
            "thread_id": thread_id,
            "active_agent": active_agent.value,
            "event_count": len(events),
        }

    @app.get("/approvals")
    def approvals(user_id: str = Depends(current_user)) -> list[dict[str, object]]:
        return [approval.model_dump(mode="json") for approval in repository.list_approvals(user_id)]

    @app.post("/approvals/{approval_id}/decide")
    def decide(
        approval_id: str, body: DecisionRequest, user_id: str = Depends(current_user)
    ) -> dict[str, object]:
        try:
            result = runtime.resume_return(user_id, approval_id, body.approve)
            ticket = result.get("ticket")
            return {
                "status": "approved" if body.approve else "rejected",
                "ticket": ticket,
            }
        except NotFound as error:
            raise HTTPException(status_code=404, detail={"code": "approval_not_found"}) from error
        except IdempotencyConflict as error:
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error

    app.state.repository = repository
    app.state.runtime = runtime
    if static_dir is not None:
        resolved_static_dir = Path(static_dir)
        if not resolved_static_dir.is_dir():
            raise ValueError(f"static directory does not exist: {resolved_static_dir}")
        app.mount("/", StaticFiles(directory=resolved_static_dir, html=True), name="web")
    return app


def create_app_from_env() -> FastAPI:
    settings = Settings.from_env()
    static_dir = os.getenv("WEB_DIST")
    policy = production_policy_retriever(settings.llm_embedding_model)
    return create_app(
        settings.business_db,
        settings.app_secret,
        checkpoint_path=settings.checkpoint_db,
        static_dir=static_dir,
        policy_retriever=policy,
    )


app = create_app()
