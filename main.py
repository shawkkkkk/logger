import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

import asyncpg
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

logger = logging.getLogger("uvicorn.error")


class LogPayload(BaseModel):
    log_entry: str = Field(max_length=65536)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for persistent log storage")

    # PostgreSQL may still be starting when Railway launches this service.
    for attempt in range(15):
        try:
            app.state.pool = await asyncpg.create_pool(
                dsn=database_url, min_size=1, max_size=5, command_timeout=15
            )
            break
        except (OSError, asyncpg.PostgresError):
            if attempt == 14:
                raise
            await asyncio.sleep(2)

    async with app.state.pool.acquire() as connection:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS log_entries (
                id BIGSERIAL PRIMARY KEY,
                log_entry TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    try:
        yield
    finally:
        await app.state.pool.close()


app = FastAPI(title="Log Receiver", lifespan=lifespan)


def valid_token(authorization: str | None) -> bool:
    secret = os.environ.get("LOG_API_TOKEN")
    if not secret or not authorization or not authorization.startswith("Bearer "):
        return False
    return secrets.compare_digest(authorization[7:], secret)


async def save_log(entry: str) -> int:
    async with app.state.pool.acquire() as connection:
        return await connection.fetchval(
            "INSERT INTO log_entries (log_entry) VALUES ($1) RETURNING id", entry
        )


@app.get("/health")
async def health():
    await app.state.pool.fetchval("SELECT 1")
    return {"status": "ok"}


@app.post("/logs")
async def receive_log(payload: LogPayload, authorization: str | None = Header(default=None)):
    if not valid_token(authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    try:
        log_id = await save_log(payload.log_entry)
    except (OSError, asyncpg.PostgresError):
        logger.exception("Failed to store log entry")
        raise HTTPException(status_code=503, detail="Log storage unavailable")
    return {"status": "received", "id": log_id}


@app.get("/logs/{log_id}")
async def get_log(log_id: int, authorization: str | None = Header(default=None)):
    if not valid_token(authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    async with app.state.pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT id, log_entry, created_at FROM log_entries WHERE id = $1", log_id
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"id": row["id"], "log_entry": row["log_entry"], "created_at": row["created_at"]}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not valid_token(websocket.headers.get("authorization")):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                payload = LogPayload.model_validate(data)
            except (ValueError, TypeError):
                await websocket.send_json({"status": "error", "detail": "Invalid log payload"})
                continue
            try:
                log_id = await save_log(payload.log_entry)
            except (OSError, asyncpg.PostgresError):
                logger.exception("Failed to store WebSocket log entry")
                await websocket.send_json({"status": "error", "detail": "Log storage unavailable"})
                continue
            await websocket.send_json({"status": "received", "id": log_id})
    except WebSocketDisconnect:
        pass
