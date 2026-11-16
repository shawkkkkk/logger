# FastAPI log receiver

Python starter for Railway. Receives JSON `{"log_entry": "..."}` by HTTP POST `/logs` or WebSocket `/ws`.

Set the Railway service variable `LOG_API_TOKEN` to a strong, random secret. Both endpoints require `Authorization: Bearer <token>` (including the WebSocket handshake). `GET /health` is unauthenticated for Railway health checks.

Run locally:

```bash
python -m pip install -r requirements.txt
export LOG_API_TOKEN='replace-with-a-long-random-token'
uvicorn main:app --reload
```

HTTP test:

```bash
curl -X POST http://127.0.0.1:8000/logs \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer replace-with-a-long-random-token' \
  -d '{"log_entry":"hello world"}'
```

Railway serves public HTTPS/WSS. Logs are printed to the service logs only, not stored durably. For production, configure persistent storage and rate limiting at the edge.
