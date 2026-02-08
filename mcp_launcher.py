#!/usr/bin/env python3
"""Ultra-fast MCP launcher for temporal-kb.

Starts a minimal stdio JSON-RPC proxy that responds to initialize/tools/list
instantly, then lazy-loads the real FastMCP server for tool calls.
This prevents Claude Code health-check timeouts for heavy MCP servers.
"""

import json
import sys
import threading


def _read_message():
    """Read a JSON-RPC message from stdin (newline-delimited)."""
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())


def _write_message(msg):
    """Write a JSON-RPC message to stdout."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


# Tool definitions (static, no imports needed)
TOOLS = [
    {
        "name": "tkb_ingest",
        "description": (
            "Add an episode to the temporal knowledge graph.\n\n"
            "Runs the full 5-stage pipeline: chunk → extract entities/events →\n"
            "resolve → store in Neo4j → run invalidation agent.\n\n"
            "If file_path is provided, extracts content from the document via Docling\n"
            "(supports PDF, DOCX, PPTX, XLSX, HTML, TXT, MD).\n\n"
            "Args:\n"
            "    content: Text content to ingest (optional if file_path is provided)\n"
            "    source: Source identifier (e.g. document name, URL)\n"
            "    episode_type: One of: text, json, chat, document\n"
            "    reference_time: ISO datetime when the content was created (optional)\n"
            "    group_id: Group/namespace for organizing episodes (optional)\n"
            "    file_path: Path to a local document file to extract and ingest (optional)"
        ),
        "inputSchema": {
            "properties": {
                "content": {"default": "", "type": "string"},
                "source": {"default": "manual", "type": "string"},
                "episode_type": {"default": "text", "type": "string"},
                "reference_time": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                },
                "group_id": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
                "file_path": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
            },
            "type": "object",
        },
    },
    {
        "name": "tkb_search",
        "description": (
            "Search the temporal knowledge graph for facts.\n\n"
            "Supports three search intents:\n"
            "- structural: relationships and structure\n"
            "- temporal: changes over time\n"
            "- hybrid: both combined (default)\n\n"
            "Args:\n"
            "    query: Natural language search query\n"
            "    intent: Search intent - structural, temporal, or hybrid\n"
            "    point_in_time: ISO datetime for point-in-time snapshot (optional)\n"
            "    limit: Maximum number of results (default 10)"
        ),
        "inputSchema": {
            "properties": {
                "query": {"type": "string"},
                "intent": {"default": "hybrid", "type": "string"},
                "point_in_time": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
                "limit": {"default": 10, "type": "integer"},
            },
            "required": ["query"],
            "type": "object",
        },
    },
    {
        "name": "tkb_ask",
        "description": (
            "Ask a question and get an LLM-generated answer grounded in the knowledge graph.\n\n"
            "Automatically extracts temporal references from the question\n"
            "(e.g. '2023', 'в январе 2024', 'January 2025') and uses them\n"
            "as point-in-time filters for more accurate results.\n\n"
            "Performs search + temporal verification + LLM response generation.\n"
            "Only uses verified, current facts for the answer.\n\n"
            "Args:\n"
            "    question: Natural language question\n"
            "    include_timeline: Include chronological timeline in response"
        ),
        "inputSchema": {
            "properties": {
                "question": {"type": "string"},
                "include_timeline": {"default": False, "type": "boolean"},
            },
            "required": ["question"],
            "type": "object",
        },
    },
    {
        "name": "tkb_timeline",
        "description": (
            "Get the full timeline of events mentioning an entity.\n\n"
            "Shows all temporal events (current and superseded) in chronological order.\n\n"
            "Args:\n"
            "    entity_id: ID of the entity to get timeline for"
        ),
        "inputSchema": {
            "properties": {"entity_id": {"type": "string"}},
            "required": ["entity_id"],
            "type": "object",
        },
    },
    {
        "name": "tkb_evolution",
        "description": (
            "Get the SUPERSEDED_BY chain showing how a fact evolved over time.\n\n"
            "Follows the chain from the given event through all its supersessions.\n\n"
            "Args:\n"
            "    event_id: ID of the starting temporal event"
        ),
        "inputSchema": {
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
            "type": "object",
        },
    },
    {
        "name": "tkb_stats",
        "description": (
            "Get statistics about the temporal knowledge graph.\n\n"
            "Returns counts of entities, temporal events, current events, and episodes."
        ),
        "inputSchema": {"properties": {}, "type": "object"},
    },
]


SERVER_INFO = {
    "name": "TemporalKnowledgeBase",
    "version": "1.0.0",
}

# The real FastMCP server (loaded lazily in background)
_real_server_proc = None
_real_server_ready = threading.Event()


def _start_real_server():
    """Start the real FastMCP server in a subprocess for tool/call delegation."""
    import os
    import subprocess

    global _real_server_proc
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    _real_server_proc = subprocess.Popen(
        [sys.executable, "mcp_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    # Send initialize to the real server
    init_msg = {
        "jsonrpc": "2.0",
        "id": "__init__",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "launcher", "version": "1.0"},
        },
    }
    _real_server_proc.stdin.write((json.dumps(init_msg) + "\n").encode())
    _real_server_proc.stdin.flush()
    # Read initialize response
    _real_server_proc.stdout.readline()
    # Send initialized notification
    notif = {"jsonrpc": "2.0", "id": "__notif__", "method": "notifications/initialized"}
    _real_server_proc.stdin.write((json.dumps(notif) + "\n").encode())
    _real_server_proc.stdin.flush()
    # Consume notification response (may be error, that's ok)
    _real_server_proc.stdout.readline()
    _real_server_ready.set()


def _delegate_to_real_server(msg):
    """Forward a request to the real FastMCP server and return its response."""
    if not _real_server_ready.is_set():
        _real_server_ready.wait(timeout=30)
    if _real_server_proc is None or _real_server_proc.poll() is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "error": {"code": -32603, "message": "Backend server not available"},
        }
    _real_server_proc.stdin.write((json.dumps(msg) + "\n").encode())
    _real_server_proc.stdin.flush()
    line = _real_server_proc.stdout.readline()
    if not line:
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "error": {"code": -32603, "message": "Backend server closed"},
        }
    return json.loads(line.decode())


def main():
    # Start real server in background thread
    t = threading.Thread(target=_start_real_server, daemon=True)
    t.start()

    while True:
        msg = _read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {"listChanged": False},
                        },
                        "serverInfo": SERVER_INFO,
                    },
                }
            )

        elif method == "notifications/initialized":
            # No response needed for notifications
            pass

        elif method == "tools/list":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"tools": TOOLS},
                }
            )

        elif method == "tools/call":
            # Delegate to real server
            resp = _delegate_to_real_server(msg)
            _write_message(resp)

        elif method == "ping":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {},
                }
            )

        else:
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


if __name__ == "__main__":
    main()
