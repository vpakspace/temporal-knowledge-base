"""Custom exceptions for temporal knowledge base."""


class TemporalKBError(Exception):
    """Base exception."""


class Neo4jConnectionError(TemporalKBError):
    """Failed to connect to Neo4j."""


class EpisodeProcessingError(TemporalKBError):
    """Error during episode ingestion."""


class EntityResolutionError(TemporalKBError):
    """Error resolving entity to canonical form."""


class InvalidationError(TemporalKBError):
    """Error during temporal invalidation."""


class ExtractionError(TemporalKBError):
    """Error extracting entities/events from text."""


class SearchError(TemporalKBError):
    """Error during search/retrieval."""


class TemporalQueryError(TemporalKBError):
    """Error in temporal query processing."""


class LLMError(TemporalKBError):
    """Error communicating with LLM."""


class EmbeddingError(TemporalKBError):
    """Error generating embeddings."""
