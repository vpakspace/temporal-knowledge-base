"""Integration tests for OpenAI API — embeddings and LLM generation.

Tests real API calls to verify:
- Embedding generation (single + batch)
- LLM text generation
- JSON structured output
- Intent classification
- Contradiction detection
"""

from __future__ import annotations

import pytest

from generation.llm_client import LLMClient
from storage.vector_store import VectorStore
from tests.conftest import skip_no_openai

pytestmark = [pytest.mark.integration, skip_no_openai]


# --- Embeddings ---


async def test_embed_single_text(vector_store: VectorStore):
    embedding = await vector_store.embed_text("Temporal knowledge graph")
    assert isinstance(embedding, list)
    assert len(embedding) == 1536
    assert all(isinstance(v, float) for v in embedding)


async def test_embed_batch(vector_store: VectorStore):
    texts = [
        "Alice is CEO of Acme.",
        "Bob works as CTO at TechCo.",
        "Revenue increased to $10M.",
    ]
    embeddings = await vector_store.embed_batch(texts)
    assert len(embeddings) == 3
    for emb in embeddings:
        assert len(emb) == 1536


async def test_embed_empty_batch(vector_store: VectorStore):
    result = await vector_store.embed_batch([])
    assert result == []


async def test_similar_texts_have_high_similarity(vector_store: VectorStore):
    emb_a = await vector_store.embed_text("Apple Inc. is a technology company.")
    emb_b = await vector_store.embed_text("Apple is a tech corporation.")
    emb_c = await vector_store.embed_text("The weather is sunny today.")

    sim_ab = VectorStore.cosine_similarity(emb_a, emb_b)
    sim_ac = VectorStore.cosine_similarity(emb_a, emb_c)

    # Similar sentences should have higher similarity
    assert sim_ab > 0.8, f"Similar texts similarity too low: {sim_ab}"
    assert sim_ac < sim_ab, f"Unrelated text similarity should be lower"


# --- LLM Generation ---


async def test_generate_text(llm_client: LLMClient):
    response = await llm_client.generate(
        "What is 2 + 2? Reply with just the number.",
        system="You are a helpful math assistant. Reply concisely.",
    )
    assert "4" in response


async def test_generate_json(llm_client: LLMClient):
    result = await llm_client.generate_json(
        'Extract the person name and role from: "Alice is the CEO of Acme Corp."',
        system='Respond in JSON with keys: "name", "role", "company".',
    )
    assert isinstance(result, dict)
    assert "name" in result
    assert result["name"].lower() == "alice"


# --- Intent Classification ---


async def test_classify_structural_intent(llm_client: LLMClient):
    intent = await llm_client.classify_intent("Who works for Acme Corporation?")
    assert intent == "structural"


async def test_classify_temporal_intent(llm_client: LLMClient):
    intent = await llm_client.classify_intent("What changed at Acme in 2024?")
    assert intent == "temporal"


async def test_classify_hybrid_intent(llm_client: LLMClient):
    intent = await llm_client.classify_intent(
        "Who was CEO when the company revenue peaked?"
    )
    assert intent in ("hybrid", "temporal")


# --- Contradiction Detection ---


async def test_contradiction_detected(llm_client: LLMClient):
    result = await llm_client.check_contradiction(
        existing_fact="Alice is the CEO of Acme Corporation.",
        new_fact="Bob was appointed as the new CEO of Acme Corporation, replacing Alice.",
    )
    assert isinstance(result, dict)
    assert result.get("contradicts") is True
    assert "severity" in result


async def test_no_contradiction(llm_client: LLMClient):
    result = await llm_client.check_contradiction(
        existing_fact="Acme Corporation has 500 employees.",
        new_fact="Acme Corporation opened a new office in Berlin.",
    )
    assert isinstance(result, dict)
    assert result.get("contradicts") is False
