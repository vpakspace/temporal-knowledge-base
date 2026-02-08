"""Streamlit UI for Temporal Knowledge Base.

Tabs:
1. Ingest         — Add episodes (text, JSON, documents, file upload)
2. Search         — Temporal-aware search with intent classification
3. Entities       — Entity explorer with filters, search, drill-down
4. Timeline       — Entity timelines and fact evolution
5. Graph          — Interactive knowledge graph visualization
6. Contradictions — Supersession chains, hotspots, invalidation log
7. Stats          — Graph statistics, export/import
"""

from __future__ import annotations

import json
import os
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

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
API_KEY = os.environ.get("APP_API_KEY", "")

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
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        with httpx.Client(timeout=60, headers=headers) as client:
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
tab_ingest, tab_search, tab_entities, tab_timeline, tab_graph, tab_contra, tab_stats = st.tabs(
    ["Ingest", "Search", "Entities", "Timeline", "Graph", "Contradictions", "Stats"]
)

# --- Tab 1: Ingest ---
with tab_ingest:
    st.header("Ingest Episode")

    input_method = st.radio(
        "Input method",
        ["Paste text", "Upload file", "Batch (JSON)"],
        horizontal=True,
    )

    content = ""

    if input_method == "Batch (JSON)":
        st.markdown(
            "Paste a JSON array of episodes. Each item: "
            '`{"content": "...", "source": "...", "episode_type": "text"}`'
        )
        batch_json = st.text_area(
            "Batch JSON",
            height=250,
            placeholder='[{"content": "Fact 1", "source": "src1"}, {"content": "Fact 2", "source": "src2"}]',
            key="batch_json",
        )
        if st.button("Ingest Batch", type="primary", disabled=not batch_json.strip()):
            try:
                episodes = json.loads(batch_json)
                if not isinstance(episodes, list):
                    st.error("JSON must be an array of objects")
                else:
                    progress = st.progress(0, text="Starting batch ingestion...")
                    result = api_call("POST", "/api/ingest/batch", json=episodes)
                    progress.progress(100, text="Done!")
                    if result and result.get("success"):
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total", result["total"])
                        c2.metric("Succeeded", result["succeeded"])
                        c3.metric("Failed", result["failed"])
                        if result["failed"] > 0:
                            for r in result["results"]:
                                if not r["success"]:
                                    st.error(f"Episode {r['index']}: {r['error']}")
            except json.JSONDecodeError:
                st.error("Invalid JSON")

    elif input_method == "Paste text":
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

# --- Tab 3: Entities ---
with tab_entities:
    st.header("Entity Explorer")

    entities = _fetch_entities()

    if not entities:
        st.info("No entities yet. Ingest some data first.")
    else:
        # Filters
        col_search, col_type = st.columns([2, 1])
        with col_search:
            name_filter = st.text_input(
                "Search by name",
                placeholder="Type to filter...",
                key="entity_search",
            )
        with col_type:
            all_types = sorted({e.get("entity_type", "unknown") for e in entities})
            type_filter = st.multiselect("Filter by type", all_types, key="entity_type_filter")

        # Apply filters
        filtered = entities
        if name_filter:
            q = name_filter.lower()
            filtered = [e for e in filtered if q in e.get("name", "").lower()]
        if type_filter:
            filtered = [e for e in filtered if e.get("entity_type") in type_filter]

        st.caption(f"{len(filtered)} of {len(entities)} entities")

        # Entity table
        if filtered:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        "Name": e.get("name", ""),
                        "Type": e.get("entity_type", ""),
                        "ID": e.get("id", ""),
                    }
                    for e in filtered
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Entity details
            st.divider()
            st.subheader("Entity Details")

            detail_options = {
                f"{e['name']} ({e.get('entity_type', '?')})": e["id"] for e in filtered
            }
            selected = st.selectbox(
                "Select entity to inspect",
                options=[""] + list(detail_options.keys()),
                index=0,
                key="entity_detail_select",
            )

            if selected:
                eid = detail_options[selected]
                with st.spinner("Loading details..."):
                    result = api_call("GET", f"/api/entities/{eid}")
                    if result and result.get("success"):
                        d = result["data"]

                        # Metrics
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total Events", d.get("total_events", 0))
                        c2.metric("Current Events", d.get("current_events", 0))
                        c3.metric("Relationships", len(d.get("relationships", [])))

                        # Info
                        st.markdown(f"**Canonical name**: {d.get('canonical_name', '-')}")
                        if d.get("valid_at"):
                            st.markdown(f"**Valid at**: {d['valid_at']}")

                        # Relationships table
                        rels = d.get("relationships", [])
                        if rels:
                            st.subheader("Relationships")
                            for r in rels:
                                direction = "<-" if r.get("direction") == "incoming" else "->"
                                st.markdown(
                                    f"- {direction} **{r.get('relation_type', '?')}** "
                                    f"{direction} {r.get('target_name', r.get('target_id', '?')[:8])}"
                                )
                        else:
                            st.info("No relationships found")

