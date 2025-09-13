"""
Initialize Neo4j schema with UUID-based constraints and indexes
"""

from app.db.neo4j import Neo4jConnection


def drop_all_constraints_and_indexes(neo4j: Neo4jConnection):
    """Drop all existing constraints and indexes"""
    print("Dropping all existing constraints and indexes...")

    # Get all constraints
    try:
        constraints = neo4j.execute_query("SHOW CONSTRAINTS")
        for constraint in constraints:
            name = constraint.get("name")
            if name:
                try:
                    neo4j.execute_query(f"DROP CONSTRAINT {name}")
                    print(f"  Dropped constraint: {name}")
                except Exception as e:
                    print(f"  Failed to drop constraint {name}: {e}")
    except Exception as e:
        print(f"  Error listing constraints: {e}")

    # Get all indexes
    try:
        indexes = neo4j.execute_query("SHOW INDEXES")
        for index in indexes:
            name = index.get("name")
            # Skip constraint-backed indexes and token lookup indexes
            if (
                name
                and not name.startswith("constraint_")
                and "token_lookup" not in name
            ):
                try:
                    neo4j.execute_query(f"DROP INDEX {name}")
                    print(f"  Dropped index: {name}")
                except Exception as e:
                    print(f"  Failed to drop index {name}: {e}")
    except Exception as e:
        print(f"  Error listing indexes: {e}")


def create_uuid_constraints(neo4j: Neo4jConnection):
    """Create UUID uniqueness constraints for all node types"""
    print("\nCreating UUID constraints...")

    node_labels = [
        "Patient",
        "Encounter",
        "Clinician",
        "TestResult",  # Instance nodes
        "Symptom",
        "Disease",
        "Test",
        "Medication",
        "Procedure",
        "Guideline",  # Catalog nodes
    ]

    for label in node_labels:
        try:
            constraint_name = f"{label.lower()}_uuid_unique"
            query = f"""
            CREATE CONSTRAINT {constraint_name}
            IF NOT EXISTS
            FOR (n:{label})
            REQUIRE n.uuid IS UNIQUE
            """
            neo4j.execute_query(query)
            print(f"  ✓ Created UUID constraint for {label}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  ○ UUID constraint already exists for {label}")
            else:
                print(f"  ✗ Failed to create UUID constraint for {label}: {e}")


def create_catalog_indexes(neo4j: Neo4jConnection):
    """Create indexes for catalog node lookups"""
    print("\nCreating catalog node indexes...")

    # Code+System composite indexes for catalog nodes
    catalog_composite = [
        ("Disease", ["code", "system"]),
        ("Medication", ["code", "system"]),
        ("Procedure", ["code", "system"]),
    ]

    for label, properties in catalog_composite:
        try:
            index_name = f"{label.lower()}_{'_'.join(properties)}_idx"
            prop_list = ", ".join([f"n.{prop}" for prop in properties])
            query = f"""
            CREATE INDEX {index_name}
            IF NOT EXISTS
            FOR (n:{label})
            ON ({prop_list})
            """
            neo4j.execute_query(query)
            print(f"  ✓ Created composite index for {label} on {properties}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  ○ Composite index already exists for {label} on {properties}")
            else:
                print(f"  ✗ Failed to create composite index for {label}: {e}")

    # Single property indexes
    single_indexes = [
        ("Symptom", "code"),
        ("Symptom", "system"),
        ("Symptom", "name"),
        ("Disease", "code"),
        ("Disease", "name"),
        ("Test", "name"),
        ("Test", "loinc"),
        ("Medication", "code"),
        ("Medication", "name"),
        ("Procedure", "code"),
        ("Procedure", "name"),
        ("Clinician", "name"),
        ("Guideline", "title"),
        ("Encounter", "date"),
        ("TestResult", "time"),
        ("Patient", "sex"),
    ]

    for label, prop in single_indexes:
        try:
            index_name = f"{label.lower()}_{prop}_idx"
            query = f"""
            CREATE INDEX {index_name}
            IF NOT EXISTS
            FOR (n:{label})
            ON (n.{prop})
            """
            neo4j.execute_query(query)
            print(f"  ✓ Created {prop} index for {label}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  ○ Index already exists for {label}.{prop}")
            else:
                print(f"  ✗ Failed to create index for {label}.{prop}: {e}")


def verify_schema(neo4j: Neo4jConnection):
    """Verify that all constraints and indexes are in place"""
    print("\nVerifying schema...")

    try:
        # Check constraints
        constraints = neo4j.execute_query("SHOW CONSTRAINTS")
        uuid_constraints = [c for c in constraints if "uuid" in c.get("properties", [])]
        print(f"  Found {len(uuid_constraints)} UUID constraints")

        # Check indexes
        indexes = neo4j.execute_query("SHOW INDEXES")
        user_indexes = [
            i
            for i in indexes
            if not i.get("name", "").startswith("constraint_")
            and "token_lookup" not in i.get("name", "")
        ]
        print(f"  Found {len(user_indexes)} user-defined indexes")

        return {
            "uuid_constraints": len(uuid_constraints),
            "indexes": len(user_indexes),
            "total_constraints": len(constraints),
            "total_indexes": len(indexes),
        }
    except Exception as e:
        print(f"  Error verifying schema: {e}")
        return {}


def init_schema():
    """Initialize the complete Neo4j schema"""
    neo4j = Neo4jConnection()

    try:
        print("=" * 60)
        print("NEO4J SCHEMA INITIALIZATION")
        print("=" * 60)

        # Drop all existing constraints and indexes
        drop_all_constraints_and_indexes(neo4j)

        # Create new UUID-based constraints
        create_uuid_constraints(neo4j)

        # Create catalog lookup indexes
        create_catalog_indexes(neo4j)

        # Verify the schema
        stats = verify_schema(neo4j)

        print("\n" + "=" * 60)
        print("SCHEMA INITIALIZATION COMPLETE!")
        print(f"UUID Constraints: {stats.get('uuid_constraints', 0)}")
        print(f"Indexes: {stats.get('indexes', 0)}")
        print("=" * 60)

        return stats

    except Exception as e:
        print(f"\n✗ Error initializing schema: {e}")
        raise
    finally:
        neo4j.close()


if __name__ == "__main__":
    init_schema()
