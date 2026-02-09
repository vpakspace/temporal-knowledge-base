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
from ui.i18n import get_translator  # type: ignore[import-not-found]

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
API_KEY = os.environ.get("APP_API_KEY", "")

MAX_FILE_SIZE_MB = 10
_doc_loader = DoclingLoader()

st.set_page_config(
    page_title="Temporal Knowledge Base",
    page_icon="🕐",
    layout="wide",
)

# --- Language selector ---
if "lang" not in st.session_state:
    st.session_state.lang = "en"

lang = st.sidebar.selectbox(
    "Language / Язык",
    options=["en", "ru"],
    index=0 if st.session_state.lang == "en" else 1,
    format_func=lambda x: "English" if x == "en" else "Русский",
    key="lang_select",
)
st.session_state.lang = lang
t = get_translator(lang)

st.title(t("page_title"))
st.caption(t("page_caption"))


def api_call(method: str, path: str, **kwargs):
    """Make API call to FastAPI backend."""
    url = f"{API_BASE}{path}"
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    timeout = kwargs.pop("timeout", 900)
    try:
        with httpx.Client(timeout=timeout, headers=headers) as client:
            if method == "GET":
                resp = client.get(url)
            elif kwargs.get("files"):
                resp = client.post(url, files=kwargs["files"])
            else:
                resp = client.post(url, json=kwargs.get("json"))
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        st.error(t("api_not_running"))
        return None
    except Exception as e:
        st.error(t("api_error", e=e))
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
            st.error(t("invalid_json_file"))
            return None, None

    try:
        result = _doc_loader.load_bytes(raw, uploaded_file.name)
        if not result.markdown.strip():
            st.warning(t("no_extractable_text"))
            return None, None
        return result.markdown, result.metadata
    except ValueError as e:
        st.error(str(e))
        return None, None
    except Exception as e:
        st.error(t("doc_processing_failed", e=e))
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
    [
        t("tab_ingest"),
        t("tab_search"),
        t("tab_entities"),
        t("tab_timeline"),
        t("tab_graph"),
        t("tab_contradictions"),
        t("tab_stats"),
    ]
)

