import pytest
from datetime import date, datetime
from pydantic import ValidationError
from app.models.nodes import (
    Patient,
    Encounter,
    Symptom,
    Disease,
    Test,
    TestResult,
    Medication,
    SourceDocument,
    Assertion,
    Sex,
    DiseaseStatus,
    TestFlag,
    SourceType,
)


class TestNodeModels:
    def test_patient_model(self):
        """Test Patient model"""
        patient = Patient(
            id="P123", dob=date(1980, 1, 15), sex=Sex.MALE, age=44, de_identified=True
        )

        assert patient.id == "P123"
        assert patient.sex == Sex.MALE
        assert patient.age == 44
        assert patient.de_identified is True

    def test_patient_model_minimal(self):
        """Test Patient model with minimal data"""
        patient = Patient(id="P123")

        assert patient.id == "P123"
        assert patient.dob is None
        assert patient.sex is None
        assert patient.de_identified is True  # Default

    def test_encounter_model(self):
        """Test Encounter model"""
        encounter = Encounter(
            id="E567",
            date=date(2025, 9, 13),
            dept="Internal Medicine",
            reason="Fever",
            location="Room 101",
        )

        assert encounter.id == "E567"
        assert encounter.date == date(2025, 9, 13)
        assert encounter.dept == "Internal Medicine"

    def test_symptom_model(self):
        """Test Symptom model"""
        symptom = Symptom(
            name="fever",
            code="SNOMED:386661006",
            coding_system="SNOMED",
            aliases=["pyrexia", "high temperature"],
        )

        assert symptom.name == "fever"
        assert symptom.code == "SNOMED:386661006"
        assert len(symptom.aliases) == 2

    def test_disease_model(self):
        """Test Disease model"""
        disease = Disease(
            code="ICD10:J10",
            name="Influenza",
            cui="C0021400",
            status=DiseaseStatus.SUSPECTED,
        )

        assert disease.code == "ICD10:J10"
        assert disease.name == "Influenza"
        assert disease.status == DiseaseStatus.SUSPECTED

    def test_test_model(self):
        """Test Test model"""
        test = Test(
            name="CRP",
            loinc="1988-5",
            category="lab",
            value_range={"low": 0, "high": 10, "unit": "mg/L"},
        )

        assert test.name == "CRP"
        assert test.loinc == "1988-5"
        assert test.value_range["unit"] == "mg/L"

    def test_test_result_model(self):
        """Test TestResult model"""
        test_result = TestResult(
            id="TR001",
            value=12.3,
            unit="mg/L",
            ref_low=0.0,
            ref_high=10.0,
            time=datetime(2025, 9, 13, 10, 30),
            flag=TestFlag.HIGH,
        )

        assert test_result.id == "TR001"
        assert test_result.value == 12.3
        assert test_result.flag == TestFlag.HIGH

    def test_medication_model(self):
        """Test Medication model"""
        medication = Medication(
            code="RxNorm:198440",
            name="Acetaminophen",
            atc="N02BE01",
            form="tablet",
        )

        assert medication.code == "RxNorm:198440"
        assert medication.name == "Acetaminophen"
        assert medication.form == "tablet"

    def test_source_document_model(self):
        """Test SourceDocument model"""
        source_doc = SourceDocument(
            source_id="doc_001",
            source_type=SourceType.EMR,
            title="Clinical Note",
            publisher="Hospital System",
            pub_date=date(2025, 9, 13),
            url="https://example.com/doc",
            hash_sha256="abc123def456",
        )

        assert source_doc.source_id == "doc_001"
        assert source_doc.source_type == SourceType.EMR
        assert source_doc.title == "Clinical Note"

    def test_assertion_model(self):
        """Test Assertion model"""
        assertion = Assertion(
            assertion_id="A1",
            predicate="HAS_SYMPTOM",
            time=datetime(2025, 9, 13, 10, 0),
            negation=False,
            uncertainty=False,
            confidence=0.95,
        )

        assert assertion.assertion_id == "A1"
        assert assertion.predicate == "HAS_SYMPTOM"
        assert assertion.confidence == 0.95
        assert assertion.negation is False

    def test_assertion_confidence_validation(self):
        """Test Assertion confidence validation"""
        # Valid confidence
        assertion = Assertion(
            assertion_id="A1", predicate="HAS_SYMPTOM", confidence=0.5
        )
        assert assertion.confidence == 0.5

        # Invalid confidence (>1.0)
        with pytest.raises(ValidationError):
            Assertion(assertion_id="A2", predicate="HAS_SYMPTOM", confidence=1.5)

        # Invalid confidence (<0.0)
        with pytest.raises(ValidationError):
            Assertion(assertion_id="A3", predicate="HAS_SYMPTOM", confidence=-0.1)

    def test_sex_enum(self):
        """Test Sex enum values"""
        assert Sex.MALE.value == "M"
        assert Sex.FEMALE.value == "F"
        assert Sex.OTHER.value == "O"

    def test_disease_status_enum(self):
        """Test DiseaseStatus enum values"""
        assert DiseaseStatus.CONFIRMED.value == "confirmed"
        assert DiseaseStatus.SUSPECTED.value == "suspected"
        assert DiseaseStatus.RULED_OUT.value == "ruled_out"

    def test_source_type_enum(self):
        """Test SourceType enum values"""
        assert SourceType.EMR.value == "EMR"
        assert SourceType.PDF.value == "PDF"
        assert SourceType.MSD.value == "MSD"
        assert SourceType.PAPER.value == "PAPER"
        assert SourceType.MANUAL.value == "MANUAL"
