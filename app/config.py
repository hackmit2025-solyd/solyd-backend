from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App info
    app_name: str = "Medical Knowledge Graph Backend"
    app_version: str = "0.1.0"

    # Neo4j database
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "test"

    # PostgreSQL (keeping minimal for potential future use)
    postgres_url: Optional[str] = None

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
