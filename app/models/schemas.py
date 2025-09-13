from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


# Request/Response Schemas
class DocumentUpload(BaseModel):
    """Document upload model for ingestion"""
    source_id: str = Field(..., description="Unique identifier for the document source", example="EMR-001")
    source_type: str = Field(..., description="Type of medical document", example="EMR")
    title: Optional[str] = Field(None, description="Document title", example="Patient Visit Record")
    content: str = Field(..., description="Full text content of the document", min_length=1)


class ChunkData(BaseModel):
    """Text chunk for processing"""
    chunk_id: str = Field(..., description="Unique chunk identifier", example="C1")
    seq: int = Field(..., description="Sequence number of chunk", ge=0, example=0)
    text: str = Field(..., description="Chunk text content", min_length=1)


class ExtractionRequest(BaseModel):
    """Request for entity extraction from chunks"""
    source: DocumentUpload = Field(..., description="Source document information")
    chunks: List[ChunkData] = Field(..., description="List of text chunks to process")


class ExtractionResult(BaseModel):
    """Result of entity extraction"""
    entities: Dict[str, List[Dict[str, Any]]] = Field(
        ...,
        description="Extracted entities grouped by type",
        example={"patients": [{"id": "P123", "name": "John Doe"}], "symptoms": [{"name": "fever"}]}
    )
    assertions: List[Dict[str, Any]] = Field(
        ...,
        description="Relationships between entities",
        example=[{"predicate": "HAS_SYMPTOM", "subject_ref": "E567", "object_ref": "fever"}]
    )


class EntityResolutionRequest(BaseModel):
    """Request for entity resolution"""
    entity_type: str = Field(..., description="Type of entity to resolve", example="patient")
    entity_data: Dict[str, Any] = Field(..., description="Entity attributes for matching")


class EntityResolutionResult(BaseModel):
    """Result of entity resolution"""
    entity: str = Field(..., description="Resolved entity identifier")
    decision: Literal["match", "new", "abstain"] = Field(..., description="Resolution decision")
    to_node_id: Optional[str] = Field(None, description="Matched node ID if found")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score")


class GraphQuery(BaseModel):
    """Cypher query request"""
    query: str = Field(..., description="Cypher query string", example="MATCH (p:Patient) RETURN p LIMIT 10")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Query parameters")


class ChatMessage(BaseModel):
    """Chat message model"""
    role: Literal["user", "assistant"] = Field(..., description="Message sender role")
    content: str = Field(..., description="Message content", min_length=1)
    timestamp: datetime = Field(default_factory=datetime.now, description="Message timestamp")


class ChatRequest(BaseModel):
    """Chat interaction request"""
    message: str = Field(..., description="User message", min_length=1, example="What symptoms did the patient have?")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for the query")


class ChatResponse(BaseModel):
    """Chat interaction response"""
    response: str = Field(..., description="Assistant's response")
    graph_path: Optional[List[Dict[str, Any]]] = Field(None, description="Relevant graph traversal path")
    evidence: Optional[List[Dict[str, Any]]] = Field(None, description="Supporting evidence from graph")
    session_id: str = Field(..., description="Session identifier")


class SubgraphRequest(BaseModel):
    """Request for subgraph extraction"""
    node_id: str = Field(..., description="Center node identifier", example="P123")
    depth: int = Field(2, ge=1, le=5, description="Maximum traversal depth")
    relationship_types: Optional[List[str]] = Field(
        None,
        description="Filter by relationship types",
        example=["HAS_SYMPTOM", "DIAGNOSED_AS"]
    )


class SubgraphResponse(BaseModel):
    """Subgraph extraction response"""
    nodes: List[Dict[str, Any]] = Field(..., description="List of nodes in subgraph")
    relationships: List[Dict[str, Any]] = Field(..., description="List of relationships in subgraph")
    center_node: str = Field(..., description="Center node ID")
