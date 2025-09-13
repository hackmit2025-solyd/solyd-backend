from pydantic import BaseModel, Field
from typing import Optional, Dict

# Request/Response Schemas
class DocumentUpload(BaseModel):
    """Document upload model for ingestion"""

    source_id: str = Field(
        ..., description="Unique identifier for the document source", example="EMR-001"
    )
    source_type: str = Field(..., description="Type of medical document", example="EMR")
    text: str = Field(
        ..., description="Full text content of the document", min_length=1
    )