# --- Tab 1: Ingest ---
with tab_ingest:
    st.header(t("ingest_header"))

    input_method = st.radio(
        t("input_method"),
        [t("paste_text"), t("upload_file"), t("batch_json")],
        horizontal=True,
    )

    content = ""
    source = "manual"
    episode_type = "text"
    group_id = ""

    if input_method == t("batch_json"):
        st.markdown(t("batch_json_help"))
        batch_json = st.text_area(
            t("batch_json_label"),
            height=250,
            placeholder='[{"content": "Fact 1", "source": "src1"}, {"content": "Fact 2", "source": "src2"}]',
            key="batch_json",
        )
        if st.button(t("ingest_batch_btn"), type="primary", disabled=not batch_json.strip()):
            try:
                episodes = json.loads(batch_json)
                if not isinstance(episodes, list):
                    st.error(t("json_must_be_array"))
                else:
                    progress = st.progress(0, text=t("starting_batch"))
                    result = api_call("POST", "/api/ingest/batch", json=episodes)
                    progress.progress(100, text=t("done"))
                    if result and result.get("success"):
                        c1, c2, c3 = st.columns(3)
                        c1.metric(t("total"), result["total"])
                        c2.metric(t("succeeded"), result["succeeded"])
                        c3.metric(t("failed"), result["failed"])
                        if result["failed"] > 0:
                            for r in result["results"]:
                                if not r["success"]:
                                    st.error(f"Episode {r['index']}: {r['error']}")
            except json.JSONDecodeError:
                st.error(t("invalid_json"))

    elif input_method == t("paste_text"):
        col1, col2 = st.columns([3, 1])
        with col1:
            content = st.text_area(
                t("content_label"),
                height=200,
                placeholder=t("content_placeholder"),
            )
        with col2:
            source = st.text_input(t("source_label"), value="manual")
            episode_type = st.selectbox(t("type_label"), ["text", "json", "chat", "document"])
            group_id = st.text_input(t("group_id_label"), value="")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            uploaded = st.file_uploader(
                t("upload_file_label"),
                type=["txt", "md", "json", "pdf", "docx", "pptx", "xlsx", "html"],
                help=t("upload_help", max_mb=MAX_FILE_SIZE_MB),
            )
            if uploaded is not None:
                if uploaded.size > MAX_FILE_SIZE_MB * 1024 * 1024:
                    st.error(
                        t(
                            "file_too_large",
                            size=uploaded.size / 1024 / 1024,
                            max_mb=MAX_FILE_SIZE_MB,
                        )
                    )
                else:
                    extracted, doc_meta = extract_text_from_file(uploaded)
                    if extracted:
                        content = extracted
                        info_parts = [t("extracted_chars", count=len(content), name=uploaded.name)]
                        if doc_meta:
                            if doc_meta.get("tables_count"):
                                info_parts.append(f"{doc_meta['tables_count']} {t('tables')}")
                            if doc_meta.get("images_count"):
                                info_parts.append(f"{doc_meta['images_count']} {t('images')}")
                            if doc_meta.get("pages"):
                                info_parts.append(f"{doc_meta['pages']} {t('pages')}")
                        st.success(" | ".join(info_parts))
                        with st.expander(t("preview_content")):
                            st.text(content[:2000] + ("..." if len(content) > 2000 else ""))
        with col2:
            source = st.text_input(
                t("source_label"),
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
                t("type_label"),
                type_options,
                index=type_options.index(default_type),
            )
            group_id = st.text_input(t("group_id_label"), value="")

    if st.button(t("ingest_btn"), type="primary", disabled=not content):
        with st.spinner(t("processing_episode")):
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
                st.success(t("episode_ingested"))
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(t("entities"), data.get("entities_extracted", 0))
                c2.metric(t("events"), data.get("temporal_events", 0))
                c3.metric(t("relations"), data.get("relationships", 0))
                c4.metric(t("invalidated"), data.get("invalidated", 0))

# --- Tab 2: Search ---
with tab_search:
    st.header(t("search_header"))

    query = st.text_input(t("query_label"), placeholder=t("query_placeholder"))

    col1, col2, col3 = st.columns(3)
    with col1:
        intent = st.selectbox(t("intent_label"), ["hybrid", "structural", "temporal"])
    with col2:
        limit = st.slider(t("results_label"), 1, 50, 10)
    with col3:
        include_timeline = st.checkbox(t("include_timeline"))

    if st.button(t("search_btn"), type="primary", disabled=not query):
        with st.spinner(t("searching")):
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

                st.subheader(t("answer"))
                st.write(data.get("answer", t("no_answer")))
                st.caption(t("based_on_facts", count=data.get("facts_used", 0)))

                if data.get("sources"):
                    st.subheader(t("sources"))
                    for src in data["sources"]:
                        valid_at = src.get("valid_at", "unknown")
                        st.markdown(f"- **{src['content']}** (valid: {valid_at})")

                if data.get("timeline"):
                    st.subheader(t("timeline"))
                    for item in data["timeline"]:
                        icon = "✅" if item.get("is_current") else "❌"
                        st.markdown(f"{icon} **{item['date']}**: {item['fact']}")

