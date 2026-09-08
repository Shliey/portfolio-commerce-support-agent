from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import AuthenticationError, TokenService
from .config import Settings
from .dependencies import create_chat_model
from .models import Approval, ConversationState, Logistics, Order, RequestScope, Ticket
from .rag import SemanticPolicyRetriever, production_policy_retriever
from .repository import (
    EligibilityChanged,
    IdempotencyConflict,
    LogisticsUnavailable,
    NotFound,
    OrderStatusUnavailable,
    SQLiteRepository,
)
from .runtime import CommerceRuntime, IntentRouter, ModelIntentRouter


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


class HealthResponse(BaseModel):
    status: Literal["ok"]


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]


class ErrorDetail(BaseModel):
    code: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class ThreadResponse(BaseModel):
    thread_id: str
    active_agent: str
    event_count: int


class ApprovalDecisionResponse(BaseModel):
    status: Literal["approved", "rejected"]
    ticket: Ticket | None


type ResponseDocs = dict[int | str, dict[str, Any]]

AUTH_ERRORS: ResponseDocs = {401: {"model": ErrorResponse, "description": "invalid_token"}}
ORDER_ERRORS: ResponseDocs = {
    **AUTH_ERRORS,
    404: {"model": ErrorResponse, "description": "order_not_found"},
    409: {"model": ErrorResponse, "description": "order_status_unavailable"},
    503: {"model": ErrorResponse, "description": "logistics_unavailable"},
}
APPROVAL_ERRORS: ResponseDocs = {
    **AUTH_ERRORS,
    404: {"model": ErrorResponse, "description": "approval_not_found"},
    409: {"model": ErrorResponse, "description": "idempotency_conflict"},
    422: {"model": ErrorResponse, "description": "return_not_eligible"},
}


def create_app(
    db_path: Path | str = "data/business.db",
    secret: str = "development-secret-change-me",
    *,
    checkpoint_path: Path | str | None = None,
    static_dir: Path | str | None = None,
    policy_retriever: SemanticPolicyRetriever | None = None,
    intent_router: IntentRouter | None = None,
) -> FastAPI:
    repository = SQLiteRepository(db_path)
    repository.seed()
    tokens = TokenService(secret)
    runtime = CommerceRuntime(
        repository,
        checkpoint_path,
        policy_retriever=policy_retriever,
        intent_router=intent_router,
    )
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

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post(
        "/login",
        response_model=LoginResponse,
        responses={401: {"model": ErrorResponse, "description": "invalid_credentials"}},
    )
    def login(body: LoginRequest) -> LoginResponse:
        user = repository.authenticate(body.username, body.password)
        if not user:
            raise HTTPException(status_code=401, detail={"code": "invalid_credentials"})
        return LoginResponse(access_token=tokens.issue(user.id), token_type="bearer")

    @app.get("/orders", response_model=list[Order], responses=AUTH_ERRORS)
    def orders(user_id: str = Depends(current_user)) -> list[Order]:
        return repository.list_orders(user_id)

    @app.get("/orders/{order_id}", response_model=Order, responses=ORDER_ERRORS)
    def order(order_id: str, user_id: str = Depends(current_user)) -> Order:
        try:
            return repository.get_order(user_id, order_id)
        except NotFound as error:
            raise HTTPException(status_code=404, detail={"code": "order_not_found"}) from error

    @app.get("/orders/{order_id}/logistics", response_model=Logistics, responses=ORDER_ERRORS)
    def logistics(order_id: str, user_id: str = Depends(current_user)) -> Logistics:
        try:
            return repository.get_logistics(user_id, order_id)
        except NotFound as error:
            raise HTTPException(status_code=404, detail={"code": "order_not_found"}) from error
        except OrderStatusUnavailable as error:
            raise HTTPException(
                status_code=409, detail={"code": "order_status_unavailable"}
            ) from error
        except LogisticsUnavailable as error:
            raise HTTPException(
                status_code=503, detail={"code": "logistics_unavailable"}
            ) from error

    @app.post(
        "/chat",
        response_class=StreamingResponse,
        responses={
            **AUTH_ERRORS,
            200: {
                "description": "Typed agent event stream",
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            },
        },
    )
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

    @app.get(
        "/chat/{thread_id}/events",
        response_class=StreamingResponse,
        responses={
            **AUTH_ERRORS,
            200: {
                "description": "Persisted typed agent event replay",
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            },
        },
    )
    def replay_events(thread_id: str, user_id: str = Depends(current_user)) -> StreamingResponse:
        events = runtime.sessions.list_events(user_id, thread_id)

        def replay() -> Iterator[str]:
            for item in events:
                yield f"event: {item.type}\ndata: {item.model_dump_json()}\n\n"

        return StreamingResponse(replay(), media_type="text/event-stream")

    @app.get(
        "/threads/{thread_id}",
        response_model=ThreadResponse,
        responses={
            **AUTH_ERRORS,
            404: {"model": ErrorResponse, "description": "thread_not_found"},
        },
    )
    def thread(thread_id: str, user_id: str = Depends(current_user)) -> ThreadResponse:
        active_agent = runtime.sessions.get(user_id, thread_id)
        if active_agent is None:
            raise HTTPException(status_code=404, detail={"code": "thread_not_found"})
        events = runtime.sessions.list_events(user_id, thread_id)
        return ThreadResponse(
            thread_id=thread_id, active_agent=active_agent.value, event_count=len(events)
        )

    @app.get("/approvals", response_model=list[Approval], responses=AUTH_ERRORS)
    def approvals(user_id: str = Depends(current_user)) -> list[Approval]:
        return repository.list_approvals(user_id)

    @app.post(
        "/approvals/{approval_id}/decide",
        response_model=ApprovalDecisionResponse,
        responses=APPROVAL_ERRORS,
    )
    def decide(
        approval_id: str, body: DecisionRequest, user_id: str = Depends(current_user)
    ) -> ApprovalDecisionResponse:
        try:
            result = runtime.resume_return(user_id, approval_id, body.approve)
            if result.get("status") == "ineligible":
                raise HTTPException(status_code=422, detail={"code": "return_not_eligible"})
            ticket = result.get("ticket")
            return ApprovalDecisionResponse(
                status="approved" if body.approve else "rejected",
                ticket=Ticket.model_validate(ticket) if ticket else None,
            )
        except NotFound as error:
            raise HTTPException(status_code=404, detail={"code": "approval_not_found"}) from error
        except IdempotencyConflict as error:
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error
        except EligibilityChanged as error:
            raise HTTPException(status_code=422, detail={"code": "return_not_eligible"}) from error

    app.state.repository = repository
    app.state.runtime = runtime
    app.state.tokens = tokens
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
    intent_router = ModelIntentRouter(create_chat_model(settings)) if settings.llm_api_key else None
    return create_app(
        settings.business_db,
        settings.app_secret,
        checkpoint_path=settings.checkpoint_db,
        static_dir=static_dir,
        policy_retriever=policy,
        intent_router=intent_router,
    )


app = create_app()
