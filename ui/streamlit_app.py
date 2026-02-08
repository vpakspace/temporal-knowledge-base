"""Streamlit UI for Temporal Knowledge Base.

Tabs:
1. Ingest  — Add episodes (text, JSON, documents, file upload)
2. Search  — Temporal-aware search with intent classification
3. Timeline — Entity timelines and fact evolution
4. Stats   — Graph statistics and overview
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

# Add project root to path for imports
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from ingestion.document_loader import DoclingLoader

API_BASE = "http://localhost:8000"

MAX_FILE_SIZE_MB = 10
_doc_loader = DoclingLoader()

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


def extract_text_from_file(uploaded_file) -> tuple[str | None, dict | None]:
    """Extract text content from uploaded file using DoclingLoader.

    Returns (markdown_text, metadata) or (None, None) on error.
    JSON files are handled specially (pretty-printed).
    """
    name = uploaded_file.name.lower()
    raw = uploaded_file.read()

    # JSON handled separately (not a Docling format)
    if name.endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8"))
            return json.dumps(data, ensure_ascii=False, indent=2), {"format": ".json"}
        except json.JSONDecodeError:
            st.error("Invalid JSON file")
            return None, None

    try:
        result = _doc_loader.load_bytes(raw, uploaded_file.name)
        if not result.markdown.strip():
            st.warning("Document has no extractable text (may be image-based)")
            return None, None
        return result.markdown, result.metadata
    except ValueError as e:
        st.error(str(e))
        return None, None
    except Exception as e:
        st.error(f"Document processing failed: {e}")
        return None, None


# --- Entity cache for autocomplete ---


@st.cache_data(ttl=30)
def _fetch_entities() -> list[dict]:
    """Fetch entities list from API (cached 30s)."""
    result = api_call("GET", "/api/entities")
    if result and result.get("success"):
        return result["data"]
    return []


# --- Tabs ---
tab_ingest, tab_search, tab_timeline, tab_graph, tab_stats = st.tabs(
    ["Ingest", "Search", "Timeline", "Graph", "Stats"]
)

# --- Tab 1: Ingest ---
with tab_ingest:
    st.header("Ingest Episode")

    input_method = st.radio(
        "Input method",
        ["Paste text", "Upload file"],
        horizontal=True,
    )

    content = ""

    if input_method == "Paste text":
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
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            uploaded = st.file_uploader(
                "Upload file",
                type=["txt", "md", "json", "pdf", "docx", "pptx", "xlsx", "html"],
                help=f"Supported: TXT, MD, JSON, PDF, DOCX, PPTX, XLSX, HTML (max {MAX_FILE_SIZE_MB} MB)",
            )
            if uploaded is not None:
                if uploaded.size > MAX_FILE_SIZE_MB * 1024 * 1024:
                    st.error(
                        f"File too large ({uploaded.size / 1024 / 1024:.1f} MB). "
                        f"Max: {MAX_FILE_SIZE_MB} MB"
                    )
                else:
                    extracted, doc_meta = extract_text_from_file(uploaded)
                    if extracted:
                        content = extracted
                        info_parts = [f"Extracted {len(content):,} characters from {uploaded.name}"]
                        if doc_meta:
                            if doc_meta.get("tables_count"):
                                info_parts.append(f"{doc_meta['tables_count']} tables")
                            if doc_meta.get("images_count"):
                                info_parts.append(f"{doc_meta['images_count']} images")
                            if doc_meta.get("pages"):
                                info_parts.append(f"{doc_meta['pages']} pages")
                        st.success(" | ".join(info_parts))
                        with st.expander("Preview content"):
                            st.text(content[:2000] + ("..." if len(content) > 2000 else ""))
        with col2:
            source = st.text_input(
                "Source",
                value=uploaded.name if uploaded else "file_upload",
            )
            # Auto-detect type from extension
            default_type = "text"
            if uploaded:
                ext = uploaded.name.lower().rsplit(".", 1)[-1] if "." in uploaded.name else ""
                if ext == "json":
                    default_type = "json"
                elif ext in {"pdf", "docx", "pptx", "xlsx", "html"}:
                    default_type = "document"
            type_options = ["text", "json", "chat", "document"]
            episode_type = st.selectbox(
                "Type",
                type_options,
                index=type_options.index(default_type),
            )
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
                "/api/ask",
                json={
                    "question": query,
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

    entities = _fetch_entities()
    entity_options = {f"{e['name']} ({e.get('entity_type', '?')})": e["id"] for e in entities}

    col_select, col_manual = st.columns([3, 1])
    with col_select:
        selected_label = st.selectbox(
            "Select entity",
            options=[""] + list(entity_options.keys()),
            index=0,
            placeholder="Choose an entity...",
        )
    with col_manual:
        manual_id = st.text_input("Or enter ID", placeholder="UUID")

    entity_id = entity_options.get(selected_label, "") or manual_id

    if st.button("Get Timeline", disabled=not entity_id):
        with st.spinner("Loading timeline..."):
            result = api_call("GET", f"/api/timeline/{entity_id}")
            if result and result.get("success"):
                events = result["data"]
                if events:
                    for ev in events:
                        superseded = " -> superseded" if ev.get("superseded_by") else ""
                        current_icon = "🟢" if ev.get("is_current") else "🔴"
                        st.markdown(
                            f"{current_icon} **{ev.get('valid_at', '?')}**: "
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
                    status = "🟢 CURRENT" if ev.get("is_current") else "🔴 Superseded"
                    st.markdown(
                        f"**Step {i + 1}** ({status}): {ev.get('statement', '')}\n"
                        f"- Valid: {ev.get('valid_at', '?')} | "
                        f"Invalid: {ev.get('invalid_at', '-')}"
                    )

# --- Tab 4: Graph ---
with tab_graph:
    st.header("Knowledge Graph")

    if st.button("Load Graph"):
        with st.spinner("Loading graph data..."):
            result = api_call("GET", "/api/graph")
            if result and result.get("success"):
                data = result["data"]
                nodes_data = data.get("nodes", [])
                edges_data = data.get("edges", [])

                if not nodes_data:
                    st.info("No entities in the graph yet. Ingest some data first.")
                else:
                    st.caption(f"{len(nodes_data)} entities, {len(edges_data)} relationships")

                    # Color by entity type
                    type_colors = {}
                    palette = [
                        "#4CAF50",
                        "#2196F3",
                        "#FF9800",
                        "#9C27B0",
                        "#F44336",
                        "#00BCD4",
                        "#795548",
                        "#607D8B",
                    ]
                    for n in nodes_data:
                        t = n.get("entity_type", "unknown")
                        if t not in type_colors:
                            type_colors[t] = palette[len(type_colors) % len(palette)]

                    ag_nodes = [
                        Node(
                            id=n["id"],
                            label=n.get("name", n["id"][:8]),
                            size=20,
                            color=type_colors.get(n.get("entity_type", ""), "#607D8B"),
                        )
                        for n in nodes_data
                    ]

                    # Only include edges where both source and target exist
                    node_ids = {n["id"] for n in nodes_data}
                    ag_edges = [
                        Edge(
                            source=e["source"],
                            target=e["target"],
                            label=e.get("label", ""),
                        )
                        for e in edges_data
                        if e["source"] in node_ids and e["target"] in node_ids
                    ]

                    config = Config(
                        width=900,
                        height=500,
                        directed=True,
                        physics=True,
                        hierarchical=False,
                    )

                    agraph(nodes=ag_nodes, edges=ag_edges, config=config)

                    # Legend
                    if type_colors:
                        st.subheader("Legend")
                        cols = st.columns(min(len(type_colors), 4))
                        for i, (t, color) in enumerate(type_colors.items()):
                            cols[i % len(cols)].markdown(
                                f"<span style='color:{color}'>&#9679;</span> {t}",
                                unsafe_allow_html=True,
                            )


# --- Tab 5: Stats ---
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