# --- Tab 3: Entities ---
with tab_entities:
    st.header(t("entity_explorer"))

    entities = _fetch_entities()

    if not entities:
        st.info(t("no_entities_yet"))
    else:
        # Filters
        col_search, col_type = st.columns([2, 1])
        with col_search:
            name_filter = st.text_input(
                t("search_by_name"),
                placeholder=t("type_to_filter"),
                key="entity_search",
            )
        with col_type:
            all_types = sorted({e.get("entity_type") or "unknown" for e in entities})
            type_filter = st.multiselect(t("filter_by_type"), all_types, key="entity_type_filter")

        # Apply filters
        filtered = entities
        if name_filter:
            q = name_filter.lower()
            filtered = [e for e in filtered if q in e.get("name", "").lower()]
        if type_filter:
            filtered = [e for e in filtered if e.get("entity_type") in type_filter]

        st.caption(t("x_of_y_entities", filtered=len(filtered), total=len(entities)))

        # Entity table
        if filtered:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        t("col_name"): e.get("name", ""),
                        t("col_type"): e.get("entity_type", ""),
                        t("col_id"): e.get("id", ""),
                    }
                    for e in filtered
                ]
            )
            st.dataframe(df, width="stretch", hide_index=True)

            # Entity details
            st.divider()
            st.subheader(t("entity_details"))

            detail_options = {
                f"{e['name']} ({e.get('entity_type', '?')})": e["id"] for e in filtered
            }
            selected = st.selectbox(
                t("select_entity_inspect"),
                options=[""] + list(detail_options.keys()),
                index=0,
                key="entity_detail_select",
            )

            if selected:
                eid = detail_options[selected]
                with st.spinner(t("loading_details")):
                    result = api_call("GET", f"/api/entities/{eid}")
                    if result and result.get("success"):
                        d = result["data"]

                        # Metrics
                        c1, c2, c3 = st.columns(3)
                        c1.metric(t("total_events"), d.get("total_events", 0))
                        c2.metric(t("current_events"), d.get("current_events", 0))
                        c3.metric(t("relationships"), len(d.get("relationships", [])))

                        # Info
                        st.markdown(f"**{t('canonical_name')}**: {d.get('canonical_name', '-')}")
                        if d.get("valid_at"):
                            st.markdown(f"**{t('valid_at')}**: {d['valid_at']}")

                        # Relationships table
                        rels = d.get("relationships", [])
                        if rels:
                            st.subheader(t("relationships"))
                            for r in rels:
                                direction = "<-" if r.get("direction") == "incoming" else "->"
                                st.markdown(
                                    f"- {direction} **{r.get('relation_type', '?')}** "
                                    f"{direction} {r.get('target_name', r.get('target_id', '?')[:8])}"
                                )
                        else:
                            st.info(t("no_relationships"))

# --- Tab 4: Timeline ---
with tab_timeline:
    st.header(t("entity_timeline"))

    entities = _fetch_entities()
    entity_options = {f"{e['name']} ({e.get('entity_type', '?')})": e["id"] for e in entities}

    col_select, col_manual = st.columns([3, 1])
    with col_select:
        selected_label = st.selectbox(
            t("select_entity"),
            options=[""] + list(entity_options.keys()),
            index=0,
            placeholder=t("choose_entity"),
        )
    with col_manual:
        manual_id = st.text_input(t("or_enter_id"), placeholder=t("uuid_placeholder"))

    entity_id = entity_options.get(selected_label, "") or manual_id

    if st.button(t("get_timeline_btn"), disabled=not entity_id):
        with st.spinner(t("loading_timeline")):
            result = api_call("GET", f"/api/timeline/{entity_id}")
            if result and result.get("success"):
                events = result["data"]
                if events:
                    for ev in events:
                        superseded_text = (
                            f" -> {t('superseded')}" if ev.get("superseded_by") else ""
                        )
                        current_icon = "🟢" if ev.get("is_current") else "🔴"
                        st.markdown(
                            f"{current_icon} **{ev.get('valid_at', '?')}**: "
                            f"{ev.get('statement', '')}{superseded_text}"
                        )
                else:
                    st.info(t("no_events_entity"))

    st.divider()
    st.subheader(t("fact_evolution"))
    event_id = st.text_input(t("event_id_label"), placeholder=t("enter_event_uuid"))
    if st.button(t("get_evolution_btn"), disabled=not event_id):
        with st.spinner(t("loading_evolution")):
            result = api_call("GET", f"/api/evolution/{event_id}")
            if result and result.get("success"):
                chain = result["data"]
                for i, ev in enumerate(chain):
                    status = (
                        f"🟢 {t('current_status')}"
                        if ev.get("is_current")
                        else f"🔴 {t('superseded_status')}"
                    )
                    st.markdown(
                        f"**{t('step_n', n=i + 1)}** ({status}): {ev.get('statement', '')}\n"
                        f"- Valid: {ev.get('valid_at', '?')} | "
                        f"Invalid: {ev.get('invalid_at', '-')}"
                    )

