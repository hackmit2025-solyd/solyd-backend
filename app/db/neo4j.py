from neo4j import GraphDatabase
from typing import Dict, List, Any, Optional
from app.config import settings


class Neo4jConnection:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password)
        )
    
    def close(self):
        if self.driver:
            self.driver.close()
    
    def execute_query(self, query: str, parameters: Optional[Dict] = None) -> List[Dict]:
        """Execute a Cypher query and return results"""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def execute_write(self, query: str, parameters: Optional[Dict] = None) -> Dict:
        """Execute a write transaction"""
        with self.driver.session() as session:
            result = session.write_transaction(
                lambda tx: tx.run(query, parameters or {}).consume()
            )
            return {
                "nodes_created": result.counters.nodes_created,
                "relationships_created": result.counters.relationships_created,
                "properties_set": result.counters.properties_set
            }
    
    def test_connection(self) -> bool:
        """Test if Neo4j connection is working"""
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1 AS test")
                return result.single()["test"] == 1
        except Exception as e:
            print(f"Neo4j connection test failed: {e}")
            return False