from fastapi import APIRouter, HTTPException, Depends, Request
from app.services.query import QueryService

router = APIRouter()


def get_query_service(request: Request) -> QueryService:
    """Get query service with Neo4j connection"""
    return QueryService(request.app.state.neo4j)


@router.get("/overview")
def get_graph_overview(query_service: QueryService = Depends(get_query_service)):
    """Get overview statistics of the graph"""
    query = """
    MATCH (p:Patient) WITH count(p) as patient_count
    MATCH (e:Encounter) WITH patient_count, count(e) as encounter_count
    MATCH (s:Symptom) WITH patient_count, encounter_count, count(s) as symptom_count
    MATCH (d:Disease) WITH patient_count, encounter_count, symptom_count, count(d) as disease_count
    MATCH (m:Medication) WITH patient_count, encounter_count, symptom_count, disease_count, count(m) as medication_count
    MATCH (t:Test) WITH patient_count, encounter_count, symptom_count, disease_count, medication_count, count(t) as test_count
    
    RETURN {
        patients: patient_count,
        encounters: encounter_count,
        symptoms: symptom_count,
        diseases: disease_count,
        medications: medication_count,
        tests: test_count
    } as stats
    """

    result = query_service.execute_custom_query(query)
    if result:
        return result[0]["stats"]
    return {
        "patients": 0,
        "encounters": 0,
        "symptoms": 0,
        "diseases": 0,
        "medications": 0,
        "tests": 0,
    }


@router.get("/recent-encounters")
def get_recent_encounters(
    limit: int = 10, query_service: QueryService = Depends(get_query_service)
):
    """Get most recent encounters for visualization"""
    query = """
    MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
    OPTIONAL MATCH (e)-[:HAS_SYMPTOM]->(s:Symptom)
    OPTIONAL MATCH (e)-[:DIAGNOSED_AS]->(d:Disease)
    
    WITH e, p, collect(DISTINCT s.name) as symptoms, collect(DISTINCT d.name) as diseases
    ORDER BY e.date DESC
    LIMIT $limit
    
    RETURN {
        encounter_id: e.id,
        date: e.date,
        patient_id: p.id,
        patient_name: p.name,
        symptoms: symptoms,
        diseases: diseases
    } as encounter
    """

    results = query_service.execute_custom_query(query, {"limit": limit})
    return [r["encounter"] for r in results]


@router.get("/disease-network/{disease_code}")
def get_disease_network(
    disease_code: str, query_service: QueryService = Depends(get_query_service)
):
    """Get network of symptoms, tests, and medications for a disease"""
    query = """
    MATCH (d:Disease {code: $disease_code})
    OPTIONAL MATCH (e:Encounter)-[:DIAGNOSED_AS]->(d)
    OPTIONAL MATCH (e)-[:HAS_SYMPTOM]->(s:Symptom)
    OPTIONAL MATCH (e)-[:PRESCRIBED]->(m:Medication)
    OPTIONAL MATCH (e)-[:ORDERED_TEST]->(t:Test)
    
    WITH d, 
         collect(DISTINCT {id: s.code, name: s.name, type: 'symptom'}) as symptoms,
         collect(DISTINCT {id: m.code, name: m.name, type: 'medication'}) as medications,
         collect(DISTINCT {id: t.loinc, name: t.name, type: 'test'}) as tests
    
    RETURN {
        disease: {id: d.code, name: d.name},
        symptoms: [s in symptoms WHERE s.id IS NOT NULL],
        medications: [m in medications WHERE m.id IS NOT NULL],
        tests: [t in tests WHERE t.id IS NOT NULL]
    } as network
    """

    result = query_service.execute_custom_query(query, {"disease_code": disease_code})
    if not result:
        raise HTTPException(status_code=404, detail=f"Disease {disease_code} not found")

    return result[0]["network"]


@router.get("/symptom-cooccurrence")
def get_symptom_cooccurrence(
    min_count: int = 5, query_service: QueryService = Depends(get_query_service)
):
    """Get co-occurrence matrix of symptoms"""
    query = """
    MATCH (e:Encounter)-[:HAS_SYMPTOM]->(s1:Symptom)
    MATCH (e)-[:HAS_SYMPTOM]->(s2:Symptom)
    WHERE id(s1) < id(s2)
    
    WITH s1, s2, count(e) as cooccurrence_count
    WHERE cooccurrence_count >= $min_count
    
    RETURN {
        symptom1: s1.name,
        symptom2: s2.name,
        count: cooccurrence_count
    } as cooccurrence
    ORDER BY cooccurrence_count DESC
    LIMIT 50
    """

    results = query_service.execute_custom_query(query, {"min_count": min_count})
    return [r["cooccurrence"] for r in results]


@router.get("/patient-timeline/{patient_id}")
def get_patient_timeline(
    patient_id: str, query_service: QueryService = Depends(get_query_service)
):
    """Get timeline visualization data for a patient"""
    query = """
    MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)
    OPTIONAL MATCH (e)-[:HAS_SYMPTOM]->(s:Symptom)
    OPTIONAL MATCH (e)-[:DIAGNOSED_AS]->(d:Disease)
    OPTIONAL MATCH (e)-[:PRESCRIBED]->(m:Medication)
    OPTIONAL MATCH (e)-[:ORDERED_TEST]->(t:Test)
    
    WITH e, 
         collect(DISTINCT s.name) as symptoms,
         collect(DISTINCT d.name) as diseases,
         collect(DISTINCT m.name) as medications,
         collect(DISTINCT t.name) as tests
    ORDER BY e.date
    
    RETURN {
        date: e.date,
        encounter_id: e.id,
        department: e.dept,
        symptoms: symptoms,
        diseases: diseases,
        medications: medications,
        tests: tests
    } as event
    """

    results = query_service.execute_custom_query(query, {"patient_id": patient_id})
    if not results:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    return {"patient_id": patient_id, "timeline": [r["event"] for r in results]}


@router.get("/graph-data")
def get_full_graph_data(
    node_limit: int = 100, query_service: QueryService = Depends(get_query_service)
):
    """Get graph data for visualization (limited for performance)"""
    query = """
    MATCH (n)
    WITH n LIMIT $node_limit
    OPTIONAL MATCH (n)-[r]-(m)
    WHERE id(m) IN [id(x) | x IN collect(n)]
    
    WITH collect(DISTINCT {
        id: coalesce(n.id, n.code, n.name, toString(id(n))),
        label: labels(n)[0],
        properties: properties(n)
    }) as nodes,
    collect(DISTINCT {
        source: coalesce(startNode(r).id, startNode(r).code, startNode(r).name, toString(id(startNode(r)))),
        target: coalesce(endNode(r).id, endNode(r).code, endNode(r).name, toString(id(endNode(r)))),
        type: type(r),
        properties: properties(r)
    }) as edges
    
    RETURN {nodes: nodes, edges: [e in edges WHERE e.source IS NOT NULL AND e.target IS NOT NULL]} as graph
    """

    result = query_service.execute_custom_query(query, {"node_limit": node_limit})
    if result:
        return result[0]["graph"]
    return {"nodes": [], "edges": []}