# --- Tab 5: Graph ---
with tab_graph:
    st.header(t("knowledge_graph"))

    if st.button(t("load_graph_btn")):
        with st.spinner(t("loading_graph")):
            result = api_call("GET", "/api/graph")
            if result and result.get("success"):
                data = result["data"]
                nodes_data = data.get("nodes", [])
                edges_data = data.get("edges", [])

                if not nodes_data:
                    st.info(t("no_entities_graph"))
                else:
                    st.caption(
                        t(
                            "n_entities_m_rels",
                            nodes=len(nodes_data),
                            edges=len(edges_data),
                        )
                    )

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
                        tp = n.get("entity_type", "unknown")
                        if tp not in type_colors:
                            type_colors[tp] = palette[len(type_colors) % len(palette)]

                    ag_nodes = [
                        Node(
                            id=n["id"],
                            label=n.get("name") or (n["id"] or "?")[:8],
                            size=20,
                            color=type_colors.get(n.get("entity_type") or "", "#607D8B"),
                        )
                        for n in nodes_data
                        if n.get("id")
                    ]

                    # Only include edges where both source and target exist
                    node_ids = {n["id"] for n in nodes_data if n.get("id")}
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
                        st.subheader(t("legend"))
                        cols = st.columns(min(len(type_colors), 4))
                        for i, (tp, color) in enumerate(type_colors.items()):
                            cols[i % len(cols)].markdown(
                                f"<span style='color:{color}'>&#9679;</span> {tp}",
                                unsafe_allow_html=True,
                            )

    # --- Communities section ---
    st.divider()
    st.subheader(t("communities_clusters"))

    col_detect, col_build = st.columns(2)

    with col_detect:
        if st.button(t("detect_clusters_btn")):
            with st.spinner(t("detecting_communities")):
                result = api_call("GET", "/api/communities")
                if result and result.get("success"):
                    source = result.get("source", "clusters")
                    communities = result["data"]

                    if not communities:
                        st.info(t("no_clusters"))
                    else:
                        source_name = (
                            t("graphiti_communities")
                            if source == "graphiti"
                            else t("connected_components")
                        )
                        st.caption(t("source_clusters", source=source_name, count=len(communities)))
                        for comm in communities:
                            members = comm.get("members", [])
                            label = (
                                comm.get("name")
                                or comm.get("summary")
                                or f"Cluster {comm.get('cluster_id', '?')}"
                            )
                            size = comm.get("member_count") or comm.get("size", len(members))
                            with st.expander(f"{label} ({t('n_members', n=size)})", expanded=False):
                                if comm.get("summary"):
                                    st.markdown(f"*{comm['summary']}*")
                                for m in members:
                                    st.markdown(
                                        f"- **{m.get('name', '?')}** ({m.get('entity_type', '?')})"
                                    )

    with col_build:
        st.caption(t("build_communities_caption"))
        if st.button(t("build_communities_btn")):
            with st.spinner(t("building_communities")):
                result = api_call("POST", "/api/communities/build")
                if result and result.get("success"):
                    data = result["data"]
                    st.success(
                        t(
                            "built_communities",
                            communities=data.get("communities", 0),
                            edges=data.get("edges", 0),
                        )
                    )
                    for d in data.get("details", []):
                        st.markdown(f"- **{d.get('name', '?')}**: {d.get('summary', '')[:200]}")


