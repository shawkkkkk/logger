import json
import logging
import os
import secrets

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

app = FastAPI(title="Log Receiver")
logger = logging.getLogger("uvicorn.error")


class LogPayload(BaseModel):
    log_entry: str = Field(max_length=65536)


def valid_token(authorization: str | None) -> bool:
    secret = os.environ.get("LOG_API_TOKEN")
    if not secret or not authorization or not authorization.startswith("Bearer "):
        return False
    return secrets.compare_digest(authorization[7:], secret)


def process_log(entry: str) -> None:
    # Replace this with durable database storage if logs must be retained.
    logger.info("[LOG] %s", entry[:50].replace("\n", " ").replace("\r", " "))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/logs")
async def receive_log(payload: LogPayload, authorization: str | None = Header(default=None)):
    if not valid_token(authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    process_log(payload.log_entry)
    return {"status": "received"}


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
            process_log(payload.log_entry)
            await websocket.send_json({"status": "received"})
    except WebSocketDisconnect:
        pass
