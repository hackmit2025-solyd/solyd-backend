from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "test"
    
    # PostgreSQL
    postgres_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"
    
    # Claude API
    anthropic_api_key: Optional[str] = None
    
    # App
    app_name: str = "Medical Knowledge Graph"
    app_version: str = "0.1.0"
    debug: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()