# --- Tab 6: Contradictions ---
with tab_contra:
    st.header(t("contradiction_dashboard"))
    st.caption(t("contradiction_caption"))

    if st.button(t("load_contradictions_btn")):
        with st.spinner(t("loading_contradictions")):
            result = api_call("GET", "/api/contradictions")
            if result and result.get("success"):
                cdata = result["data"]
                chains = cdata.get("chains", [])
                hotspots = cdata.get("hotspots", [])
                log = cdata.get("invalidation_log", [])

                # --- Summary metrics ---
                c1, c2, c3 = st.columns(3)
                c1.metric(t("supersession_chains"), len(chains))
                c2.metric(t("entity_hotspots"), len(hotspots))
                c3.metric(t("invalidated_facts"), len(log))

                # --- Entity Hotspots ---
                if hotspots:
                    st.subheader(t("entity_hotspots"))
                    st.caption(t("entities_most_superseded"))
                    import pandas as pd

                    df_hot = pd.DataFrame(hotspots)
                    df_hot.columns = [
                        t("col_id"),
                        t("col_name"),
                        t("col_type"),
                        t("col_superseded_facts"),
                    ]
                    st.dataframe(
                        df_hot[[t("col_name"), t("col_type"), t("col_superseded_facts")]],
                        width="stretch",
                        hide_index=True,
                    )

                # --- Supersession Chains ---
                if chains:
                    st.subheader(t("supersession_chains"))
                    st.caption(t("old_facts_replaced"))
                    for ch in chains:
                        entities_str = ", ".join(ch.get("entities", [])) or "—"
                        is_current = ch.get("new_is_current", False)
                        status_icon = "🟢" if is_current else "🔄"
                        with st.expander(
                            f"{status_icon} {entities_str}: "
                            f"{(ch.get('old_statement') or '')[:80]}",
                            expanded=False,
                        ):
                            st.markdown(f"**{t('old_superseded')}**")
                            st.markdown(
                                f"> {ch.get('old_statement', '—')}\n\n"
                                f"Valid: `{ch.get('old_valid_at', '?')}` | "
                                f"Invalidated: `{ch.get('old_invalid_at', '—')}`"
                            )
                            st.markdown(f"**{t('new_replacement')}**")
                            current_text = t("current_yes") if is_current else t("current_no")
                            st.markdown(
                                f"> {ch.get('new_statement', '—')}\n\n"
                                f"Valid: `{ch.get('new_valid_at', '?')}` | "
                                f"{t('current_label')}: {current_text}"
                            )
                else:
                    st.info(t("no_supersession_chains"))

                # --- Invalidation Log ---
                if log:
                    st.subheader(t("invalidation_log"))
                    st.caption(t("recent_invalidations"))
                    for entry in log:
                        entities_str = ", ".join(entry.get("entities", [])) or "—"
                        replaced_by = entry.get("replaced_by")
                        replaced_text = replaced_by or t("no_replacement")
                        st.markdown(
                            f"- **{(entry.get('statement') or '—')[:100]}**\n"
                            f"  - {t('entities')}: {entities_str}\n"
                            f"  - Valid: `{entry.get('valid_at', '?')}` → "
                            f"Invalidated: `{entry.get('invalid_at', '—')}`\n"
                            f"  - {t('replaced_by')}: {replaced_text}"
                        )


