FROM python:3.12-slim

WORKDIR /app/servers

# Install dependencies directly
RUN pip install --no-cache-dir "mcp[cli]" "pyjwt[crypto]" httpx structlog pydantic

# Copy shared modules and server source
COPY shared/ shared/
COPY bloomberg/ bloomberg/

ENV PYTHONPATH=/app/servers
EXPOSE 8010

CMD ["python", "-m", "bloomberg.server"]
