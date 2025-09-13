from typing import Dict, List, Any, Optional
from app.db.neo4j import Neo4jConnection


class QueryService:
    def __init__(self, neo4j_conn: Neo4jConnection):
        self.neo4j = neo4j_conn

    def get_patient_summary(self, patient_id: str) -> Dict[str, Any]:
        """Get comprehensive patient summary"""
        query = """
        MATCH (p:Patient {id: $patient_id})
        OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
        OPTIONAL MATCH (e)-[:HAS_SYMPTOM]->(s:Symptom)
        OPTIONAL MATCH (e)-[:DIAGNOSED_AS]->(d:Disease)
        OPTIONAL MATCH (e)-[:PRESCRIBED]->(m:Medication)
        OPTIONAL MATCH (e)-[:ORDERED_TEST]->(t:Test)-[:YIELDED]->(tr:TestResult)
        
        RETURN p,
               collect(DISTINCT e) as encounters,
               collect(DISTINCT s) as symptoms,
               collect(DISTINCT d) as diseases,
               collect(DISTINCT m) as medications,
               collect(DISTINCT {test: t, result: tr}) as tests
        """

        result = self.neo4j.execute_query(query, {"patient_id": patient_id})

        if not result:
            return None

        data = result[0]
        return {
            "patient": data.get("p"),
            "encounters": data.get("encounters", []),
            "symptoms": data.get("symptoms", []),
            "diseases": data.get("diseases", []),
            "medications": data.get("medications", []),
            "tests": data.get("tests", []),
        }

    def get_encounter_details(self, encounter_id: str) -> Dict[str, Any]:
        """Get detailed encounter information with relationships"""
        query = """
        MATCH (e:Encounter {id: $encounter_id})
        OPTIONAL MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e)
        OPTIONAL MATCH (e)-[hs:HAS_SYMPTOM]->(s:Symptom)
        OPTIONAL MATCH (e)-[dg:DIAGNOSED_AS]->(d:Disease)
        OPTIONAL MATCH (e)-[pr:PRESCRIBED]->(m:Medication)
        OPTIONAL MATCH (e)-[ot:ORDERED_TEST]->(t:Test)-[yr:YIELDED]->(tr:TestResult)
        
        RETURN e,
               p,
               collect(DISTINCT {
                   symptom: s, 
                   negation: hs.negation, 
                   confidence: hs.confidence,
                   source_id: hs.source_id
               }) as symptoms,
               collect(DISTINCT {
                   disease: d, 
                   status: dg.status, 
                   confidence: dg.confidence
               }) as diagnoses,
               collect(DISTINCT {
                   medication: m, 
                   dose: pr.dose, 
                   route: pr.route,
                   frequency: pr.frequency
               }) as prescriptions,
               collect(DISTINCT {
                   test: t, 
                   result: tr
               }) as test_results
        """

        result = self.neo4j.execute_query(query, {"encounter_id": encounter_id})

        if not result:
            return None

        data = result[0]
        return {
            "encounter": data.get("e"),
            "patient": data.get("p"),
            "symptoms": [s for s in data.get("symptoms", []) if s.get("symptom")],
            "diagnoses": [d for d in data.get("diagnoses", []) if d.get("disease")],
            "prescriptions": [
                p for p in data.get("prescriptions", []) if p.get("medication")
            ],
            "test_results": [t for t in data.get("test_results", []) if t.get("test")],
        }

    def get_subgraph(
        self, node_id: str, node_type: str, depth: int = 2
    ) -> Dict[str, Any]:
        """Get subgraph around a specific node"""
        query = f"""
        MATCH (n:{node_type} {{id: $node_id}})
        CALL apoc.path.subgraphAll(n, {{
            maxLevel: $depth,
            relationshipFilter: "HAS_ENCOUNTER|HAS_SYMPTOM|DIAGNOSED_AS|PRESCRIBED|ORDERED_TEST|YIELDED"
        }})
        YIELD nodes, relationships
        
        RETURN [node in nodes | {{
                   id: coalesce(node.id, node.code, node.name),
                   label: labels(node)[0],
                   properties: properties(node)
               }}] as nodes,
               [rel in relationships | {{
                   id: id(rel),
                   type: type(rel),
                   from: coalesce(startNode(rel).id, startNode(rel).code, startNode(rel).name),
                   to: coalesce(endNode(rel).id, endNode(rel).code, endNode(rel).name),
                   properties: properties(rel)
               }}] as relationships
        """

        # Fallback query without APOC
        fallback_query = f"""
        MATCH path = (n:{node_type} {{id: $node_id}})-[*0..{depth}]-()
        WITH nodes(path) as pathNodes, relationships(path) as pathRels
        UNWIND pathNodes as node
        WITH collect(DISTINCT node) as nodes, pathRels
        UNWIND pathRels as rel
        WITH nodes, collect(DISTINCT rel) as relationships
        
        RETURN [node in nodes | {{
                   id: coalesce(node.id, node.code, node.name),
                   label: labels(node)[0],
                   properties: properties(node)
               }}] as nodes,
               [rel in relationships | {{
                   id: id(rel),
                   type: type(rel),
                   from: coalesce(startNode(rel).id, startNode(rel).code, startNode(rel).name),
                   to: coalesce(endNode(rel).id, endNode(rel).code, endNode(rel).name),
                   properties: properties(rel)
               }}] as relationships
        """

        try:
            # Try with APOC first
            result = self.neo4j.execute_query(
                query, {"node_id": node_id, "depth": depth}
            )
        except Exception:
            # Fallback to standard Cypher
            result = self.neo4j.execute_query(
                fallback_query, {"node_id": node_id, "depth": depth}
            )

        if not result:
            return {"nodes": [], "relationships": [], "center_node": node_id}

        data = result[0]
        return {
            "nodes": data.get("nodes", []),
            "relationships": data.get("relationships", []),
            "center_node": node_id,
        }

    def find_path_between_nodes(
        self, start_id: str, end_id: str, max_depth: int = 5
    ) -> List[Dict]:
        """Find shortest path between two nodes"""
        query = (
            """
        MATCH path = shortestPath((start {id: $start_id})-[*..%d]-(end {id: $end_id}))
        RETURN [node in nodes(path) | {
                   id: coalesce(node.id, node.code, node.name),
                   label: labels(node)[0],
                   properties: properties(node)
               }] as nodes,
               [rel in relationships(path) | {
                   type: type(rel),
                   properties: properties(rel)
               }] as relationships
        """
            % max_depth
        )

        result = self.neo4j.execute_query(
            query, {"start_id": start_id, "end_id": end_id}
        )

        if not result:
            return []

        return result

    def search_by_symptoms(self, symptom_codes: List[str]) -> List[Dict]:
        """Find diseases associated with given symptoms"""
        query = """
        MATCH (s:Symptom)
        WHERE s.code IN $symptom_codes OR s.name IN $symptom_codes
        MATCH (e:Encounter)-[:HAS_SYMPTOM]->(s)
        MATCH (e)-[:DIAGNOSED_AS]->(d:Disease)
        
        WITH d, count(DISTINCT s) as symptom_count, collect(DISTINCT s.name) as matching_symptoms
        RETURN {
            disease: d,
            symptom_count: symptom_count,
            matching_symptoms: matching_symptoms
        } as result
        ORDER BY symptom_count DESC
        """

        results = self.neo4j.execute_query(query, {"symptom_codes": symptom_codes})
        return [r["result"] for r in results]

    def get_evidence_trail(self, assertion_id: str) -> Dict[str, Any]:
        """Get evidence trail for an assertion"""
        query = """
        MATCH (a:Assertion {assertion_id: $assertion_id})
        OPTIONAL MATCH (a)-[:EVIDENCED_BY]->(src:SourceDocument)
        OPTIONAL MATCH (a)-[:ABOUT_SUBJECT]->(subj)
        OPTIONAL MATCH (a)-[:ABOUT_OBJECT]->(obj)
        
        RETURN a as assertion,
               src as source,
               subj as subject,
               obj as object
        """

        result = self.neo4j.execute_query(query, {"assertion_id": assertion_id})

        if not result:
            return None

        data = result[0]
        return {
            "assertion": data.get("assertion"),
            "source": data.get("source"),
            "subject": data.get("subject"),
            "object": data.get("object"),
        }

    def execute_custom_query(
        self, cypher: str, parameters: Optional[Dict] = None
    ) -> List[Dict]:
        """Execute custom Cypher query (use with caution)"""
        # Add safety checks
        forbidden_keywords = ["DELETE", "REMOVE", "DROP", "DETACH"]
        if any(keyword in cypher.upper() for keyword in forbidden_keywords):
            raise ValueError("Destructive operations are not allowed")

        return self.neo4j.execute_query(cypher, parameters or {})