# --- Tab 4: Timeline ---
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

# --- Tab 5: Graph ---
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

    # --- Communities section ---
    st.divider()
    st.subheader("Communities / Clusters")

    col_detect, col_build = st.columns(2)

    with col_detect:
        if st.button("Detect Clusters"):
            with st.spinner("Detecting communities..."):
                result = api_call("GET", "/api/communities")
                if result and result.get("success"):
                    source = result.get("source", "clusters")
                    communities = result["data"]

                    if not communities:
                        st.info("No clusters found. Ingest more data to form connections.")
                    else:
                        st.caption(
                            f"Source: {'Graphiti Communities' if source == 'graphiti' else 'Connected Components'} "
                            f"| {len(communities)} clusters"
                        )
                        for comm in communities:
                            members = comm.get("members", [])
                            label = (
                                comm.get("name")
                                or comm.get("summary")
                                or f"Cluster {comm.get('cluster_id', '?')}"
                            )
                            size = comm.get("member_count") or comm.get("size", len(members))
                            with st.expander(f"{label} ({size} members)", expanded=False):
                                if comm.get("summary"):
                                    st.markdown(f"*{comm['summary']}*")
                                for m in members:
                                    st.markdown(
                                        f"- **{m.get('name', '?')}** ({m.get('entity_type', '?')})"
                                    )

    with col_build:
        st.caption("Build Graphiti communities (uses LLM for summarization)")
        if st.button("Build Communities (LLM)"):
            with st.spinner("Building communities via Graphiti (may take a minute)..."):
                result = api_call("POST", "/api/communities/build")
                if result and result.get("success"):
                    data = result["data"]
                    st.success(
                        f"Built {data.get('communities', 0)} communities "
                        f"with {data.get('edges', 0)} membership edges"
                    )
                    for d in data.get("details", []):
                        st.markdown(f"- **{d.get('name', '?')}**: {d.get('summary', '')[:200]}")


