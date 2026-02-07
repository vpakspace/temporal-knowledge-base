"""Streamlit UI for Temporal Knowledge Base.

Tabs:
1. Ingest  — Add episodes (text, JSON, documents)
2. Search  — Temporal-aware search with intent classification
3. Timeline — Entity timelines and fact evolution
4. Stats   — Graph statistics and overview
"""

from __future__ import annotations

import httpx
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="Temporal Knowledge Base",
    page_icon="🕐",
    layout="wide",
)

st.title("Temporal Knowledge Base")
st.caption("Graphiti + GraphOS | Bi-temporal Knowledge Graph")


def api_call(method: str, path: str, **kwargs):
    """Make API call to FastAPI backend."""
    url = f"{API_BASE}{path}"
    try:
        with httpx.Client(timeout=60) as client:
            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json=kwargs.get("json"))
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        st.error("API server not running. Start with: uvicorn api.server:app")
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


# --- Tabs ---
tab_ingest, tab_search, tab_timeline, tab_stats = st.tabs(
    ["Ingest", "Search", "Timeline", "Stats"]
)

# --- Tab 1: Ingest ---
with tab_ingest:
    st.header("Ingest Episode")

    col1, col2 = st.columns([3, 1])
    with col1:
        content = st.text_area(
            "Content",
            height=200,
            placeholder="Paste text, JSON, or document content...",
        )
    with col2:
        source = st.text_input("Source", value="manual")
        episode_type = st.selectbox("Type", ["text", "json", "chat", "document"])
        group_id = st.text_input("Group ID (optional)", value="")

    if st.button("Ingest", type="primary", disabled=not content):
        with st.spinner("Processing episode..."):
            result = api_call(
                "POST",
                "/api/ingest",
                json={
                    "content": content,
                    "source": source,
                    "episode_type": episode_type,
                    "group_id": group_id or None,
                },
            )
            if result and result.get("success"):
                data = result["data"]
                st.success("Episode ingested!")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Entities", data.get("entities_extracted", 0))
                c2.metric("Events", data.get("temporal_events", 0))
                c3.metric("Relations", data.get("relationships", 0))
                c4.metric("Invalidated", data.get("invalidated", 0))

# --- Tab 2: Search ---
with tab_search:
    st.header("Temporal Search")

    query = st.text_input("Query", placeholder="What changed in 2024?")

    col1, col2, col3 = st.columns(3)
    with col1:
        intent = st.selectbox("Intent", ["hybrid", "structural", "temporal"])
    with col2:
        limit = st.slider("Results", 1, 50, 10)
    with col3:
        include_timeline = st.checkbox("Include timeline")

    if st.button("Search", type="primary", disabled=not query):
        with st.spinner("Searching..."):
            result = api_call(
                "POST",
                "/api/search",
                json={
                    "query": query,
                    "intent": intent,
                    "limit": limit,
                    "include_timeline": include_timeline,
                },
            )
            if result and result.get("success"):
                data = result["data"]

                st.subheader("Answer")
                st.write(data.get("answer", "No answer"))
                st.caption(f"Based on {data.get('facts_used', 0)} verified facts")

                if data.get("sources"):
                    st.subheader("Sources")
                    for src in data["sources"]:
                        valid_at = src.get("valid_at", "unknown")
                        st.markdown(f"- **{src['content']}** (valid: {valid_at})")

                if data.get("timeline"):
                    st.subheader("Timeline")
                    for item in data["timeline"]:
                        icon = "✅" if item.get("is_current") else "❌"
                        st.markdown(f"{icon} **{item['date']}**: {item['fact']}")

# --- Tab 3: Timeline ---
with tab_timeline:
    st.header("Entity Timeline")

    entity_id = st.text_input("Entity ID", placeholder="Enter entity UUID")
    if st.button("Get Timeline", disabled=not entity_id):
        with st.spinner("Loading timeline..."):
            result = api_call("GET", f"/api/timeline/{entity_id}")
            if result and result.get("success"):
                events = result["data"]
                if events:
                    for ev in events:
                        superseded = " → superseded" if ev.get("superseded_by") else ""
                        current = "🟢" if ev.get("is_current") else "🔴"
                        st.markdown(
                            f"{current} **{ev.get('valid_at', '?')}**: "
                            f"{ev.get('statement', '')}{superseded}"
                        )
                else:
                    st.info("No events found for this entity")

    st.divider()
    st.subheader("Fact Evolution")
    event_id = st.text_input("Event ID", placeholder="Enter event UUID")
    if st.button("Get Evolution", disabled=not event_id):
        with st.spinner("Loading evolution chain..."):
            result = api_call("GET", f"/api/evolution/{event_id}")
            if result and result.get("success"):
                chain = result["data"]
                for i, ev in enumerate(chain):
                    current = "🟢 CURRENT" if ev.get("is_current") else "🔴 Superseded"
                    st.markdown(
                        f"**Step {i + 1}** ({current}): {ev.get('statement', '')}\n"
                        f"- Valid: {ev.get('valid_at', '?')} | "
                        f"Invalid: {ev.get('invalid_at', '-')}"
                    )

# --- Tab 4: Stats ---
with tab_stats:
    st.header("Graph Statistics")

    if st.button("Refresh Stats"):
        with st.spinner("Loading..."):
            result = api_call("GET", "/api/stats")
            if result and result.get("success"):
                data = result["data"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Entities", data.get("entities", 0))
                c2.metric("Total Events", data.get("events", 0))
                c3.metric("Current Events", data.get("current_events", 0))
                c4.metric("Episodes", data.get("episodes", 0))

                if data.get("events", 0) > 0:
                    invalidated = data.get("events", 0) - data.get("current_events", 0)
                    st.progress(
                        data.get("current_events", 0) / max(data.get("events", 1), 1),
                        text=f"{data.get('current_events', 0)} current / {invalidated} superseded",
                    )
