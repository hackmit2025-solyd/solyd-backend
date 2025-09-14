"""Service for generating and validating Cypher queries from natural language"""

from typing import Dict, Optional, Tuple
import json
from anthropic import Anthropic
from app.config import settings
from app.db.neo4j import Neo4jConnection
from app.models.search_schemas import EntityMatch


class CypherGenerator:
    """Generate and validate Cypher queries from natural language"""

    def __init__(self, neo4j: Neo4jConnection):
        self.neo4j = neo4j
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    def natural_to_cypher(
        self,
        natural_query: str,
        entity_mappings: Dict[str, EntityMatch] = None,
        max_retries: int = 3,
    ) -> Tuple[str, str]:
        """
        Convert natural language query to Cypher

        Args:
            natural_query: Natural language query
            entity_mappings: Mapped entities with UUIDs
            max_retries: Maximum retry attempts for fixing errors

        Returns:
            Tuple of (cypher_query, validation_status)
        """
        # Extract entities from query if not provided
        if not entity_mappings:
            entity_mappings = {}

        # Generate initial Cypher
        cypher = self._generate_cypher(natural_query, entity_mappings)

        # Validate and fix if necessary
        for _ in range(max_retries):
            is_valid, error = self._validate_cypher(cypher)
            if is_valid:
                return cypher, "valid"

            # Try to fix the error
            cypher = self._fix_cypher_error(cypher, error, natural_query)

        return cypher, f"potentially invalid after {max_retries} attempts"

    def _generate_cypher(
        self, natural_query: str, entity_mappings: Dict[str, EntityMatch]
    ) -> str:
        """Generate Cypher query using Claude"""

        # Build entity context
        entity_context = ""
        if entity_mappings:
            entity_context = "\n## Mapped Entities (use these UUIDs in the query):\n"
            for original, match in entity_mappings.items():
                entity_type = match.matched_entity.get("__labels__", ["Unknown"])[0] if "__labels__" in match.matched_entity else "Unknown"
                entity_context += f"- '{original}' -> {entity_type} with UUID: '{match.uuid}'\n"

        prompt = f"""Convert this natural language query to a Neo4j Cypher query.

## Graph Schema:
### Node Types:
- Patient (uuid, name, dob, sex)
- Encounter (uuid, date, dept, reason)
- Clinician (uuid, name, specialty)
- Disease (uuid, code, system, name)
- Symptom (uuid, name, code, system)
- Medication (uuid, code, system, name)
- Procedure (uuid, code, system, name)
- Test (uuid, name, loinc)
- TestResult (uuid, value, unit, ref_low, ref_high, time)

### Relationship Types:
- HAS_ENCOUNTER: Patient -> Encounter
- SEEN_BY: Encounter -> Clinician
- HAS_SYMPTOM: Encounter -> Symptom
- DIAGNOSED_AS: Encounter -> Disease
- ORDERED_TEST: Encounter -> Test
- HAS_RESULT: Encounter -> TestResult
- OF_TEST: TestResult -> Test
- PRESCRIBED: Encounter -> Medication
- PERFORMED: Encounter -> Procedure

{entity_context}

## Important:
1. ALWAYS use UUID for matching when provided
2. Return only nodes and relationships that exist
3. Use MATCH, not CREATE or MERGE
4. Include relevant properties in RETURN
5. Limit results appropriately (default 50)

Natural Language Query: {natural_query}

Return ONLY the Cypher query, no explanation or markdown:"""

        try:
            response = self.client.messages.create(
                model=settings.claude_model,
                max_tokens=1000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            cypher = response.content[0].text.strip()

            # Remove markdown code blocks if present
            if cypher.startswith("```"):
                lines = cypher.split("\n")
                cypher = "\n".join(lines[1:-1])

            return cypher

        except Exception as e:
            print(f"Error generating Cypher: {e}")
            # Return a safe default query
            return "MATCH (n) RETURN n LIMIT 10"

    def _validate_cypher(self, cypher: str) -> Tuple[bool, Optional[str]]:
        """
        Validate Cypher query using EXPLAIN

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Use EXPLAIN to validate without executing
            explain_query = f"EXPLAIN {cypher}"
            self.neo4j.execute_query(explain_query)
            return True, None
        except Exception as e:
            return False, str(e)

    def _fix_cypher_error(
        self, cypher: str, error: str, original_query: str
    ) -> str:
        """Fix Cypher query error using Claude"""

        prompt = f"""Fix this Cypher query error.

Original natural language query: {original_query}

Cypher query with error:
{cypher}

Error message:
{error}

Common fixes:
- Variable naming issues: ensure variables are defined before use
- Property access: use node.property not node['property']
- Relationship syntax: use -[r:TYPE]-> not -[:TYPE]-
- UUID matching: use WHERE n.uuid = 'value' not WHERE n.uuid = value
- RETURN clause: ensure all used variables are returned or aggregated

Return ONLY the fixed Cypher query:"""

        try:
            response = self.client.messages.create(
                model=settings.claude_model,
                max_tokens=1000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            fixed_cypher = response.content[0].text.strip()

            # Remove markdown if present
            if fixed_cypher.startswith("```"):
                lines = fixed_cypher.split("\n")
                fixed_cypher = "\n".join(lines[1:-1])

            return fixed_cypher

        except Exception as e:
            print(f"Error fixing Cypher: {e}")
            return cypher  # Return original if fix fails

    def extract_entities_from_query(self, natural_query: str) -> Dict[str, list]:
        """Extract entities from natural language query"""

        prompt = f"""Extract medical entities from this query.

Query: {natural_query}

Identify and categorize entities into these types:
- patients (names of patients)
- clinicians (names of doctors/nurses)
- diseases (disease names or ICD codes)
- symptoms (symptom descriptions)
- medications (drug names)
- procedures (procedure names)
- tests (test names)

Return as JSON with entity type as key and list of entity names as value.
Example: {{"patients": ["John Doe"], "diseases": ["diabetes"]}}

Return ONLY valid JSON:"""

        try:
            response = self.client.messages.create(
                model=settings.claude_model,
                max_tokens=500,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()

            # Extract JSON from response
            if "{" in content and "}" in content:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]
                return json.loads(json_str)

            return {}

        except Exception as e:
            print(f"Error extracting entities: {e}")
            return {}