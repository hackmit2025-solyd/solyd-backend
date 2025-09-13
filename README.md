# Medical Knowledge Graph Backend

A graph-based medical knowledge system that integrates patient data, medical literature, and clinical guidelines using Neo4j and LLMs.

## Features

- **Graph Database**: Neo4j-based knowledge graph for medical entities and relationships
- **Entity Extraction**: LLM-powered extraction of medical entities from unstructured text
- **Smart Querying**: Natural language to Cypher query conversion
- **Chat Interface**: Medical Q&A with graph-based evidence
- **Visualization**: Graph data APIs for frontend visualization

## Tech Stack

- **FastAPI**: Web framework
- **Neo4j**: Graph database
- **PostgreSQL**: Document storage
- **Claude API**: LLM integration
- **Python 3.11+**: Runtime

## Installation

1. Clone the repository
2. Install dependencies with uv:
```bash
uv sync
```

3. Set up environment variables in `.env`:
```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres
ANTHROPIC_API_KEY=your-api-key-here
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

## Graph Schema

### Nodes
- Patient (id, dob, sex)
- Encounter (id, date, dept)
- Symptom (name, code, coding_system)
- Disease (code, name, status)
- Test (name, loinc, category)
- TestResult (id, value, unit, time)
- Medication (code, name, form)
- SourceDocument (source_id, source_type, title)
- Assertion (assertion_id, predicate, confidence)

### Relationships
- Patient ’ HAS_ENCOUNTER ’ Encounter
- Encounter ’ HAS_SYMPTOM ’ Symptom
- Encounter ’ DIAGNOSED_AS ’ Disease
- Encounter ’ ORDERED_TEST ’ Test
- Test ’ YIELDED ’ TestResult
- Encounter ’ PRESCRIBED ’ Medication
- Assertion ’ EVIDENCED_BY ’ SourceDocument

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