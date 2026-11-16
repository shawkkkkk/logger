# FastAPI log receiver

Python starter for Railway, with persistent PostgreSQL storage.

## Endpoints

- `POST /logs` accepts JSON `{"log_entry": "..."}`, inserts it into PostgreSQL, and returns `{"status":"received","id":123}`.
- `WS /ws` accepts the same JSON and acknowledges after saving.
- `GET /logs/{id}` retrieves one saved entry.
- `GET /health` checks the database connection.

All endpoints except `/health` require `Authorization: Bearer <token>`. For WebSockets, set that header during the handshake.

## Railway setup

Add a PostgreSQL service in the same Railway project. Set the logger service variables:

- `DATABASE_URL=${{Postgres.DATABASE_URL}}` (Railway private-network reference)
- `LOG_API_TOKEN` to a strong secret

The logger creates the `log_entries` table on startup. Entries stay in PostgreSQL across app restarts and redeploys, subject to database volume retention, backups, and Railway account lifecycle. Configure regular database backups for protection against deletion or database failure.

## Local setup

```bash
python -m pip install -r requirements.txt
export DATABASE_URL='postgresql://user:password@localhost:5432/railway'
export LOG_API_TOKEN='replace-with-a-long-random-token'
uvicorn main:app --reload
```

Send a log:

```bash
curl -X POST http://127.0.0.1:8000/logs \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer replace-with-a-long-random-token' \
  -d '{"log_entry":"hello world"}'
```

Use the returned ID to read it back from `GET /logs/{id}` with the same authorization header.

Logs have a 65,536-character maximum per entry. The service intentionally does not echo log contents to stdout. Add network-level rate limits and an explicit retention policy if volume grows.
