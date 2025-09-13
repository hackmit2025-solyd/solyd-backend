from app.db.neo4j import Neo4jConnection
from typing import List, Tuple


class GraphSchemaInitializer:
    def __init__(self, neo4j_conn: Neo4jConnection):
        self.neo4j = neo4j_conn

    def get_constraints(self) -> List[Tuple[str, str]]:
        """Define all unique constraints for nodes"""
        return [
            ("Patient", "id"),
            ("Encounter", "id"),
            ("Disease", "code"),
            ("TestResult", "id"),
            ("Medication", "code"),
            ("Procedure", "code"),
            ("Clinician", "id"),
            ("Guideline", "id"),
            ("SourceDocument", "source_id"),
            ("Assertion", "assertion_id"),
        ]

    def get_indexes(self) -> List[Tuple[str, str]]:
        """Define all indexes for efficient querying"""
        return [
            ("Symptom", "code"),
            ("Symptom", "name"),
            ("Test", "loinc"),
            ("Test", "name"),
            ("Disease", "name"),
            ("Medication", "name"),
            ("Procedure", "name"),
            ("Encounter", "date"),
            ("Patient", "sex"),
            ("SourceDocument", "source_type"),
        ]

    def create_constraints(self):
        """Create unique constraints in Neo4j"""
        constraints = self.get_constraints()
        results = []

        for label, property in constraints:
            query = f"""
            CREATE CONSTRAINT {label.lower()}_{property}_unique 
            IF NOT EXISTS 
            FOR (n:{label}) 
            REQUIRE n.{property} IS UNIQUE
            """
            try:
                self.neo4j.execute_query(query)
                results.append(f"✓ Created constraint: {label}.{property}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    results.append(f"○ Constraint exists: {label}.{property}")
                else:
                    results.append(f"✗ Failed constraint: {label}.{property} - {e}")

        return results

    def create_indexes(self):
        """Create indexes in Neo4j"""
        indexes = self.get_indexes()
        results = []

        for label, property in indexes:
            query = f"""
            CREATE INDEX {label.lower()}_{property}_index 
            IF NOT EXISTS 
            FOR (n:{label}) 
            ON (n.{property})
            """
            try:
                self.neo4j.execute_query(query)
                results.append(f"✓ Created index: {label}.{property}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    results.append(f"○ Index exists: {label}.{property}")
                else:
                    results.append(f"✗ Failed index: {label}.{property} - {e}")

        return results

    def initialize_schema(self):
        """Initialize complete graph schema"""
        print("Initializing Neo4j graph schema...")

        # Create constraints
        print("\nCreating constraints:")
        constraint_results = self.create_constraints()
        for result in constraint_results:
            print(f"  {result}")

        # Create indexes
        print("\nCreating indexes:")
        index_results = self.create_indexes()
        for result in index_results:
            print(f"  {result}")

        print("\nSchema initialization complete!")
        return {"constraints": constraint_results, "indexes": index_results}

    def verify_schema(self):
        """Verify that all constraints and indexes are in place"""
        # Check constraints
        constraints_query = "SHOW CONSTRAINTS"
        constraints = self.neo4j.execute_query(constraints_query)

        # Check indexes
        indexes_query = "SHOW INDEXES"
        indexes = self.neo4j.execute_query(indexes_query)

        return {
            "constraints_count": len(constraints),
            "indexes_count": len(indexes),
            "constraints": constraints,
            "indexes": indexes,
        }


def init_graph_schema():
    """Standalone function to initialize the graph schema"""
    neo4j_conn = Neo4jConnection()
    initializer = GraphSchemaInitializer(neo4j_conn)

    try:
        result = initializer.initialize_schema()
        verification = initializer.verify_schema()
        result["verification"] = verification
        return result
    finally:
        neo4j_conn.close()


if __name__ == "__main__":
    # Run schema initialization
    init_graph_schema()
