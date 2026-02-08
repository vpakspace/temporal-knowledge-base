FROM python:3.12-slim

WORKDIR /app

# System dependencies for neo4j driver and docling
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default: run API server
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