# --- Tab 7: Stats ---
with tab_stats:
    st.header(t("graph_statistics"))

    if st.button(t("refresh_stats_btn")):
        with st.spinner(t("loading")):
            result = api_call("GET", "/api/stats")
            if result and result.get("success"):
                data = result["data"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(t("entities"), data.get("entities", 0))
                c2.metric(t("total_events"), data.get("events", 0))
                c3.metric(t("current_events"), data.get("current_events", 0))
                c4.metric(t("episodes"), data.get("episodes", 0))

                if data.get("events", 0) > 0:
                    invalidated_count = data.get("events", 0) - data.get("current_events", 0)
                    st.progress(
                        data.get("current_events", 0) / max(data.get("events", 1), 1),
                        text=t(
                            "current_superseded_progress",
                            current=data.get("current_events", 0),
                            superseded=invalidated_count,
                        ),
                    )

    st.divider()

    # --- Cache Stats ---
    st.subheader(t("cache_statistics"))
    st.caption(t("cache_caption"))

    col_cache, col_clear = st.columns([3, 1])
    with col_cache:
        if st.button(t("refresh_cache_btn")):
            result = api_call("GET", "/api/cache/stats")
            if result and result.get("success"):
                data = result["data"]
                llm_stats = data.get("llm", {})
                emb_stats = data.get("embeddings", {})

                lc, ec = st.columns(2)
                with lc:
                    st.markdown(f"**{t('llm_cache')}**")
                    st.metric(t("entries"), llm_stats.get("size", 0))
                    st.metric(t("hit_rate"), f"{llm_stats.get('hit_rate_pct', 0)}%")
                    st.caption(
                        t(
                            "hits_misses",
                            hits=llm_stats.get("hits", 0),
                            misses=llm_stats.get("misses", 0),
                        )
                    )
                with ec:
                    st.markdown(f"**{t('embedding_cache')}**")
                    st.metric(t("entries"), emb_stats.get("size", 0))
                    st.metric(t("hit_rate"), f"{emb_stats.get('hit_rate_pct', 0)}%")
                    st.caption(
                        t(
                            "hits_misses",
                            hits=emb_stats.get("hits", 0),
                            misses=emb_stats.get("misses", 0),
                        )
                    )
    with col_clear:
        if st.button(t("clear_caches_btn")):
            result = api_call("POST", "/api/cache/clear")
            if result and result.get("success"):
                st.success(t("caches_cleared"))

    st.divider()

    # --- Metrics ---
    st.subheader(t("api_metrics"))
    st.caption(t("metrics_caption"))

    if st.button(t("refresh_metrics_btn")):
        result = api_call("GET", "/api/metrics")
        if result and result.get("success"):
            mdata = result["data"]
            # Uptime and request counters
            m1, m2, m3 = st.columns(3)
            uptime_s = mdata.get("uptime_seconds", 0)
            hours = int(uptime_s // 3600)
            mins = int((uptime_s % 3600) // 60)
            m1.metric(t("uptime"), f"{hours}h {mins}m")

            counters = mdata.get("counters", {})
            m2.metric(t("total_requests"), counters.get("requests_total", 0))
            m3.metric(t("errors"), counters.get("errors_total", 0))

            # Pipeline counters
            if counters.get("ingest_total", 0) > 0:
                p1, p2, p3, p4 = st.columns(4)
                p1.metric(t("ingestions"), counters.get("ingest_total", 0))
                p2.metric(t("entities_extracted"), counters.get("entities_extracted_total", 0))
                p3.metric(t("events_extracted"), counters.get("events_extracted_total", 0))
                p4.metric(t("invalidated"), counters.get("invalidated_total", 0))

            # Search counters
            if counters.get("search_total", 0) > 0:
                s1, s2 = st.columns(2)
                s1.metric(t("searches"), counters.get("search_total", 0))
                s2.metric(t("results_returned"), counters.get("search_results_total", 0))

            # Latency stats
            timings = mdata.get("timings", {})
            if timings:
                st.markdown(f"**{t('latency_ms')}**")
                latency_rows = []
                for name, stats in sorted(timings.items()):
                    if stats:
                        latency_rows.append(
                            {
                                t("col_endpoint"): name,
                                t("col_count"): stats.get("count", 0),
                                t("col_avg"): stats.get("avg_ms", 0),
                                "P50": stats.get("p50_ms", 0),
                                "P95": stats.get("p95_ms", 0),
                                "Max": stats.get("max_ms", 0),
                            }
                        )
                if latency_rows:
                    st.dataframe(latency_rows, width="stretch")

    st.divider()

    # --- Export ---
    st.subheader(t("export_import"))

    col_exp, col_imp = st.columns(2)

    with col_exp:
        if st.button(t("export_btn")):
            with st.spinner(t("exporting")):
                result = api_call("GET", "/api/export")
                if result and result.get("success"):
                    export_data = result["data"]
                    export_json = json.dumps(export_data, indent=2, default=str)
                    st.download_button(
                        label=t("download_json_btn"),
                        data=export_json,
                        file_name="tkb_export.json",
                        mime="application/json",
                    )
                    st.success(
                        f"{t('entities')}: {len(export_data.get('entities', []))}, "
                        f"{t('events')}: {len(export_data.get('events', []))}, "
                        f"{t('episodes')}: {len(export_data.get('episodes', []))}"
                    )

    with col_imp:
        uploaded = st.file_uploader(t("import_json_label"), type=["json"], key="import_json")
        if uploaded is not None:
            try:
                import_data = json.loads(uploaded.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                st.error(t("invalid_json_file"))
                import_data = None

            if import_data:
                if import_data.get("version") != "1.0":
                    st.warning(t("unknown_version"))
                st.info(
                    f"{t('entities')}: {len(import_data.get('entities', []))}, "
                    f"{t('events')}: {len(import_data.get('events', []))}, "
                    f"{t('episodes')}: {len(import_data.get('episodes', []))}"
                )
                if st.button(t("confirm_import_btn")):
                    with st.spinner(t("importing")):
                        result = api_call("POST", "/api/import", json=import_data)
                        if result and result.get("success"):
                            counts = result["data"]
                            st.success(
                                t(
                                    "imported_counts",
                                    entities=counts.get("entities", 0),
                                    events=counts.get("events", 0),
                                    episodes=counts.get("episodes", 0),
                                    rels=counts.get("relationships", 0),
                                )
                            )

    st.divider()

    # --- Webhooks ---
    st.subheader(t("webhook_notifications"))
    st.caption(t("webhook_caption"))

    # Show existing webhooks
    wh_result = api_call("GET", "/api/webhooks")
    if wh_result and wh_result.get("success"):
        webhooks = wh_result["data"]
        if webhooks:
            for wh in webhooks:
                col_info, col_del = st.columns([4, 1])
                col_info.markdown(
                    f"**{wh.get('name', wh['url'])}** — `{wh['url']}`\n"
                    f"Events: {', '.join(wh.get('events', []))}"
                )
                if col_del.button(t("remove_btn"), key=f"rm_{wh['url']}"):
                    api_call("DELETE", f"/api/webhooks?url={wh['url']}")
                    st.rerun()
        else:
            st.info(t("no_webhooks"))

    # Add new webhook
    with st.expander(t("add_webhook")):
        wh_url = st.text_input(t("webhook_url_label"), placeholder="https://example.com/webhook")
        wh_name = st.text_input(t("webhook_name_label"), placeholder="Slack notification")
        if st.button(t("register_webhook_btn")):
            if wh_url:
                result = api_call("POST", "/api/webhooks", json={"url": wh_url, "name": wh_name})
                if result and result.get("success"):
                    st.success(t("webhook_registered", url=wh_url))
                    st.rerun()
            else:
                st.warning(t("enter_webhook_url"))

    st.divider()

    # --- Clear Database ---
    st.subheader(t("clear_database"))
    st.caption(t("clear_database_caption"))

    confirm_text = st.text_input(
        t("clear_confirm_text"), key="clear_db_confirm", placeholder="DELETE"
    )
    if st.button(t("clear_btn"), type="primary"):
        if confirm_text == "DELETE":
            with st.spinner(t("clearing_database")):
                result = api_call("POST", "/api/clear")
                if result and result.get("success"):
                    counts = result["data"]
                    st.success(
                        t(
                            "database_cleared",
                            nodes=counts.get("nodes", 0),
                            rels=counts.get("relationships", 0),
                        )
                    )
        else:
            st.warning(t("clear_confirm_wrong"))
