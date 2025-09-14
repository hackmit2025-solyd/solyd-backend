"""
Entity extraction service using Claude
"""

import traceback
from typing import Dict, List, Optional
import json
from datetime import datetime
from anthropic import Anthropic
from app.config import settings


class ExtractionService:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    def extract_from_chunks(self, chunks: List[Dict]) -> Dict:
        """Extract entities and assertions from text chunks"""
        extracted_chunks = []

        for chunk in chunks:
            result = self.extract_entities(chunk["text"])
            result["chunk_id"] = chunk["chunk_id"]
            extracted_chunks.append(result)

        return {"chunks": extracted_chunks}

    def extract_entities(self, text: str, context: Dict = None) -> Dict:
        """Extract medical entities and relationships from text"""
        prompt = self._build_extraction_prompt(text, context)

        try:
            response = self.client.messages.create(
                model=settings.claude_model,
                max_tokens=8192,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse JSON response
            content = response.content[0].text

            # Try to find JSON in the response
            if not content:
                print("ERROR: Empty response from Claude")
                return {"entities": {}, "assertions": []}

            # Look for JSON block in the response (handles markdown code blocks)
            json_start = content.find("{")
            json_end = content.rfind("}") + 1

            if json_start != -1 and json_end > json_start:
                json_str = content[json_start:json_end]
                result = json.loads(json_str)
                return result
            else:
                print("ERROR: No JSON found in response")
                return {"entities": {}, "assertions": []}

        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(
                f"Content that failed to parse: {content[:1000] if 'content' in locals() else 'No content'}"
            )
            return {"entities": {}, "assertions": []}
        except Exception as e:
            print(f"Extraction error: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return {"entities": {}, "assertions": []}

    def _build_extraction_prompt(self, text: str, context: Dict = None) -> str:
        """Build prompt for entity extraction"""

        # Add context if available
        context_section = ""
        if context:
            context_section = "\n## PREVIOUS CONTEXT (entities from earlier chunks):\n"
            if context.get("patient"):
                context_section += f"- Patient: {context['patient']}\n"
            if context.get("encounter"):
                context_section += f"- Encounter: {context['encounter']}\n"
            if context.get("clinician"):
                context_section += f"- Clinician: {context['clinician']}\n"
            context_section += "\nREFERENCE these entities if they appear in the current text chunk.\n"

        base_prompt = f"""Extract medical entities and relationships from the following text.
{context_section}
## NODE TYPES (with attributes):

### Instance Nodes (always create new):
- **Patient**: dob, sex (M/F/O), name
- **Encounter**: date (required), dept, reason
- **Clinician**: name, specialty
- **TestResult**: value, unit, ref_low, ref_high, time

### Catalog Nodes (reuse if same code/name):
- **Symptom**: name (required), code, system (e.g., SNOMED)
- **Disease**: code (required), system (required, e.g., ICD10), name
- **Test**: name (required), loinc, value_range
- **Medication**: code (required), system (required, e.g., RxNorm/ATC), name
- **Procedure**: code (required), system (required), name
- **Guideline**: title, source, url

## RELATIONSHIP TYPES:
### Clinical Relationships:
- **HAS_ENCOUNTER**: Patient → Encounter
- **SEEN_BY**: Encounter → Clinician (role)
- **HAS_SYMPTOM**: Encounter → Symptom (onset, negation, certainty)
- **DIAGNOSED_AS**: Encounter → Disease (status: confirmed/probable/ruled_out, time)
- **ORDERED_TEST**: Encounter → Test (time)
- **HAS_RESULT**: Encounter → TestResult
- **OF_TEST**: TestResult → Test
- **PRESCRIBED**: Encounter → Medication (dose, route, frequency, start, end)
- **PERFORMED**: Encounter → Procedure (time)

### Knowledge Graph Relationships:
- **HAS_SYMPTOM_KB**: Disease → Symptom (general association)
- **INDICATES_TEST**: Disease → Test
- **HAS_TREATMENT**: Disease → Medication/Procedure
- **SUPPORTS**: Guideline → Disease/Symptom/Test/Medication/Procedure

## IMPORTANT RULES:
1. DO NOT extract or generate IDs - system will assign UUIDs
2. For catalog nodes (Symptom, Disease, Test, Medication, Procedure):
   - Always include code and system when available
   - These will be matched against existing nodes by code/name
3. For instance nodes (Patient, Encounter, Clinician, TestResult):
   - New nodes will always be created
4. Include confidence scores (0.0-1.0) for uncertain relationships
5. Use negation=true for negative findings (e.g., "no fever")

Return a JSON object with this structure:
{{
  "entities": {{
    "patients": [
      {{"name": "John Doe", "sex": "M", "dob": "1980-01-15"}}
    ],
    "encounters": [
      {{"date": "2025-09-13", "dept": "Internal Medicine"}}
    ],
    "symptoms": [
      {{"name": "fever", "code": "386661006", "system": "SNOMED"}},
      {{"name": "myalgia", "code": "68962001", "system": "SNOMED"}},
      {{"name": "cough", "code": "49727002", "system": "SNOMED"}}
    ],
    "diseases": [
      {{"code": "J10", "system": "ICD10", "name": "Influenza"}}
    ],
    "tests": [
      {{"name": "Influenza A+B Rapid Test", "loinc": "80383-3"}}
    ],
    "test_results": [
      {{"value": "Positive", "time": "2025-09-13T10:30:00"}}
    ],
    "medications": [
      {{"code": "1099298", "system": "RxNorm", "name": "Oseltamivir 75 MG"}}
    ],
    "clinicians": [
      {{"name": "Dr. Smith", "specialty": "Internal Medicine"}}
    ],
    "procedures": [],
    "guidelines": []
  }},
  "assertions": [
    {{
      "predicate": "HAS_ENCOUNTER",
      "subject_ref": "patients[0]",
      "object_ref": "encounters[0]",
      "confidence": 1.0
    }},
    {{
      "predicate": "HAS_SYMPTOM",
      "subject_ref": "encounters[0]",
      "object_ref": "symptoms[0]",
      "properties": {{"onset": "2025-09-12", "negation": false}},
      "confidence": 1.0
    }},
    {{
      "predicate": "DIAGNOSED_AS",
      "subject_ref": "encounters[0]",
      "object_ref": "diseases[0]",
      "properties": {{"status": "confirmed"}},
      "confidence": 0.9
    }},
    {{
      "predicate": "ORDERED_TEST",
      "subject_ref": "encounters[0]",
      "object_ref": "tests[0]",
      "confidence": 1.0
    }},
    {{
      "predicate": "HAS_RESULT",
      "subject_ref": "encounters[0]",
      "object_ref": "test_results[0]",
      "confidence": 1.0
    }},
    {{
      "predicate": "OF_TEST",
      "subject_ref": "test_results[0]",
      "object_ref": "tests[0]",
      "confidence": 1.0
    }},
    {{
      "predicate": "PRESCRIBED",
      "subject_ref": "encounters[0]",
      "object_ref": "medications[0]",
      "properties": {{"dose": "75 mg", "route": "oral", "frequency": "BID"}},
      "confidence": 1.0
    }},
    {{
      "predicate": "SEEN_BY",
      "subject_ref": "encounters[0]",
      "object_ref": "clinicians[0]",
      "properties": {{"role": "attending"}},
      "confidence": 1.0
    }}
  ]
}}

Text to extract from:
{text}"""
        return base_prompt

    def merge_chunks(self, chunks: List[Dict]) -> Dict:
        """Merge extracted entities from multiple chunks"""
        merged_entities = {}
        merged_assertions = []

        for chunk in chunks:
            # Merge entities
            for entity_type, entities in chunk.get("entities", {}).items():
                if entity_type not in merged_entities:
                    merged_entities[entity_type] = []
                merged_entities[entity_type].extend(entities)

            # Merge assertions
            merged_assertions.extend(chunk.get("assertions", []))

        return {"entities": merged_entities, "assertions": merged_assertions}

    def normalize_entities(self, entities: Dict) -> Dict:
        """Normalize entity data"""
        normalized = {}

        for entity_type, entity_list in entities.items():
            normalized[entity_type] = []
            for entity in entity_list:
                norm_entity = self._normalize_entity(entity_type, entity)
                if norm_entity:
                    normalized[entity_type].append(norm_entity)

        return normalized

    def _normalize_entity(self, entity_type: str, entity: Dict) -> Optional[Dict]:
        """Normalize a single entity - no ID generation, just validation"""

        # Basic validation by entity type
        if entity_type == "patients":
            # Optional fields, just pass through
            pass

        elif entity_type == "encounters":
            # Date is required
            if "date" not in entity:
                entity["date"] = datetime.now().date().isoformat()
            elif isinstance(entity["date"], str):
                # Ensure date format
                try:
                    datetime.fromisoformat(entity["date"])
                except (ValueError, TypeError):
                    entity["date"] = datetime.now().date().isoformat()

        elif entity_type == "symptoms":
            if "name" not in entity:
                return None

        elif entity_type == "diseases":
            if "code" not in entity or "system" not in entity:
                return None

        elif entity_type == "tests":
            if "name" not in entity:
                return None

        elif entity_type == "test_results":
            # Value is optional
            pass

        elif entity_type == "medications":
            if "code" not in entity or "system" not in entity:
                return None

        elif entity_type == "procedures":
            if "code" not in entity or "system" not in entity:
                return None

        elif entity_type == "clinicians":
            # Name is optional
            pass

        elif entity_type == "guidelines":
            # Title is optional
            pass

        return entity


# Singleton instance
extraction_service = ExtractionService()
