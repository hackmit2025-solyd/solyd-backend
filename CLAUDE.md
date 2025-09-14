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

# Run tests with verbose output
uv run pytest -v

# Run specific test function
uv run pytest tests/test_extraction.py::test_entity_extraction
```

### Database Management
```bash
# Start databases only
docker-compose up -d neo4j postgres

# View Neo4j browser
# Navigate to: http://localhost:7474
# Default credentials: neo4j/P@ssw0rd

# Connect to PostgreSQL
docker exec -it postgres psql -U postgres -d postgres

# Clear Neo4j database (CAUTION)
docker exec neo4j cypher-shell -u neo4j -p P@ssw0rd "MATCH (n) DETACH DELETE n"

# View Docker logs
docker-compose logs -f neo4j
docker-compose logs -f postgres
```

## Architecture Overview

### Core Service Architecture

The system implements a **Medical Knowledge Graph** with the following key architectural patterns:

1. **Dual Database Pattern**:
   - Neo4j for graph relationships and entity connections
   - PostgreSQL with pgvector for document storage and semantic search
   - Redis for session management and conflict caching (optional)

2. **Entity Extraction Pipeline**:
   ```
   Document → Chunking → LLM Extraction → Validation → Normalization → ID Generation → Graph Writing
   ```
   - Documents are chunked with overlap (app/services/chunking.py) - 1000 chars, 200 overlap
   - Entities extracted via Claude Sonnet (app/services/extraction.py)
   - Cross-chunk entity deduplication in _merge_chunk_extractions()
   - UUID-based node identification for consistency
   - Batch written to Neo4j with document_id tracking

3. **Natural Language Search System**:
   - Full-text indexes on Neo4j using Lucene
   - Fuzzy matching with Levenshtein distance
   - Entity extraction from queries → UUID mapping → Cypher generation
   - Two endpoints: `/api/search/query` (JSON) and `/api/search/query-graph` (nodes/edges)

4. **Graph Export & Visualization**:
   - `/api/graph/full` - Complete graph export with optional limit
   - `/api/graph/subgraph/{uuid}` - Node-centered subgraph with depth control
   - `/api/graph/statistics` - Graph metrics and counts
   - Node labeling via _determine_node_label() heuristics

### API Endpoint Structure

```
/api/
├── ingest/
│   ├── document    # Text document ingestion
│   └── pdf         # PDF file upload and processing
├── search/
│   ├── to-cypher   # Natural language → Cypher
│   ├── query       # Execute search (JSON results)
│   ├── query-graph # Execute search (graph format)
│   └── validate-cypher
└── graph/
    ├── full        # Export entire graph
    ├── subgraph/{uuid}
    └── statistics
```

### Critical Data Flow Patterns

1. **Document Ingestion with Chunking**:
   - Upload → Text extraction (PDF via PyPDF2)
   - Chunking with context passing between chunks
   - Parallel entity extraction per chunk
   - Cross-chunk entity deduplication
   - UUID generation and graph storage

2. **Query Processing**:
   - Natural language → Entity extraction
   - Full-text search for entity → UUID mapping
   - Cypher generation with UUID injection
   - Query validation via EXPLAIN
   - Result formatting (JSON or graph)

3. **Graph Query Transformation** (query-graph endpoint):
   - Cypher RETURN clause modification to return full nodes
   - Extraction of all MATCH pattern variables
   - Automatic inclusion of missing nodes in RETURN
   - Relationship querying between result nodes

### Environment Variables Required

```env
# Core databases
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=P@ssw0rd  # Docker default
POSTGRES_URL=postgresql://postgres:P@ssw0rd@localhost:5432/postgres

# APIs
ANTHROPIC_API_KEY=sk-xxx
VOYAGE_API_KEY=xxx  # For embeddings (voyage-3.5, 1024 dimensions)

# Optional services
BIOPORTAL_API_KEY=xxx  # Medical ontology mapping
AWS_ACCESS_KEY_ID=xxx  # For Textract OCR
AWS_SECRET_ACCESS_KEY=xxx
AWS_REGION=us-east-1
S3_BUCKET_NAME=medical-docs
REDIS_URL=redis://localhost:6379  # Optional, falls back to memory
```

### Key Service Patterns

- **Service Initialization**: Services created in endpoint dependencies via `get_services()`
- **Neo4j Connection**: Singleton in app.state.neo4j, accessed via `get_neo4j(request)`
- **Entity Matching**: EntityMatcher uses full-text indexes for fuzzy search
- **Cypher Generation**: CypherGenerator with retry logic and error fixing
- **ID Generation**: UUID-based with deterministic generation for duplicates
- **Batch Processing**: Uses UNWIND for efficient Neo4j writes

### Database Schema Considerations

**Neo4j Indexes** (created in init_schema.py):
- Full-text indexes for fuzzy search on each entity type
- Unique constraints on uuid properties
- Composite indexes for frequently queried patterns

**PostgreSQL Tables**:
- `documents`: Stores original text with UUID primary key
- `chunks`: Document chunks with embeddings (pgvector)
- Vector similarity search for semantic queries

### Model Configuration

- **Claude Model**: claude-3-5-sonnet-20241022 (settings.claude_model)
- **Embedding Model**: voyage-3.5 with 1024 dimensions
- **Extraction Temperature**: 0.3 for consistency
- **Token Limits**: 8192 max tokens for extraction

### Common Development Tasks

```bash
# Restart everything fresh
docker-compose down -v  # Remove volumes
./run.sh

# Debug entity extraction
uv run python -c "from app.services.extraction import ExtractionService; print(ExtractionService().extract_entities('Patient John Doe, 45 years old'))"

# Test natural language search
curl -X POST http://localhost:8000/api/search/query \
  -H "Content-Type: application/json" \
  -d '{"query": "patients with diabetes"}'

# View Neo4j graph
# Open http://localhost:7474
# Run: MATCH (n) RETURN n LIMIT 50
```

### Error Handling Patterns

- Services return empty results on failure (not exceptions)
- API endpoints use HTTPException for client errors
- Validation errors auto-repair via JSON schema
- Cypher errors retry with Claude-based fixing
- Full-text search falls back from fuzzy to partial matching