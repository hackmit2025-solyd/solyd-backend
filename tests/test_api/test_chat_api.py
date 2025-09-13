import pytest
import json
from unittest.mock import MagicMock, patch


class TestChatAPI:
    def test_send_message(self, client, setup_test_neo4j):
        """Test POST /api/chat/message"""
        with patch("app.api.chat.ChatService") as mock_chat_service:
            mock_instance = mock_chat_service.return_value
            mock_instance.generate_response.return_value = {
                "response": "Based on the graph, fever is a common symptom.",
                "graph_path": [{"node": "fever", "type": "Symptom"}],
                "evidence": [{"source": "EMR", "confidence": 0.95}],
            }
            mock_instance.sessions = {}
            
            response = client.post(
                "/api/chat/message",
                json={"message": "What is fever?", "session_id": "test_session"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "response" in data
            assert "graph_path" in data
            assert "session_id" in data

    def test_send_message_without_session(self, client):
        """Test POST /api/chat/message without session ID"""
        with patch("app.api.chat.ChatService") as mock_chat_service:
            mock_instance = mock_chat_service.return_value
            mock_instance.generate_response.return_value = {
                "response": "Test response",
                "graph_path": [],
                "evidence": [],
            }
            mock_instance.sessions = {}
            
            response = client.post(
                "/api/chat/message",
                json={"message": "Test message"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["session_id"] is not None

    def test_get_session_history(self, client):
        """Test GET /api/chat/session/{session_id}"""
        with patch("app.api.chat.ChatService") as mock_chat_service:
            mock_instance = mock_chat_service.return_value
            mock_instance.sessions = {
                "test_session": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ]
            }
            
            response = client.get("/api/chat/session/test_session")
            
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == "test_session"
            assert len(data["messages"]) == 2
            assert data["messages"][0]["role"] == "user"

    def test_get_session_history_not_found(self, client):
        """Test GET /api/chat/session/{session_id} when not found"""
        with patch("app.api.chat.ChatService") as mock_chat_service:
            mock_instance = mock_chat_service.return_value
            mock_instance.sessions = {}
            
            response = client.get("/api/chat/session/nonexistent")
            
            assert response.status_code == 404

    def test_query_to_cypher(self, client):
        """Test POST /api/chat/query-to-cypher"""
        with patch("app.api.chat.ChatService") as mock_chat_service:
            mock_instance = mock_chat_service.return_value
            mock_instance.client = MagicMock()
            mock_instance.client.messages.create.return_value = MagicMock(
                content=[
                    MagicMock(
                        text="MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) RETURN p, e"
                    )
                ]
            )
            
            response = client.post(
                "/api/chat/query-to-cypher",
                json={"query": "Show me all patients and their encounters"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "cypher" in data
            assert "MATCH" in data["cypher"]
            assert data["natural_language"] == "Show me all patients and their encounters"

    def test_query_to_cypher_without_client(self, client):
        """Test POST /api/chat/query-to-cypher without Claude client"""
        with patch("app.api.chat.ChatService") as mock_chat_service:
            mock_instance = mock_chat_service.return_value
            mock_instance.client = None  # No API key
            
            response = client.post(
                "/api/chat/query-to-cypher",
                json={"query": "Show me all patients"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "cypher" in data
            assert data["explanation"] == "Mock Cypher query for testing"