#!/bin/bash
# Run the FastAPI server
set -e
cd "$(dirname "$0")"

if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "Starting Temporal Knowledge Base API on http://localhost:8000"
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
