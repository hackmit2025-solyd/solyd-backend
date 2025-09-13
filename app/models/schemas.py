from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# Request/Response Schemas
class DocumentUpload(BaseModel):
    source_id: str
    source_type: str
    title: Optional[str] = None
    content: str


class ChunkData(BaseModel):
    chunk_id: str
    seq: int
    text: str


class ExtractionRequest(BaseModel):
    source: DocumentUpload
    chunks: List[ChunkData]


class ExtractionResult(BaseModel):
    entities: Dict[str, List[Dict[str, Any]]]
    assertions: List[Dict[str, Any]]


class EntityResolutionRequest(BaseModel):
    entity_type: str
    entity_data: Dict[str, Any]


class EntityResolutionResult(BaseModel):
    entity: str
    decision: str  # "match", "new", "abstain"
    to_node_id: Optional[str] = None
    score: float


class GraphQuery(BaseModel):
    query: str
    parameters: Optional[Dict[str, Any]] = None


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    response: str
    graph_path: Optional[List[Dict[str, Any]]] = None
    evidence: Optional[List[Dict[str, Any]]] = None
    session_id: str


class SubgraphRequest(BaseModel):
    node_id: str
    depth: int = 2
    relationship_types: Optional[List[str]] = None


class SubgraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    center_node: str
