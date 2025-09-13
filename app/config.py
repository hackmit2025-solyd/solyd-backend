from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import quote_plus


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

    # App
    app_name: str = "Medical Knowledge Graph"
    app_version: str = "0.1.0"
    debug: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
