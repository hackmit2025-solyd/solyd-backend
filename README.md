# Medical Knowledge Graph Backend

A comprehensive graph-based medical knowledge system that integrates patient data, medical literature, and clinical guidelines using Neo4j, LLMs, and advanced medical ontologies.

## Features

### Core Capabilities
- **Graph Database**: Neo4j-based knowledge graph for medical entities and relationships
- **Entity Extraction**: LLM-powered extraction with JSON schema validation and auto-repair
- **Medical Ontology Mapping**: Integration with ICD-10, SNOMED CT, LOINC, and RxNorm
- **Smart Querying**: Natural language to Cypher query conversion with injection prevention
- **Chat Interface**: Medical Q&A with graph-based evidence and context
- **Progressive Visualization**: Scalable graph rendering with clustering and filtering

### Advanced Features
- **OCR Processing**: AWS Textract integration for medical document digitization
- **Conflict Resolution**: Bi-temporal versioning with automated and human-in-the-loop resolution
- **Medical Normalization**: Standardized units, dosages, and date formats
- **Document Processing**: Apache Tika for PDF/Word extraction with S3 integration
- **Session Management**: Redis-based sessions with conflict storage
- **Batch Processing**: Optimized graph writes with Neo4j UNWIND

## Tech Stack

- **FastAPI**: Async web framework
- **Neo4j**: Graph database for relationships
- **PostgreSQL + pgvector**: Document storage and semantic search
- **Redis**: Session and cache management
- **Claude API**: Entity extraction and query generation
- **AWS Textract**: Medical document OCR
- **BioPortal API**: Medical ontology services
- **Apache Tika**: Document parsing
- **Python 3.11+**: Runtime

## Installation

1. Clone the repository
2. Install dependencies with uv:
```bash
uv sync
```

3. Set up environment variables in `.env`:
```env
# Core Databases
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres

# API Keys
ANTHROPIC_API_KEY=your-api-key-here
VOYAGE_API_KEY=your-voyage-key-here  # For embeddings
BIOPORTAL_API_KEY=your-bioportal-key  # For medical ontologies

# AWS Services (for OCR and S3)
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-medical-docs-bucket

# Redis (optional - falls back to memory if not provided)
REDIS_URL=redis://localhost:6379
```

## Quick Start

Run all services with:
```bash
./run.sh
```

Or manually:

1. Start databases:
```bash
docker-compose up -d
```

2. Initialize Neo4j schema:
```bash
uv run python -m app.db.init_schema
```

3. Start the API server:
```bash
uv run fastapi dev app/main.py
```

The API will be available at http://localhost:8000

## API Endpoints

### Graph Operations
- `GET /api/graph/patient/{patient_id}` - Get patient summary
- `GET /api/graph/encounter/{encounter_id}` - Get encounter details
- `POST /api/graph/subgraph` - Get subgraph around a node
- `GET /api/graph/path/{start_id}/{end_id}` - Find path between nodes
- `POST /api/graph/search/symptoms` - Search diseases by symptoms
- `POST /api/graph/query` - Execute custom Cypher query

### Data Ingestion
- `POST /api/ingest/document` - Upload and process a document
- `POST /api/ingest/file` - Upload a file for processing
- `POST /api/ingest/extract` - Extract entities from text
- `POST /api/ingest/bulk` - Bulk document upload

### Chat Interface
- `POST /api/chat/message` - Send chat message
- `GET /api/chat/session/{session_id}` - Get session history
- `WS /api/chat/ws/{session_id}` - WebSocket chat
- `POST /api/chat/query-to-cypher` - Convert natural language to Cypher

### Visualization
- `GET /api/visualization/overview` - Graph statistics
- `GET /api/visualization/recent-encounters` - Recent encounters
- `GET /api/visualization/disease-network/{disease_code}` - Disease network
- `GET /api/visualization/symptom-cooccurrence` - Symptom co-occurrence
- `GET /api/visualization/patient-timeline/{patient_id}` - Patient timeline
- `GET /api/visualization/graph-data` - Full graph data

### Progressive Graph Rendering
- `POST /api/graph/progressive/{start_node}` - Get initial graph with expansion capability
- `POST /api/graph/expand` - Expand graph from specific node
- `POST /api/graph/filter` - Filter graph by criteria
- `POST /api/graph/cluster/{node_id}` - Get node clusters (similar/temporal/structural)
- `GET /api/graph/conflicts/{node_id}` - Detect conflicting data

### Conflict Resolution
- `GET /api/conflicts` - List unresolved conflicts
- `GET /api/conflicts/{conflict_id}` - Get conflict details
- `POST /api/conflicts/{conflict_id}/resolve` - Resolve a conflict
- `POST /api/conflicts/auto-resolve` - Attempt automatic resolution
- `POST /api/conflicts/{conflict_id}/defer` - Defer conflict for later

## Graph Schema

### Nodes
- **Patient** (id, dob, sex, name)
- **Encounter** (id, date, dept, reason)
- **Symptom** (name, code, system, severity, onset)
- **Disease** (code, name, system, status)
- **Test** (name, loinc, category)
- **TestResult** (id, value, unit, time, flag)
- **Medication** (code, name, system, dose, route, frequency)
- **Procedure** (code, name, cpt)
- **Clinician** (id, name, specialty, npi)
- **SourceDocument** (source_id, source_type, title, created_at)
- **Assertion** (assertion_id, predicate, confidence, negation, uncertainty, valid_from, valid_to)
- **OntologyTerm** (system, code, name, synonyms, category)
- **ExternalResource** (resource_type, url, title, description)

### Relationships
- Patient → HAS_ENCOUNTER → Encounter
- Encounter → HAS_SYMPTOM → Symptom
- Encounter → DIAGNOSED_AS → Disease
- Encounter → ORDERED_TEST → Test
- Test → YIELDED → TestResult
- Encounter → PRESCRIBED → Medication
- Encounter → PERFORMED → Procedure
- Encounter → TREATED_BY → Clinician
- Assertion → EVIDENCED_BY → SourceDocument
- Entity → MAPPED_TO → OntologyTerm
- Entity → REFERENCES → ExternalResource
- Patient → REFERRED_TO → Clinician
- Patient → ALLERGIC_TO → Medication
- Medication → CONTRAINDICATED → Disease

## Development

### Code Quality
```bash
# Format code
uv run ruff format app/

# Check linting
uv run ruff check app/ --fix
```

### Testing
```bash
# Run tests (to be implemented)
uv run pytest
```

## License

MIT