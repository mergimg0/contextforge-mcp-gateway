FROM python:3.12-slim

WORKDIR /app

# Install dependencies directly
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx "pyjwt[crypto]" redis pyyaml pydantic pydantic-settings structlog prometheus-client

COPY gateway/ gateway/
COPY config/ config/

EXPOSE 9000

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "9000", "--log-level", "info"]
