from pydantic import BaseModel, Field


# Request/Response Schemas
class DocumentUpload(BaseModel):
    """Document upload model for ingestion"""

    text: str = Field(
        ..., description="Full text content of the document", min_length=1
    )
