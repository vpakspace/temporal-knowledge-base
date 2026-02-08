"""Core data models for temporal knowledge base.

Implements the bi-temporal data model from GraphOS architecture:
- Entity Layer: structural graph (nodes + relationships)
- Temporal Event Layer: atomic temporal facts with valid_at/invalid_at
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

# --- Enums ---


class EpisodeType(str, Enum):
    """Type of episode being ingested."""

    TEXT = "text"
    JSON = "json"
    CHAT = "chat"
    DOCUMENT = "document"


class FactType(str, Enum):
    """Classification of temporal facts."""

    STATIC = "static"  # Rarely changes (e.g., date of birth)
    DYNAMIC = "dynamic"  # Changes over time (e.g., job title)
    ATEMPORAL = "atemporal"  # Not time-bound (e.g., mathematical truth)


class InvalidationMode(str, Enum):
    """How entity properties should be invalidated on update."""

    REPLACE = "replace"  # New value replaces old (e.g., CEO)
    ACCUMULATE = "accumulate"  # Values accumulate (e.g., skills list)
    VERSIONED = "versioned"  # Keep full version history


class DriftSeverity(str, Enum):
    """Severity of detected contradiction."""

    CRITICAL = "critical"  # Direct contradiction
    WARNING = "warning"  # Potential conflict
    INFO = "info"  # Minor update


class IntentType(str, Enum):
    """Query intent classification (GraphOS Layer 3)."""

    STRUCTURAL = "structural"  # "Who works for X?"
    TEMPORAL = "temporal"  # "What changed in 2024?"
    HYBRID = "hybrid"  # "Who was CEO when revenue peaked?"


# --- Core Models ---


class TemporalMetadata(BaseModel):
    """Bi-temporal metadata attached to nodes and edges."""

    valid_at: datetime | None = None  # When fact became true in reality
    invalid_at: datetime | None = None  # When fact was superseded
    expired_at: datetime | None = None  # When fact naturally expired
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))  # Transaction time
    is_current: bool = True
    source_episode_id: str | None = None


class Entity(BaseModel):
    """Node in the Entity Layer (structural graph)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    entity_type: str  # e.g., "Person", "Organization", "Product"
    canonical_name: str | None = None  # Resolved canonical form
    properties: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)
    invalidation_mode: InvalidationMode = InvalidationMode.REPLACE

    @property
    def display_name(self) -> str:
        return self.canonical_name or self.name


class Relationship(BaseModel):
    """Edge between entities in the Entity Layer."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    target_id: str
    relation_type: str  # e.g., "WORKS_FOR", "CEO_OF", "TREATS"
    properties: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    fact_type: FactType = FactType.DYNAMIC
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)


class TemporalEvent(BaseModel):
    """Atomic temporal fact in the Temporal Event Layer.

    Represents a single statement extracted from a source,
    with bi-temporal tracking and contradiction detection.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    statement: str  # The atomic fact as text
    fact_type: FactType = FactType.DYNAMIC
    entity_ids: list[str] = Field(default_factory=list)  # Referenced entities
    embedding: list[float] | None = None
    confidence: float = 1.0
    source: str | None = None
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)
    superseded_by: str | None = None  # ID of newer event that supersedes this one


class Episode(BaseModel):
    """A unit of information to be ingested into the knowledge graph.

    Episodes are the primary input mechanism (Graphiti's add_episode).
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    episode_type: EpisodeType = EpisodeType.TEXT
    source: str | None = None  # Document name, URL, etc.
    reference_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- Extraction Results ---


class ExtractionResult(BaseModel):
    """Result of dual-track extraction from an episode."""

    episode_id: str
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    temporal_events: list[TemporalEvent] = Field(default_factory=list)


# --- Invalidation ---


class InvalidationCandidate(BaseModel):
    """A pair of events where the new one may supersede the old."""

    existing_event: TemporalEvent
    new_event: TemporalEvent
    temporal_overlap: bool = False
    shared_entity_ids: list[str] = Field(default_factory=list)
    semantic_similarity: float = 0.0
    llm_confirmed: bool = False


class InvalidationResult(BaseModel):
    """Result of invalidation agent processing."""

    invalidated_events: list[str] = Field(default_factory=list)  # IDs
    supersede_pairs: list[tuple[str, str]] = Field(default_factory=list)  # (old_id, new_id)
    severity: DriftSeverity = DriftSeverity.INFO


# --- Search & Query ---


class SearchQuery(BaseModel):
    """Unified search query with temporal filtering."""

    query: str
    intent: IntentType = IntentType.HYBRID
    point_in_time: datetime | None = None  # For point-in-time snapshots
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    entity_types: list[str] | None = None
    limit: int = 10
    include_superseded: bool = False  # Include invalidated facts


class SearchResult(BaseModel):
    """A single search result with temporal context."""

    id: str
    content: str
    score: float = 0.0
    result_type: str = "entity"  # "entity", "relationship", "temporal_event"
    temporal: TemporalMetadata | None = None
    related_entities: list[str] = Field(default_factory=list)
    supersedes: str | None = None
    superseded_by: str | None = None


class SearchResponse(BaseModel):
    """Complete search response with timeline."""

    query: SearchQuery
    results: list[SearchResult] = Field(default_factory=list)
    timeline: list[TemporalEvent] | None = None
    total_count: int = 0
