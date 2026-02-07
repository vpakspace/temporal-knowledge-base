"""Shared fixtures for integration tests.

Requires:
- Neo4j running at bolt://localhost:7687
- OPENAI_API_KEY set in .env or environment
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from core.config import AppSettings, Neo4jSettings, OpenAISettings
from generation.llm_client import LLMClient
from storage.neo4j_client import Neo4jClient
from storage.vector_store import VectorStore


def _neo4j_available() -> bool:
    """Check if Neo4j is reachable."""
    import socket

    try:
        sock = socket.create_connection(("localhost", 7687), timeout=2)
        sock.close()
        return True
    except OSError:
        return False


def _openai_available() -> bool:
    """Check if OpenAI API key is configured."""
    key = os.getenv("OPENAI_API_KEY", "")
    return bool(key and key.startswith("sk-"))


skip_no_neo4j = pytest.mark.skipif(
    not _neo4j_available(), reason="Neo4j not available at localhost:7687"
)

skip_no_openai = pytest.mark.skipif(
    not _openai_available(), reason="OPENAI_API_KEY not configured"
)


@pytest.fixture(scope="session")
def neo4j_settings() -> Neo4jSettings:
    return Neo4jSettings()


@pytest.fixture(scope="session")
def openai_settings() -> OpenAISettings:
    return OpenAISettings()


@pytest.fixture(scope="session")
def app_settings() -> AppSettings:
    return AppSettings()


@pytest_asyncio.fixture
async def neo4j_client(neo4j_settings: Neo4jSettings) -> Neo4jClient:
    """Fresh Neo4j client that cleans up test data after each test."""
    client = Neo4jClient(neo4j_settings)
    await client.connect()
    yield client
    # Cleanup: remove all test data
    async with client.session() as session:
        await session.run(
            "MATCH (n) WHERE n.id STARTS WITH 'test-' DETACH DELETE n"
        )
    await client.close()


@pytest_asyncio.fixture
async def neo4j_clean(neo4j_client: Neo4jClient) -> Neo4jClient:
    """Neo4j client with a completely clean graph (drops everything)."""
    async with neo4j_client.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    return neo4j_client


@pytest.fixture
def vector_store(openai_settings: OpenAISettings) -> VectorStore:
    return VectorStore(openai_settings)


@pytest.fixture
def llm_client(openai_settings: OpenAISettings) -> LLMClient:
    return LLMClient(openai_settings)
