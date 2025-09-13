# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development
```bash
# Install dependencies
uv sync

# Run development server
uv run fastapi dev app/main.py --port 8000

# Initialize databases and schema
./run.sh  # Starts Docker containers and initializes Neo4j schema

# Manual database setup
docker-compose up -d
uv run python -m app.db.init_schema
```

### Code Quality
```bash
# Run linter and auto-fix
uv run ruff check app/ --fix

# Format code
uv run ruff format app/

# Check all code quality issues
uv run ruff check app/
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_extraction.py

# Run with coverage
uv run pytest --cov=app --cov-report=html
```

## Architecture Overview

### Core Service Architecture

The system implements a **Medical Knowledge Graph** with the following key architectural patterns:

1. **Dual Database Pattern**:
   - Neo4j for graph relationships and entity connections
   - PostgreSQL with pgvector for document storage and semantic search
   - Redis for session management and conflict caching

2. **Entity Extraction Pipeline**:
   ```
   Document → Chunking → LLM Extraction → Validation → Normalization → ID Generation → Graph Writing
   ```
   - Documents are chunked (app/services/chunking.py)
   - Entities extracted via Claude (app/services/extraction.py)
   - JSON validated with auto-repair (app/services/validation.py)
   - Medical data normalized (app/services/normalization.py)
   - Consistent IDs generated (app/services/id_generator.py)
   - Batch written to Neo4j (app/services/graph_writer.py)

3. **Ontology Mapping Strategy**:
   - Primary: BioPortal API for comprehensive medical codes (app/services/bioportal.py)
   - Fallback: Local SQLite cache with Claude-based selection (app/services/ontology.py)
   - Systems: ICD-10, SNOMED CT, LOINC, RxNorm

4. **Conflict Resolution System**:
   - Automatic resolution for timestamp-based conflicts
   - Human-in-the-loop for contradictory medical data
   - Bi-temporal model (valid_from/valid_to) for versioning

### Security Considerations

- **Cypher Injection Prevention**: All dynamic queries use whitelisted labels/properties (app/services/graph_writer.py)
- **Batch Processing**: Uses Neo4j UNWIND for safe bulk operations
- **S3 Integration**: Documents processed then deleted from temp storage

### External Service Dependencies

- **AWS Textract**: OCR for medical documents (requires AWS credentials)
- **BioPortal API**: Medical ontology mapping (requires API key)
- **Apache Tika**: PDF/Word document extraction (Java-based service)
- **Claude/Anthropic API**: Entity extraction and query generation

### Critical Data Flow Patterns

1. **Document Ingestion**:
   - Upload → S3 Storage → OCR/Text Extraction → Chunking → Entity Extraction → Graph Storage

2. **Query Processing**:
   - Natural Language → Claude → Cypher Query → Neo4j → Result Formatting

3. **Conflict Detection**:
   - New assertions compared against existing graph → Conflicts stored in Redis → API for resolution

4. **Progressive Graph Rendering**:
   - Initial node → Expandable detection → On-demand expansion → Clustering/Filtering

### Environment Variables Required

```env
# Core databases
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
POSTGRES_URL=postgresql://user:pass@localhost:5432/db

# APIs
ANTHROPIC_API_KEY=sk-xxx
BIOPORTAL_API_KEY=xxx
VOYAGE_API_KEY=xxx  # For embeddings

# AWS (for OCR and S3)
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_REGION=us-east-1
S3_BUCKET_NAME=medical-docs

# Redis (optional, falls back to memory)
REDIS_URL=redis://localhost:6379
```

### Key Service Patterns

- **Singleton Services**: Most services use singleton pattern (e.g., `ontology_mapper`, `id_generator`)
- **Dependency Injection**: FastAPI dependencies for Neo4j/PostgreSQL connections
- **Async Operations**: All database operations are async-ready
- **Batch Processing**: Graph writes optimized with UNWIND for 100+ entities

### Testing Strategy

- Unit tests for individual services (normalization, validation, ID generation)
- Integration tests for end-to-end pipelines
- Mock external services (Textract, BioPortal, Claude) in tests
- Use test fixtures for Neo4j/PostgreSQL data