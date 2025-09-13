from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


# Relationship Models
class HasEncounter(BaseModel):
    patient_id: str
    encounter_id: str


class HasSymptom(BaseModel):
    encounter_id: str
    symptom_name: str
    symptom_code: Optional[str] = None
    onset: Optional[datetime] = None
    negation: bool = False
    uncertainty: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source_id: Optional[str] = None


class DiagnosedAs(BaseModel):
    encounter_id: str
    disease_code: str
    status: str = "confirmed"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    valid_from: date
    valid_to: Optional[date] = None
    source_id: Optional[str] = None


class OrderedTest(BaseModel):
    encounter_id: str
    test_name: str
    test_loinc: Optional[str] = None
    time: Optional[datetime] = None
    priority: Optional[str] = None
    source_id: Optional[str] = None


class Yielded(BaseModel):
    test_name: str
    test_result_id: str
    time: Optional[datetime] = None
    lab_id: Optional[str] = None
    method: Optional[str] = None
    source_id: Optional[str] = None


class Prescribed(BaseModel):
    encounter_id: str
    medication_code: str
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    duration_days: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    source_id: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class Performed(BaseModel):
    encounter_id: str
    procedure_code: str
    time: Optional[datetime] = None
    outcome: Optional[str] = None
    source_id: Optional[str] = None


class AttendedBy(BaseModel):
    encounter_id: str
    clinician_id: str
    role: Optional[str] = None


class EvidencedBy(BaseModel):
    assertion_id: str
    source_id: str
    chunk_ids: Optional[List[str]] = None
