import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock
from typing import Generator
import os

# Set test environment
os.environ["TESTING"] = "true"

from app.main import app
from app.db.neo4j import Neo4jConnection
from app.services.ingestion import IngestionService
from app.services.extraction import ExtractionService
from app.services.resolution import ResolutionService
from app.services.query import QueryService


@pytest.fixture
def client() -> Generator:
    """Create test client"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j connection"""
    mock = Mock(spec=Neo4jConnection)
    mock.execute_query = MagicMock(return_value=[])
    mock.execute_write = MagicMock(
        return_value={
            "nodes_created": 0,
            "relationships_created": 0,
            "properties_set": 0,
        }
    )
    mock.test_connection = MagicMock(return_value=True)
    return mock


@pytest.fixture
def mock_claude_client():
    """Mock Claude API client"""
    mock = MagicMock()
    mock.messages.create = MagicMock(
        return_value=MagicMock(
            content=[
                MagicMock(
                    text='{"entities": {"patients": [{"id": "P123", "name": "Test Patient"}]}, "assertions": []}'
                )
            ]
        )
    )
    return mock


@pytest.fixture
def ingestion_service():
    """Create ingestion service"""
    return IngestionService()


@pytest.fixture
def extraction_service(mock_claude_client):
    """Create extraction service with mocked Claude"""
    service = ExtractionService()
    service.client = mock_claude_client
    return service


@pytest.fixture
def resolution_service(mock_neo4j):
    """Create resolution service with mocked Neo4j"""
    return ResolutionService(mock_neo4j)


@pytest.fixture
def query_service(mock_neo4j):
    """Create query service with mocked Neo4j"""
    return QueryService(mock_neo4j)


@pytest.fixture
def sample_patient():
    """Sample patient data"""
    return {
        "id": "P123",
        "dob": "1980-01-15",
        "sex": "M",
        "age": 44,
        "de_identified": True,
    }


@pytest.fixture
def sample_encounter():
    """Sample encounter data"""
    return {
        "id": "E567",
        "date": "2025-09-13",
        "dept": "Internal Medicine",
        "reason": "Fever and myalgia",
    }


@pytest.fixture
def sample_symptom():
    """Sample symptom data"""
    return {"name": "fever", "code": "SNOMED:386661006", "coding_system": "SNOMED"}


@pytest.fixture
def sample_disease():
    """Sample disease data"""
    return {"code": "ICD10:J10", "name": "Influenza", "status": "suspected"}


@pytest.fixture
def sample_document():
    """Sample document for testing"""
    return {
        "source_id": "test_doc_001",
        "source_type": "EMR",
        "title": "Test EMR Note",
        "content": "Patient John Doe (P123) reported fever and myalgia since yesterday. He denies cough. CRP test was performed.",
    }


@pytest.fixture
def sample_chunk():
    """Sample chunk data"""
    return {
        "chunk_id": "C1",
        "seq": 1,
        "text": "Patient John Doe (P123) reported fever and myalgia since yesterday.",
    }


@pytest.fixture
def sample_extraction_result():
    """Sample extraction result"""
    return {
        "entities": {
            "patients": [{"id": "P123", "name": "John Doe"}],
            "encounters": [{"id": "E567", "date": "2025-09-13", "dept": "IM"}],
            "symptoms": [
                {"name": "fever", "code": "SNOMED:386661006"},
                {"name": "myalgia", "code": "SNOMED:68962001"},
            ],
        },
        "assertions": [
            {
                "id": "A1",
                "predicate": "HAS_SYMPTOM",
                "subject_ref": "E567",
                "object_ref": "fever",
                "confidence": 0.95,
                "negation": False,
                "chunk_ids": ["C1"],
            }
        ],
    }


@pytest.fixture(scope="function")
def setup_test_neo4j():
    """Setup test Neo4j connection for all tests"""
    mock_neo4j = Mock(spec=Neo4jConnection)
    mock_neo4j.execute_query = MagicMock(return_value=[])
    mock_neo4j.execute_write = MagicMock(
        return_value={
            "nodes_created": 0,
            "relationships_created": 0,
            "properties_set": 0,
        }
    )
    mock_neo4j.test_connection = MagicMock(return_value=True)
    mock_neo4j.close = MagicMock()

    # Patch the app state neo4j
    app.state.neo4j = mock_neo4j
    return mock_neo4j
