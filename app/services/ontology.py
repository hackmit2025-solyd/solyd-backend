"""
Medical ontology mapping service for standard code systems
"""

import json
import sqlite3
from typing import Dict, List, Optional, Tuple
import os
from pathlib import Path
import anthropic
from app.config import settings


class OntologyMapper:
    """Maps medical terms to standard ontologies (ICD, SNOMED, LOINC, RxNorm)"""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize with local ontology database"""
        if db_path is None:
            db_path = os.path.join(
                Path(__file__).parent.parent.parent, "data", "ontology.db"
            )

        self.db_path = db_path
        self.client = None
        if settings.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # Initialize database if needed
        self._init_database()

    def _init_database(self):
        """Initialize ontology database with basic terms"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ontology_terms (
                system TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                synonyms TEXT,
                category TEXT,
                parent_code TEXT,
                description TEXT,
                PRIMARY KEY (system, code)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_name ON ontology_terms(name);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_system ON ontology_terms(system);
        """)

        # Insert sample ontology data (in production, load from official sources)
        sample_terms = [
            # SNOMED CT symptoms
            (
                "SNOMED",
                "386661006",
                "Fever",
                "pyrexia,febrile,elevated temperature",
                "symptom",
                None,
                "Body temperature above normal",
            ),
            (
                "SNOMED",
                "68962001",
                "Myalgia",
                "muscle pain,muscle ache",
                "symptom",
                None,
                "Muscle pain",
            ),
            (
                "SNOMED",
                "49727002",
                "Cough",
                "coughing",
                "symptom",
                None,
                "Sudden expulsion of air from lungs",
            ),
            (
                "SNOMED",
                "25064002",
                "Headache",
                "cephalgia",
                "symptom",
                None,
                "Pain in head",
            ),
            (
                "SNOMED",
                "267036007",
                "Dyspnea",
                "shortness of breath,breathlessness,SOB",
                "symptom",
                None,
                "Difficulty breathing",
            ),
            (
                "SNOMED",
                "422587007",
                "Nausea",
                "feeling sick,queasy",
                "symptom",
                None,
                "Feeling of sickness with inclination to vomit",
            ),
            (
                "SNOMED",
                "422400008",
                "Vomiting",
                "emesis,throwing up",
                "symptom",
                None,
                "Forceful expulsion of stomach contents",
            ),
            (
                "SNOMED",
                "62315008",
                "Diarrhea",
                "loose stools,watery stools",
                "symptom",
                None,
                "Frequent loose or liquid bowel movements",
            ),
            (
                "SNOMED",
                "84229001",
                "Fatigue",
                "tiredness,exhaustion,lethargy",
                "symptom",
                None,
                "Extreme tiredness",
            ),
            (
                "SNOMED",
                "271807003",
                "Polyuria",
                "frequent urination,excessive urination",
                "symptom",
                None,
                "Excessive urination",
            ),
            (
                "SNOMED",
                "17173007",
                "Polydipsia",
                "excessive thirst,increased thirst",
                "symptom",
                None,
                "Excessive thirst",
            ),
            # ICD-10 diseases
            (
                "ICD10",
                "J06.9",
                "Upper respiratory infection",
                "URI,URTI,common cold",
                "disease",
                None,
                "Acute upper respiratory infection, unspecified",
            ),
            (
                "ICD10",
                "E11.9",
                "Type 2 diabetes mellitus",
                "T2DM,diabetes type 2,NIDDM",
                "disease",
                None,
                "Type 2 diabetes mellitus without complications",
            ),
            (
                "ICD10",
                "I10",
                "Essential hypertension",
                "high blood pressure,HTN",
                "disease",
                None,
                "Primary hypertension",
            ),
            (
                "ICD10",
                "J45.9",
                "Asthma",
                "bronchial asthma",
                "disease",
                None,
                "Asthma, unspecified",
            ),
            (
                "ICD10",
                "N39.0",
                "Urinary tract infection",
                "UTI",
                "disease",
                None,
                "Urinary tract infection, site not specified",
            ),
            (
                "ICD10",
                "K21.9",
                "GERD",
                "gastroesophageal reflux,acid reflux",
                "disease",
                None,
                "Gastro-esophageal reflux disease without esophagitis",
            ),
            (
                "ICD10",
                "F32.9",
                "Depression",
                "major depression,MDD",
                "disease",
                None,
                "Major depressive disorder, single episode, unspecified",
            ),
            (
                "ICD10",
                "G43.909",
                "Migraine",
                "migraine headache",
                "disease",
                None,
                "Migraine, unspecified, not intractable, without status migrainosus",
            ),
            (
                "ICD10",
                "J10.1",
                "Influenza",
                "flu",
                "disease",
                None,
                "Influenza with other respiratory manifestations",
            ),
            (
                "ICD10",
                "I20.9",
                "Angina pectoris",
                "chest pain,angina",
                "disease",
                None,
                "Angina pectoris, unspecified",
            ),
            # LOINC lab tests
            (
                "LOINC",
                "1988-5",
                "CRP",
                "C-reactive protein",
                "lab",
                None,
                "C reactive protein [Mass/volume] in Serum or Plasma",
            ),
            (
                "LOINC",
                "6690-2",
                "WBC",
                "white blood cell count,leukocyte count",
                "lab",
                None,
                "Leukocytes [#/volume] in Blood by Automated count",
            ),
            (
                "LOINC",
                "718-7",
                "Hemoglobin",
                "Hgb,Hb",
                "lab",
                None,
                "Hemoglobin [Mass/volume] in Blood",
            ),
            (
                "LOINC",
                "2345-7",
                "Glucose",
                "blood sugar,blood glucose",
                "lab",
                None,
                "Glucose [Mass/volume] in Serum or Plasma",
            ),
            (
                "LOINC",
                "2160-0",
                "Creatinine",
                "Cr",
                "lab",
                None,
                "Creatinine [Mass/volume] in Serum or Plasma",
            ),
            (
                "LOINC",
                "1742-6",
                "ALT",
                "alanine aminotransferase,SGPT",
                "lab",
                None,
                "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma",
            ),
            (
                "LOINC",
                "1920-8",
                "AST",
                "aspartate aminotransferase,SGOT",
                "lab",
                None,
                "Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma",
            ),
            (
                "LOINC",
                "3016-3",
                "TSH",
                "thyroid stimulating hormone,thyrotropin",
                "lab",
                None,
                "Thyrotropin [Units/volume] in Serum or Plasma",
            ),
            (
                "LOINC",
                "2093-3",
                "Cholesterol",
                "total cholesterol",
                "lab",
                None,
                "Cholesterol [Mass/volume] in Serum or Plasma",
            ),
            (
                "LOINC",
                "33914-3",
                "GFR",
                "glomerular filtration rate,eGFR",
                "lab",
                None,
                "Glomerular filtration rate/1.73 sq M.predicted",
            ),
            # RxNorm medications
            (
                "RxNorm",
                "6809",
                "Metformin",
                "glucophage",
                "medication",
                None,
                "Metformin hydrochloride",
            ),
            (
                "RxNorm",
                "1191",
                "Aspirin",
                "ASA,acetylsalicylic acid",
                "medication",
                None,
                "Aspirin",
            ),
            (
                "RxNorm",
                "5640",
                "Ibuprofen",
                "advil,motrin",
                "medication",
                None,
                "Ibuprofen",
            ),
            (
                "RxNorm",
                "161",
                "Acetaminophen",
                "paracetamol,tylenol",
                "medication",
                None,
                "Acetaminophen",
            ),
            ("RxNorm", "29046", "Lisinopril", None, "medication", None, "Lisinopril"),
            (
                "RxNorm",
                "6135",
                "Metoprolol",
                "lopressor",
                "medication",
                None,
                "Metoprolol tartrate",
            ),
            (
                "RxNorm",
                "321988",
                "Atorvastatin",
                "lipitor",
                "medication",
                None,
                "Atorvastatin calcium",
            ),
            (
                "RxNorm",
                "197361",
                "Albuterol",
                "salbutamol,ventolin",
                "medication",
                None,
                "Albuterol sulfate",
            ),
            (
                "RxNorm",
                "35636",
                "Simvastatin",
                "zocor",
                "medication",
                None,
                "Simvastatin",
            ),
            (
                "RxNorm",
                "7052",
                "Morphine",
                None,
                "medication",
                None,
                "Morphine sulfate",
            ),
        ]

        # Insert sample data
        cursor.executemany(
            """
            INSERT OR IGNORE INTO ontology_terms
            (system, code, name, synonyms, category, parent_code, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            sample_terms,
        )

        conn.commit()
        conn.close()

    def search_terms(
        self,
        query: str,
        systems: Optional[List[str]] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """Search for ontology terms matching the query"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build query
        sql = """
            SELECT system, code, name, synonyms, category, description
            FROM ontology_terms
            WHERE (LOWER(name) LIKE ? OR LOWER(synonyms) LIKE ?)
        """
        params = [f"%{query.lower()}%", f"%{query.lower()}%"]

        if systems:
            placeholders = ",".join("?" * len(systems))
            sql += f" AND system IN ({placeholders})"
            params.extend(systems)

        if category:
            sql += " AND category = ?"
            params.append(category)

        sql += f" LIMIT {limit}"

        cursor.execute(sql, params)
        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    def get_candidates(self, term: str, entity_type: str) -> List[Dict]:
        """Get candidate ontology codes for a term based on entity type"""
        # Map entity types to ontology systems and categories
        type_mapping = {
            "symptom": (["SNOMED"], "symptom"),
            "disease": (["ICD10", "SNOMED"], "disease"),
            "test": (["LOINC"], "lab"),
            "medication": (["RxNorm"], "medication"),
        }

        systems, category = type_mapping.get(entity_type, (None, None))
        return self.search_terms(term, systems=systems, category=category)

    def map_with_claude(
        self, term: str, candidates: List[Dict], context: Optional[str] = None
    ) -> Optional[Dict]:
        """Use Claude to select the best ontology match from candidates"""
        if not self.client or not candidates:
            # Return first candidate if no Claude available
            return candidates[0] if candidates else None

        candidates_json = json.dumps(candidates, indent=2)
        prompt = f"""Select the best medical ontology code for the term: "{term}"

Context: {context or 'No additional context'}

Candidates:
{candidates_json}

Return ONLY the JSON of the best matching candidate, or null if none match well.
Consider:
1. Exact name matches are preferred
2. Synonym matches are acceptable
3. Context should guide selection when multiple valid options exist
4. Return null if confidence is low

Response format: {{"system": "...", "code": "...", "name": "...", "confidence": 0.0-1.0}}"""

        try:
            response = self.client.messages.create(
                model=settings.claude_model,
                max_tokens=8192,  # Required parameter for Claude API
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text
            # Extract JSON from response
            json_start = result_text.find("{")
            json_end = result_text.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                result = json.loads(result_text[json_start:json_end])
                return result

        except Exception as e:
            print(f"Claude mapping error: {e}")

        # Fallback to first candidate
        return candidates[0] if candidates else None

    def normalize_code(self, raw_code: str) -> Tuple[Optional[str], Optional[str]]:
        """Normalize a raw code string to (system, code) tuple"""
        if not raw_code:
            return (None, None)

        # Check if already formatted as system:code
        if ":" in raw_code:
            parts = raw_code.split(":", 1)
            return (parts[0], parts[1])

        # Try to identify system from code pattern
        raw_upper = raw_code.upper()

        # ICD-10 patterns
        if (
            raw_upper.startswith(
                (
                    "A",
                    "B",
                    "C",
                    "D",
                    "E",
                    "F",
                    "G",
                    "H",
                    "I",
                    "J",
                    "K",
                    "L",
                    "M",
                    "N",
                    "O",
                    "P",
                    "Q",
                    "R",
                    "S",
                    "T",
                    "U",
                    "V",
                    "W",
                    "X",
                    "Y",
                    "Z",
                )
            )
            and len(raw_upper) >= 3
            and raw_upper[1:3].replace(".", "").isdigit()
        ):
            return ("ICD10", raw_upper)

        # LOINC patterns (numeric with optional dash)
        if raw_code.replace("-", "").replace(".", "").isdigit():
            return ("LOINC", raw_code)

        # SNOMED patterns (long numeric)
        if raw_code.isdigit() and len(raw_code) >= 6:
            return ("SNOMED", raw_code)

        # RxNorm patterns (numeric)
        if raw_code.isdigit() and len(raw_code) <= 7:
            return ("RxNorm", raw_code)

        return (None, raw_code)

    def add_custom_mapping(
        self,
        system: str,
        code: str,
        name: str,
        synonyms: Optional[List[str]] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Add a custom ontology mapping to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        synonyms_str = ",".join(synonyms) if synonyms else None

        cursor.execute(
            """
            INSERT OR REPLACE INTO ontology_terms
            (system, code, name, synonyms, category, parent_code, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (system, code, name, synonyms_str, category, None, description),
        )

        conn.commit()
        conn.close()


# Singleton instance
ontology_mapper = OntologyMapper()
