from typing import Optional
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "P@ssw0rd"

    # PostgreSQL - URL encode the password with @ symbol
    postgres_url: str = (
        f"postgresql://postgres:{quote_plus('P@ssw0rd')}@localhost:5432/postgres"
    )

    # Claude API
    anthropic_api_key: Optional[str] = None

    # Voyage AI
    voyage_api_key: Optional[str] = None

    # AWS S3
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "medical-knowledge-graph"

    # BioPortal API
    bioportal_api_key: Optional[str] = None

    # Redis
    redis_url: Optional[str] = "redis://localhost:6379"

    # Model Configuration
    claude_model: str = "claude-sonnet-4-20250514"
    voyage_embedding_model: str = "voyage-3-large"
    embedding_dimension: int = 1024

    # Service Configuration
    max_retry_attempts: int = 3
    cache_ttl_seconds: int = 3600  # 1 hour
    session_max_messages: int = 100
    conflict_ttl_hours: int = 72

    # BioPortal Configuration
    bioportal_base_url: str = "https://data.bioontology.org"
    bioportal_min_match_length: int = 3

    # Document Processing
    tika_server_url: str = "http://localhost:9998"
    max_chunk_size: int = 1000  # characters
    chunk_overlap: int = 100  # characters

    # Batch Processing
    neo4j_batch_size: int = 100

    # App
    app_name: str = "Medical Knowledge Graph"
    app_version: str = "0.1.0"
    debug: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
