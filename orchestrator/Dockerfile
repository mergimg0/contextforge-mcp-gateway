FROM python:3.12-slim

WORKDIR /app

# Install dependencies directly
RUN pip install --no-cache-dir "mcp[cli]" "pyjwt[crypto]" httpx structlog pydantic

COPY orchestrator/ orchestrator/

ENV PYTHONPATH=/app
EXPOSE 8014

CMD ["python", "-m", "orchestrator.main"]
