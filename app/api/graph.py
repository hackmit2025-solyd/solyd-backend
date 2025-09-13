from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List
from app.services.query import QueryService
from app.models.schemas import SubgraphRequest, SubgraphResponse, GraphQuery

router = APIRouter()


def get_query_service(request: Request) -> QueryService:
    """Get query service with Neo4j connection"""
    return QueryService(request.app.state.neo4j)


@router.get("/patient/{patient_id}")
def get_patient(
    patient_id: str, query_service: QueryService = Depends(get_query_service)
):
    """Get patient summary with all related data"""
    result = query_service.get_patient_summary(patient_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return result


@router.get("/encounter/{encounter_id}")
def get_encounter(
    encounter_id: str, query_service: QueryService = Depends(get_query_service)
):
    """Get detailed encounter information"""
    result = query_service.get_encounter_details(encounter_id)
    if not result:
        raise HTTPException(
            status_code=404, detail=f"Encounter {encounter_id} not found"
        )
    return result


@router.post("/subgraph")
def get_subgraph(
    request: SubgraphRequest, query_service: QueryService = Depends(get_query_service)
):
    """Get subgraph around a specific node"""
    # Determine node type from the node_id pattern
    node_type = _infer_node_type(request.node_id)

    result = query_service.get_subgraph(
        node_id=request.node_id, node_type=node_type, depth=request.depth
    )

    return SubgraphResponse(
        nodes=result["nodes"],
        relationships=result["relationships"],
        center_node=result["center_node"],
    )


@router.get("/path/{start_id}/{end_id}")
def find_path(
    start_id: str,
    end_id: str,
    max_depth: int = 5,
    query_service: QueryService = Depends(get_query_service),
):
    """Find shortest path between two nodes"""
    paths = query_service.find_path_between_nodes(start_id, end_id, max_depth)
    if not paths:
        raise HTTPException(
            status_code=404, detail=f"No path found between {start_id} and {end_id}"
        )
    return paths


@router.post("/search/symptoms")
def search_by_symptoms(
    symptom_codes: List[str], query_service: QueryService = Depends(get_query_service)
):
    """Find diseases associated with given symptoms"""
    results = query_service.search_by_symptoms(symptom_codes)
    return {"symptom_codes": symptom_codes, "associated_diseases": results}


@router.get("/evidence/{assertion_id}")
def get_evidence(
    assertion_id: str, query_service: QueryService = Depends(get_query_service)
):
    """Get evidence trail for an assertion"""
    result = query_service.get_evidence_trail(assertion_id)
    if not result:
        raise HTTPException(
            status_code=404, detail=f"Assertion {assertion_id} not found"
        )
    return result


@router.post("/query")
def execute_query(
    query: GraphQuery, query_service: QueryService = Depends(get_query_service)
):
    """Execute custom Cypher query (read-only)"""
    try:
        results = query_service.execute_custom_query(query.query, query.parameters)
        return {"results": results, "count": len(results)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {e}")


def _infer_node_type(node_id: str) -> str:
    """Infer node type from ID pattern"""
    if node_id.startswith("P"):
        return "Patient"
    elif node_id.startswith("E"):
        return "Encounter"
    elif node_id.startswith("ICD"):
        return "Disease"
    elif node_id.startswith("RxNorm"):
        return "Medication"
    elif node_id.startswith("SNOMED"):
        return "Symptom"
    elif node_id.startswith("LOINC"):
        return "Test"
    else:
        # Default to Patient for now
        return "Patient"
