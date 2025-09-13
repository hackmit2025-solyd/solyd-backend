from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


class Sex(str, Enum):
    MALE = "M"
    FEMALE = "F"
    OTHER = "O"


class DiseaseStatus(str, Enum):
    CONFIRMED = "confirmed"
    SUSPECTED = "suspected"
    RULED_OUT = "ruled_out"


class TestFlag(str, Enum):
    HIGH = "H"
    LOW = "L"
    NORMAL = "N"


class SourceType(str, Enum):
    EMR = "EMR"
    PDF = "PDF"
    MSD = "MSD"
    PAPER = "PAPER"
    MANUAL = "MANUAL"


# Node Models
class Patient(BaseModel):
    id: str
    dob: Optional[date] = None
    sex: Optional[Sex] = None
    age: Optional[int] = None
    de_identified: bool = True


class Encounter(BaseModel):
    id: str
    date: date
    dept: Optional[str] = None
    reason: Optional[str] = None
    location: Optional[str] = None


class Symptom(BaseModel):
    name: str
    code: Optional[str] = None
    coding_system: Optional[str] = None
    aliases: Optional[List[str]] = None


class Disease(BaseModel):
    code: str
    name: str
    cui: Optional[str] = None
    status: Optional[DiseaseStatus] = None


class Test(BaseModel):
    name: str
    loinc: Optional[str] = None
    category: Optional[str] = None
    value_range: Optional[dict] = None


class TestResult(BaseModel):
    id: str
    value: float
    unit: str
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    time: datetime
    flag: Optional[TestFlag] = None


class Medication(BaseModel):
    code: str
    name: str
    atc: Optional[str] = None
    form: Optional[str] = None


class Procedure(BaseModel):
    code: str
    name: str
    cpt: Optional[str] = None


class Clinician(BaseModel):
    id: str
    name: str
    specialty: Optional[str] = None
    npi: Optional[str] = None


class Guideline(BaseModel):
    id: str
    title: str
    source: str
    url: Optional[str] = None
    evidence_level: Optional[str] = None


class SourceDocument(BaseModel):
    source_id: str
    source_type: SourceType
    title: Optional[str] = None
    publisher: Optional[str] = None
    pub_date: Optional[date] = None
    url: Optional[str] = None
    hash_sha256: Optional[str] = None


class Assertion(BaseModel):
    assertion_id: str
    predicate: str
    time: Optional[datetime] = None
    negation: bool = False
    uncertainty: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)