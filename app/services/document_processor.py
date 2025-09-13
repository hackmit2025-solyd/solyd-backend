"""
Document processing service using Apache Tika and S3
Handles PDF, Word, and other document formats
"""

import os
import tempfile
from typing import Dict, Any, List
import boto3
from tika import parser
from pathlib import Path
from app.config import settings
from app.services.s3 import S3Service
from app.services.ocr import TextractService


class DocumentProcessor:
    """Process various document formats from S3"""

    def __init__(self):
        """Initialize document processor with S3 and OCR services"""
        self.s3_service = S3Service()
        self.textract_service = TextractService()
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

        # Initialize Tika (will download Java runtime if needed on first use)
        os.environ["TIKA_SERVER_JAR"] = (
            "https://repo1.maven.org/maven2/org/apache/tika/tika-server/2.9.1/tika-server-2.9.1.jar"
        )

    def process_s3_document(self, s3_key: str, use_ocr: bool = False) -> Dict[str, Any]:
        """
        Process document from S3 - download, extract text, then delete local copy

        Args:
            s3_key: S3 object key
            use_ocr: Whether to use OCR for image-based PDFs
        """

        # Create temporary file
        with tempfile.NamedTemporaryFile(
            suffix=self._get_file_extension(s3_key), delete=False
        ) as tmp_file:
            temp_path = tmp_file.name

            try:
                # Download from S3 to temp file
                print(f"Downloading {s3_key} from S3...")
                self.s3_client.download_file(settings.s3_bucket_name, s3_key, temp_path)

                # Get file metadata
                file_metadata = self.s3_service.get_file_metadata(s3_key)

                # Process based on file type
                file_extension = self._get_file_extension(s3_key).lower()

                if file_extension in [".pdf", ".PDF"]:
                    result = self._process_pdf(temp_path, s3_key, use_ocr)
                elif file_extension in [".doc", ".docx", ".DOC", ".DOCX"]:
                    result = self._process_word(temp_path)
                elif file_extension in [".txt", ".TXT"]:
                    result = self._process_text(temp_path)
                elif file_extension in [
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".tiff",
                    ".PNG",
                    ".JPG",
                    ".JPEG",
                    ".TIFF",
                ]:
                    # Use OCR for images
                    result = self._process_image_ocr(s3_key)
                else:
                    # Try generic Tika extraction
                    result = self._process_with_tika(temp_path)

                # Add metadata
                result["metadata"] = {
                    "s3_key": s3_key,
                    "file_size": file_metadata.get("content_length"),
                    "content_type": file_metadata.get("content_type"),
                    "last_modified": str(file_metadata.get("last_modified")),
                    "file_extension": file_extension,
                }

                return result

            finally:
                # Always delete temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    print(f"Deleted temporary file: {temp_path}")

    def _get_file_extension(self, file_path: str) -> str:
        """Get file extension from path"""
        return Path(file_path).suffix

    def _process_pdf(
        self, file_path: str, s3_key: str, use_ocr: bool
    ) -> Dict[str, Any]:
        """Process PDF document"""

        # First try Tika for text extraction
        parsed = parser.from_file(file_path)

        content = parsed.get("content", "")
        metadata = parsed.get("metadata", {})

        # Check if PDF has extractable text
        has_text = content and len(content.strip()) > 100

        result = {
            "content": content,
            "pages": metadata.get("xmpTPg:NPages", 1),
            "title": metadata.get("title", ""),
            "author": metadata.get("Author", ""),
            "creation_date": metadata.get("Creation-Date", ""),
            "has_text": has_text,
        }

        # If no text or OCR requested, use Textract
        if use_ocr or not has_text:
            print(f"Using OCR for {s3_key}...")
            ocr_result = self.textract_service.process_document_from_s3(s3_key)

            if "error" not in ocr_result:
                # Combine OCR text with metadata
                ocr_text = " ".join(
                    [item["text"] for item in ocr_result.get("text", [])]
                )
                if ocr_text:
                    result["content"] = ocr_text
                    result["ocr_used"] = True
                    result["tables"] = ocr_result.get("tables", [])
                    result["forms"] = ocr_result.get("forms", [])
                    result["medical_sections"] = ocr_result.get("medical_sections", {})

        return result

    def _process_word(self, file_path: str) -> Dict[str, Any]:
        """Process Word document"""
        parsed = parser.from_file(file_path)

        return {
            "content": parsed.get("content", ""),
            "metadata": parsed.get("metadata", {}),
            "title": parsed.get("metadata", {}).get("title", ""),
            "author": parsed.get("metadata", {}).get("Author", ""),
            "page_count": parsed.get("metadata", {}).get("Page-Count", 1),
        }

    def _process_text(self, file_path: str) -> Dict[str, Any]:
        """Process plain text file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            return {
                "content": content,
                "lines": content.count("\n") + 1,
                "characters": len(content),
            }
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read()

            return {
                "content": content,
                "lines": content.count("\n") + 1,
                "characters": len(content),
                "encoding": "latin-1",
            }

    def _process_image_ocr(self, s3_key: str) -> Dict[str, Any]:
        """Process image file with OCR"""
        print(f"Processing image {s3_key} with OCR...")

        ocr_result = self.textract_service.process_document_from_s3(
            s3_key, feature_types=["TABLES", "FORMS"]
        )

        if "error" in ocr_result:
            return {"content": "", "error": ocr_result["error"], "ocr_used": True}

        # Extract text from OCR results
        text_items = ocr_result.get("text", [])
        content = " ".join([item["text"] for item in text_items])

        return {
            "content": content,
            "ocr_used": True,
            "tables": ocr_result.get("tables", []),
            "forms": ocr_result.get("forms", []),
            "medical_sections": ocr_result.get("medical_sections", {}),
            "confidence": sum(item["confidence"] for item in text_items)
            / len(text_items)
            if text_items
            else 0,
        }

    def _process_with_tika(self, file_path: str) -> Dict[str, Any]:
        """Generic document processing with Tika"""
        try:
            parsed = parser.from_file(file_path)

            return {
                "content": parsed.get("content", ""),
                "metadata": parsed.get("metadata", {}),
                "status": parsed.get("status", 200),
            }
        except Exception as e:
            print(f"Tika processing error: {e}")
            return {"content": "", "error": str(e)}

    def extract_medical_content(self, content: str) -> Dict[str, List[str]]:
        """Extract medical-relevant content from text"""

        medical_content = {
            "patient_info": [],
            "symptoms": [],
            "diagnoses": [],
            "medications": [],
            "lab_results": [],
            "procedures": [],
            "vital_signs": [],
        }

        # Split content into lines for analysis
        lines = content.split("\n")

        for line in lines:
            line_lower = line.lower()

            # Patient information patterns
            if any(
                term in line_lower
                for term in ["patient", "name:", "dob:", "mrn:", "id:"]
            ):
                medical_content["patient_info"].append(line.strip())

            # Symptoms patterns
            elif any(
                term in line_lower
                for term in ["symptom", "complain", "present", "report"]
            ):
                medical_content["symptoms"].append(line.strip())

            # Diagnosis patterns
            elif any(
                term in line_lower
                for term in ["diagnosis", "diagnosed", "impression", "assessment"]
            ):
                medical_content["diagnoses"].append(line.strip())

            # Medication patterns
            elif any(
                term in line_lower
                for term in ["medication", "prescribed", "rx:", "drug"]
            ):
                medical_content["medications"].append(line.strip())

            # Lab results patterns
            elif any(
                term in line_lower
                for term in ["lab", "test", "result", "value", "range"]
            ):
                medical_content["lab_results"].append(line.strip())

            # Procedure patterns
            elif any(
                term in line_lower
                for term in ["procedure", "surgery", "operation", "performed"]
            ):
                medical_content["procedures"].append(line.strip())

            # Vital signs patterns
            elif any(
                term in line_lower
                for term in [
                    "bp:",
                    "blood pressure",
                    "pulse:",
                    "temp:",
                    "respiratory",
                    "oxygen",
                    "heart rate",
                ]
            ):
                medical_content["vital_signs"].append(line.strip())

        # Remove empty categories
        medical_content = {k: v for k, v in medical_content.items() if v}

        return medical_content

    def batch_process_s3_documents(
        self, s3_keys: List[str], use_ocr: bool = False
    ) -> List[Dict[str, Any]]:
        """Process multiple documents from S3"""
        results = []

        for s3_key in s3_keys:
            try:
                result = self.process_s3_document(s3_key, use_ocr)
                result["status"] = "success"
                results.append(result)
            except Exception as e:
                results.append({"s3_key": s3_key, "status": "error", "error": str(e)})

        return results


# Singleton instance
document_processor = DocumentProcessor()
