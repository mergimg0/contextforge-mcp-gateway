FROM python:3.12-slim

WORKDIR /app/servers

# Install dependencies directly
RUN pip install --no-cache-dir "mcp[cli]" "pyjwt[crypto]" httpx structlog pydantic numpy

# Copy shared modules and server source
COPY shared/ shared/
COPY risk/ risk/

ENV PYTHONPATH=/app/servers
EXPOSE 8011

CMD ["python", "-m", "risk.server"]
