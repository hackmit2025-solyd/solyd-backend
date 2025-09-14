from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App info
    app_name: str = "Medical Knowledge Graph Backend"
    app_version: str = "0.1.0"

    # Neo4j database
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "test"

    # PostgreSQL
    postgres_url: str = "postgresql://postgres:postgres@localhost:5432/medical_kg"

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Chunking settings
    chunk_size: int = 1000  # characters per chunk
    chunk_overlap: int = 200  # overlap between chunks

    # Embedding settings (VoyageAI)
    voyage_api_key: str = ""
    voyage_model: str = "voyage-3.5"
    embedding_dimension: int = 1024  # voyage-3.5 dimension

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