# --- Tab 6: Contradictions ---
with tab_contra:
    st.header("Contradiction Dashboard")
    st.caption("Supersession chains, entity hotspots, and invalidation log")

    if st.button("Load Contradictions"):
        with st.spinner("Loading contradiction data..."):
            result = api_call("GET", "/api/contradictions")
            if result and result.get("success"):
                cdata = result["data"]
                chains = cdata.get("chains", [])
                hotspots = cdata.get("hotspots", [])
                log = cdata.get("invalidation_log", [])

                # --- Summary metrics ---
                c1, c2, c3 = st.columns(3)
                c1.metric("Supersession Chains", len(chains))
                c2.metric("Entity Hotspots", len(hotspots))
                c3.metric("Invalidated Facts", len(log))

                # --- Entity Hotspots ---
                if hotspots:
                    st.subheader("Entity Hotspots")
                    st.caption("Entities with the most superseded facts")
                    import pandas as pd

                    df_hot = pd.DataFrame(hotspots)
                    df_hot.columns = ["ID", "Name", "Type", "Superseded Facts"]
                    st.dataframe(
                        df_hot[["Name", "Type", "Superseded Facts"]],
                        use_container_width=True,
                        hide_index=True,
                    )

                # --- Supersession Chains ---
                if chains:
                    st.subheader("Supersession Chains")
                    st.caption("Old facts replaced by new facts")
                    for ch in chains:
                        entities_str = ", ".join(ch.get("entities", [])) or "—"
                        is_current = ch.get("new_is_current", False)
                        status_icon = "🟢" if is_current else "🔄"
                        with st.expander(
                            f"{status_icon} {entities_str}: "
                            f"{(ch.get('old_statement') or '')[:80]}",
                            expanded=False,
                        ):
                            st.markdown("**Old (superseded):**")
                            st.markdown(
                                f"> {ch.get('old_statement', '—')}\n\n"
                                f"Valid: `{ch.get('old_valid_at', '?')}` | "
                                f"Invalidated: `{ch.get('old_invalid_at', '—')}`"
                            )
                            st.markdown("**New (replacement):**")
                            st.markdown(
                                f"> {ch.get('new_statement', '—')}\n\n"
                                f"Valid: `{ch.get('new_valid_at', '?')}` | "
                                f"Current: {'Yes' if is_current else 'No'}"
                            )
                else:
                    st.info("No supersession chains found. All facts are current.")

                # --- Invalidation Log ---
                if log:
                    st.subheader("Invalidation Log")
                    st.caption("Recent fact invalidations (newest first)")
                    for entry in log:
                        entities_str = ", ".join(entry.get("entities", [])) or "—"
                        replaced_by = entry.get("replaced_by")
                        st.markdown(
                            f"- **{(entry.get('statement') or '—')[:100]}**\n"
                            f"  - Entities: {entities_str}\n"
                            f"  - Valid: `{entry.get('valid_at', '?')}` → "
                            f"Invalidated: `{entry.get('invalid_at', '—')}`\n"
                            f"  - Replaced by: {replaced_by or '(no replacement)'}"
                        )


# --- Tab 7: Stats ---
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

    st.divider()

    # --- Export ---
    st.subheader("Export / Import")

    col_exp, col_imp = st.columns(2)

    with col_exp:
        if st.button("Export Graph Data"):
            with st.spinner("Exporting..."):
                result = api_call("GET", "/api/export")
                if result and result.get("success"):
                    export_data = result["data"]
                    export_json = json.dumps(export_data, indent=2, default=str)
                    st.download_button(
                        label="Download JSON",
                        data=export_json,
                        file_name="tkb_export.json",
                        mime="application/json",
                    )
                    st.success(
                        f"Entities: {len(export_data.get('entities', []))}, "
                        f"Events: {len(export_data.get('events', []))}, "
                        f"Episodes: {len(export_data.get('episodes', []))}"
                    )

    with col_imp:
        uploaded = st.file_uploader("Import JSON", type=["json"], key="import_json")
        if uploaded is not None:
            try:
                import_data = json.loads(uploaded.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                st.error("Invalid JSON file")
                import_data = None

            if import_data:
                if import_data.get("version") != "1.0":
                    st.warning("Unknown export version, may not be compatible")
                st.info(
                    f"Entities: {len(import_data.get('entities', []))}, "
                    f"Events: {len(import_data.get('events', []))}, "
                    f"Episodes: {len(import_data.get('episodes', []))}"
                )
                if st.button("Confirm Import"):
                    with st.spinner("Importing..."):
                        result = api_call("POST", "/api/import", json=import_data)
                        if result and result.get("success"):
                            counts = result["data"]
                            st.success(
                                f"Imported: {counts.get('entities', 0)} entities, "
                                f"{counts.get('events', 0)} events, "
                                f"{counts.get('episodes', 0)} episodes, "
                                f"{counts.get('relationships', 0)} relationships"
                            )
