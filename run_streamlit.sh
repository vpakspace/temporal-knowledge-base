#!/bin/bash
# Run the Streamlit UI
set -e
cd "$(dirname "$0")"

echo "Starting Temporal Knowledge Base UI on http://localhost:8501"
streamlit run ui/streamlit_app.py --server.port 8501
