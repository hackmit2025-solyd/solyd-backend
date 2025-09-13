"""
JSON Schema validation with retry mechanism for Claude responses
"""

import json
import re
from typing import Dict, Any, Optional
from jsonschema import ValidationError, Draft7Validator
import time
from app.config import settings


class SchemaValidator:
    """Validates and repairs JSON responses from LLM"""

    # Define schemas for different extraction types
    SCHEMAS = {
        "extraction": {
            "type": "object",
            "required": ["entities", "assertions"],
            "properties": {
                "entities": {
                    "type": "object",
                    "properties": {
                        "patients": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/patient"},
                        },
                        "encounters": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/encounter"},
                        },
                        "symptoms": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/symptom"},
                        },
                        "diseases": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/disease"},
                        },
                        "tests": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/test"},
                        },
                        "test_results": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/test_result"},
                        },
                        "medications": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/medication"},
                        },
                        "procedures": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/procedure"},
                        },
                        "clinicians": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/clinician"},
                        },
                    },
                },
                "assertions": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/assertion"},
                },
            },
            "definitions": {
                "patient": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "dob": {"type": "string", "format": "date"},
                        "sex": {"type": "string", "enum": ["M", "F", "O", "U"]},
                    },
                },
                "encounter": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "date": {"type": "string"},
                        "dept": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
                "symptom": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "code": {"type": "string"},
                        "system": {"type": "string"},
                        "severity": {"type": "string"},
                        "onset": {"type": "string"},
                    },
                },
                "disease": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "code": {"type": "string"},
                        "name": {"type": "string"},
                        "system": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["confirmed", "suspected", "ruled_out"],
                        },
                    },
                },
                "test": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "loinc": {"type": "string"},
                        "category": {"type": "string"},
                    },
                },
                "test_result": {
                    "type": "object",
                    "required": ["test", "value"],
                    "properties": {
                        "id": {"type": "string"},
                        "test": {"type": "string"},
                        "value": {"type": ["number", "string"]},
                        "unit": {"type": "string"},
                        "time": {"type": "string"},
                        "flag": {"type": "string", "enum": ["H", "L", "N"]},
                    },
                },
                "medication": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "code": {"type": "string"},
                        "name": {"type": "string"},
                        "system": {"type": "string"},
                        "dose": {"type": "string"},
                        "route": {"type": "string"},
                        "frequency": {"type": "string"},
                    },
                },
                "procedure": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "code": {"type": "string"},
                        "name": {"type": "string"},
                        "cpt": {"type": "string"},
                    },
                },
                "clinician": {
                    "type": "object",
                    "required": ["id", "name"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "specialty": {"type": "string"},
                        "npi": {"type": "string"},
                    },
                },
                "assertion": {
                    "type": "object",
                    "required": ["predicate", "subject_ref", "object_ref"],
                    "properties": {
                        "id": {"type": "string"},
                        "predicate": {
                            "type": "string",
                            "enum": [
                                "HAS_SYMPTOM",
                                "DIAGNOSED_AS",
                                "PRESCRIBED",
                                "ORDERED_TEST",
                                "YIELDED",
                                "HAS_ENCOUNTER",
                                "TREATED_BY",
                                "REFERRED_TO",
                                "ALLERGIC_TO",
                                "CONTRAINDICATED",
                                "PERFORMED",
                            ],
                        },
                        "subject_ref": {"type": "string"},
                        "object_ref": {"type": "string"},
                        "time": {"type": "string"},
                        "negation": {"type": "boolean"},
                        "uncertainty": {"type": "boolean"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
        }
    }

    def __init__(self):
        self.validators = {
            name: Draft7Validator(schema) for name, schema in self.SCHEMAS.items()
        }

    def validate_with_retry(
        self,
        data: Any,
        schema_name: str,
        max_retries: Optional[int] = None,
        repair_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """Validate JSON with retry and repair attempts"""
        if schema_name not in self.validators:
            raise ValueError(f"Unknown schema: {schema_name}")

        validator = self.validators[schema_name]
        last_error = None
        max_retries = max_retries or settings.max_retry_attempts

        for attempt in range(max_retries):
            try:
                # Attempt validation
                validator.validate(data)
                return {"valid": True, "data": data, "attempts": attempt + 1}

            except ValidationError as e:
                last_error = e

                # Try to repair the data
                if repair_callback:
                    repaired = repair_callback(data, e)
                    if repaired and repaired != data:
                        data = repaired
                        continue

                # Auto-repair common issues
                data = self._auto_repair(data, e, schema_name)

                # Exponential backoff
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2**attempt))

        return {
            "valid": False,
            "data": data,
            "attempts": max_retries,
            "error": str(last_error) if last_error else "Unknown validation error",
        }

    def _auto_repair(self, data: Any, error: ValidationError, schema_name: str) -> Any:
        """Attempt to automatically repair common JSON issues"""
        if not isinstance(data, dict):
            return {"entities": {}, "assertions": []}

        # Fix missing required fields
        if "entities" not in data:
            data["entities"] = {}
        if "assertions" not in data:
            data["assertions"] = []

        # Ensure entities is a dict
        if not isinstance(data["entities"], dict):
            data["entities"] = {}

        # Ensure assertions is a list
        if not isinstance(data["assertions"], list):
            data["assertions"] = []

        # Fix common entity issues
        for entity_type in [
            "patients",
            "encounters",
            "symptoms",
            "diseases",
            "tests",
            "test_results",
            "medications",
        ]:
            if entity_type in data["entities"]:
                if not isinstance(data["entities"][entity_type], list):
                    # Convert single item to list
                    if isinstance(data["entities"][entity_type], dict):
                        data["entities"][entity_type] = [data["entities"][entity_type]]
                    else:
                        data["entities"][entity_type] = []

        # Fix assertion issues
        fixed_assertions = []
        for assertion in data.get("assertions", []):
            if isinstance(assertion, dict):
                # Ensure required fields
                if (
                    "predicate" in assertion
                    and "subject_ref" in assertion
                    and "object_ref" in assertion
                ):
                    # Fix predicate if needed
                    predicate = assertion["predicate"].upper().replace(" ", "_")
                    if (
                        predicate
                        not in self.SCHEMAS["extraction"]["definitions"]["assertion"][
                            "properties"
                        ]["predicate"]["enum"]
                    ):
                        # Try to map to valid predicate
                        predicate_map = {
                            "HAS": "HAS_SYMPTOM",
                            "DIAGNOSED": "DIAGNOSED_AS",
                            "PRESCRIBED_TO": "PRESCRIBED",
                            "TESTED": "ORDERED_TEST",
                            "RESULT": "YIELDED",
                            "ENCOUNTER": "HAS_ENCOUNTER",
                            "TREATED": "TREATED_BY",
                            "REFERRED": "REFERRED_TO",
                            "ALLERGIC": "ALLERGIC_TO",
                            "CONTRAINDICATED_FOR": "CONTRAINDICATED",
                        }
                        for key, value in predicate_map.items():
                            if key in predicate:
                                predicate = value
                                break

                    assertion["predicate"] = predicate

                    # Ensure confidence is in range
                    if "confidence" in assertion:
                        try:
                            conf = float(assertion["confidence"])
                            assertion["confidence"] = max(0.0, min(1.0, conf))
                        except (ValueError, TypeError):
                            assertion["confidence"] = 0.5

                    # Ensure booleans
                    for bool_field in ["negation", "uncertainty"]:
                        if bool_field in assertion:
                            assertion[bool_field] = bool(assertion[bool_field])

                    fixed_assertions.append(assertion)

        data["assertions"] = fixed_assertions

        return data

    def extract_json_from_text(self, text: str) -> Optional[Dict]:
        """Extract JSON from LLM response text"""
        # Try to find JSON block
        json_start = text.find("{")
        json_end = text.rfind("}") + 1

        if json_start == -1 or json_end <= json_start:
            # Try to find JSON array
            json_start = text.find("[")
            json_end = text.rfind("]") + 1

        if json_start != -1 and json_end > json_start:
            json_str = text[json_start:json_end]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # Try to fix common JSON issues
                json_str = self._fix_json_string(json_str)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    return None
        return None

    def _fix_json_string(self, json_str: str) -> str:
        """Fix common JSON string issues"""
        # Fix trailing commas
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)

        # Fix single quotes
        json_str = json_str.replace("'", '"')

        # Fix unquoted keys
        json_str = re.sub(r"(\w+):", r'"\1":', json_str)

        # Fix None/null
        json_str = json_str.replace("None", "null")
        json_str = json_str.replace("True", "true")
        json_str = json_str.replace("False", "false")

        return json_str


# Singleton instance
validator = SchemaValidator()
