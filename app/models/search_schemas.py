"""Schemas for search API"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Natural language search request"""
    query: str = Field(..., description="Natural language query", min_length=1)
    limit: Optional[int] = Field(50, description="Maximum number of results")


class CypherResponse(BaseModel):
    """Response containing generated Cypher query"""
    cypher: str = Field(..., description="Generated Cypher query")
    entity_mappings: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Mapping of extracted entities to database UUIDs"
    )
    validation_status: str = Field(..., description="Query validation status")


class EntityMatch(BaseModel):
    """Entity match result from full-text search"""
    original_text: str = Field(..., description="Original text from query")
    matched_entity: Dict[str, Any] = Field(..., description="Matched entity from database")
    uuid: str = Field(..., description="UUID of matched entity")
    score: float = Field(..., description="Match confidence score (0-1)")
    match_type: str = Field(..., description="Type of match (exact, fuzzy, partial)")


class SearchResponse(BaseModel):
    """Natural language search response"""
    results: List[Dict[str, Any]] = Field(..., description="Query results")
    cypher_used: str = Field(..., description="Cypher query that was executed")
    entity_mappings: Dict[str, EntityMatch] = Field(
        default_factory=dict,
        description="Entity mappings used in query"
    )
    execution_time_ms: Optional[float] = Field(None, description="Query execution time")
    result_count: int = Field(..., description="Number of results returned")


class ErrorResponse(BaseModel):
    """Error response for search failures"""
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Detailed error information")
    suggested_query: Optional[str] = Field(None, description="Suggested alternative query")