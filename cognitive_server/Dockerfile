FROM python:3.12-slim

WORKDIR /app

# Install dependencies directly
RUN pip install --no-cache-dir "mcp[cli]" "pyjwt[crypto]" httpx structlog pydantic asyncpg "sqlalchemy[asyncio]" numpy fastapi "uvicorn[standard]"

COPY cognitive_server/ cognitive_server/
COPY cognitive_server/db/ cognitive_server/db/

ENV PYTHONPATH=/app
EXPOSE 8013

CMD ["python", "-m", "cognitive_server.server"]
