from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from typing import Dict, List, Any, Optional
import json
import uuid
from datetime import datetime
from app.services.query import QueryService
from app.models.schemas import ChatRequest, ChatResponse
from app.config import settings
import anthropic

router = APIRouter()


class ChatService:
    def __init__(self, query_service: QueryService):
        self.query_service = query_service
        self.client = None
        if settings.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.sessions = {}  # In-memory session storage (use Redis in production)

    def generate_response(
        self, message: str, context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Generate response using Claude and graph data"""
        # Extract medical entities from the message
        entities = self._extract_entities_from_message(message)

        # Query graph for relevant information
        graph_context = self._get_graph_context(entities)

        # Generate response
        if self.client:
            response = self._generate_claude_response(message, graph_context)
        else:
            response = self._generate_mock_response(message, graph_context)

        return {
            "response": response["text"],
            "graph_path": graph_context.get("path", []),
            "evidence": graph_context.get("evidence", []),
            "entities": entities,
        }

    def _extract_entities_from_message(self, message: str) -> Dict[str, List[str]]:
        """Extract medical entities from chat message"""
        # Simple keyword extraction for MVP
        # In production, use NER or Claude for extraction

        entities = {"symptoms": [], "diseases": [], "medications": [], "tests": []}

        # Simple keyword matching (replace with proper NER)
        symptom_keywords = ["fever", "cough", "pain", "headache", "fatigue"]
        disease_keywords = ["diabetes", "hypertension", "influenza", "covid"]
        med_keywords = ["aspirin", "ibuprofen", "acetaminophen", "insulin"]
        test_keywords = ["CRP", "CBC", "glucose", "X-ray", "MRI"]

        message_lower = message.lower()

        for keyword in symptom_keywords:
            if keyword in message_lower:
                entities["symptoms"].append(keyword)

        for keyword in disease_keywords:
            if keyword in message_lower:
                entities["diseases"].append(keyword)

        for keyword in med_keywords:
            if keyword in message_lower:
                entities["medications"].append(keyword)

        for keyword in test_keywords:
            if keyword in message_lower:
                entities["tests"].append(keyword)

        return entities

    def _get_graph_context(self, entities: Dict[str, List[str]]) -> Dict[str, Any]:
        """Query graph for relevant context based on entities"""
        context = {"nodes": [], "relationships": [], "path": [], "evidence": []}

        # Query for symptoms
        if entities.get("symptoms"):
            symptom_query = """
            MATCH (s:Symptom)
            WHERE s.name IN $symptoms OR toLower(s.name) IN $symptoms
            OPTIONAL MATCH (s)<-[:HAS_SYMPTOM]-(e:Encounter)-[:DIAGNOSED_AS]->(d:Disease)
            RETURN s, collect(DISTINCT d) as related_diseases
            LIMIT 10
            """
            results = self.query_service.execute_custom_query(
                symptom_query, {"symptoms": entities["symptoms"]}
            )
            for result in results:
                context["nodes"].append(result.get("s"))
                context["nodes"].extend(result.get("related_diseases", []))

        # Query for diseases
        if entities.get("diseases"):
            disease_query = """
            MATCH (d:Disease)
            WHERE toLower(d.name) IN $diseases
            OPTIONAL MATCH (d)<-[:DIAGNOSED_AS]-(e:Encounter)
            OPTIONAL MATCH (e)-[:HAS_SYMPTOM]->(s:Symptom)
            OPTIONAL MATCH (e)-[:PRESCRIBED]->(m:Medication)
            RETURN d, collect(DISTINCT s) as symptoms, collect(DISTINCT m) as medications
            LIMIT 10
            """
            results = self.query_service.execute_custom_query(
                disease_query, {"diseases": entities["diseases"]}
            )
            for result in results:
                context["nodes"].append(result.get("d"))
                context["nodes"].extend(result.get("symptoms", []))
                context["nodes"].extend(result.get("medications", []))

        return context

    def _generate_claude_response(
        self, message: str, graph_context: Dict
    ) -> Dict[str, str]:
        """Generate response using Claude"""
        prompt = f"""You are a medical assistant helping doctors make decisions based on a knowledge graph.

User Query: {message}

Graph Context:
- Nodes found: {len(graph_context.get('nodes', []))}
- Related entities: {json.dumps([n for n in graph_context.get('nodes', [])[:5]], default=str)}

Please provide a helpful medical response based on this context. Be concise and reference the graph data when relevant.
Include any relevant medical relationships or patterns found in the data."""

        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=500,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            return {"text": response.content[0].text}
        except Exception as e:
            return {"text": f"Error generating response: {e}"}

    def _generate_mock_response(
        self, message: str, graph_context: Dict
    ) -> Dict[str, str]:
        """Generate mock response for testing"""
        nodes_count = len(graph_context.get("nodes", []))
        return {
            "text": f"Based on the knowledge graph, I found {nodes_count} relevant medical entities related to your query: '{message}'. "
            f"The graph shows connections between symptoms, diseases, and treatments that can help inform medical decisions."
        }


def get_chat_service(request: Request) -> ChatService:
    """Get chat service instance"""
    query_service = QueryService(request.app.state.neo4j)
    return ChatService(query_service)


@router.post("/message")
def send_message(
    request: ChatRequest, chat_service: ChatService = Depends(get_chat_service)
):
    """Send a message and get response"""
    # Generate or retrieve session ID
    session_id = request.session_id or str(uuid.uuid4())

    # Generate response
    result = chat_service.generate_response(request.message, request.context)

    # Store in session history
    if session_id not in chat_service.sessions:
        chat_service.sessions[session_id] = []

    chat_service.sessions[session_id].append(
        {"role": "user", "content": request.message, "timestamp": datetime.now()}
    )
    chat_service.sessions[session_id].append(
        {
            "role": "assistant",
            "content": result["response"],
            "timestamp": datetime.now(),
        }
    )

    return ChatResponse(
        response=result["response"],
        graph_path=result.get("graph_path"),
        evidence=result.get("evidence"),
        session_id=session_id,
    )


@router.get("/session/{session_id}")
def get_session_history(
    session_id: str, chat_service: ChatService = Depends(get_chat_service)
):
    """Get chat session history"""
    if session_id not in chat_service.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "messages": chat_service.sessions[session_id],
    }


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, request: Request):
    """WebSocket endpoint for real-time chat"""
    await websocket.accept()
    query_service = QueryService(request.app.state.neo4j)
    chat_service = ChatService(query_service)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # Generate response
            result = chat_service.generate_response(
                message_data.get("message"), message_data.get("context")
            )

            # Send response back
            await websocket.send_json(
                {
                    "type": "response",
                    "data": {
                        "response": result["response"],
                        "graph_path": result.get("graph_path"),
                        "evidence": result.get("evidence"),
                        "timestamp": datetime.now().isoformat(),
                    },
                }
            )

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close()


@router.post("/query-to-cypher")
def natural_language_to_cypher(
    query: str, chat_service: ChatService = Depends(get_chat_service)
):
    """Convert natural language query to Cypher"""
    if not chat_service.client:
        # Return mock Cypher for testing
        return {
            "natural_language": query,
            "cypher": "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) RETURN p, e LIMIT 10",
            "explanation": "Mock Cypher query for testing",
        }

    prompt = f"""Convert this natural language medical query to a Neo4j Cypher query:

Query: {query}

The graph schema includes:
- Nodes: Patient, Encounter, Symptom, Disease, Medication, Test, TestResult
- Relationships: HAS_ENCOUNTER, HAS_SYMPTOM, DIAGNOSED_AS, PRESCRIBED, ORDERED_TEST, YIELDED

Return only the Cypher query, no explanation."""

    try:
        response = chat_service.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=200,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        cypher = response.content[0].text.strip()

        return {
            "natural_language": query,
            "cypher": cypher,
            "explanation": "Generated from natural language using Claude",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Cypher: {e}")
