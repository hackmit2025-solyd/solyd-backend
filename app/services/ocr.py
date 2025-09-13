"""
AWS Textract integration for OCR processing of medical documents
"""
import boto3
from typing import Dict, List, Optional, Any
import time
from app.config import settings
from app.services.s3 import S3Service


class TextractService:
    """OCR service using AWS Textract for medical documents"""

    def __init__(self):
        """Initialize AWS Textract client"""
        self.textract_client = boto3.client(
            'textract',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region
        )
        self.s3_service = S3Service()
        self.bucket_name = settings.s3_bucket_name

    def process_document_from_s3(self, s3_key: str,
                                feature_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Process document from S3 using Textract"""

        if not feature_types:
            # Default features for medical documents
            feature_types = ["TABLES", "FORMS"]

        try:
            # Start asynchronous document analysis
            response = self.textract_client.start_document_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': self.bucket_name,
                        'Name': s3_key
                    }
                },
                FeatureTypes=feature_types
            )

            job_id = response['JobId']
            print(f"Started Textract job: {job_id}")

            # Wait for job completion
            result = self._wait_for_job_completion(job_id)

            if result:
                # Process and structure the results
                return self._process_textract_results(result)
            else:
                return {"error": "Textract job failed or timed out"}

        except Exception as e:
            print(f"Textract processing error: {e}")
            return {"error": str(e)}

    def process_document_bytes(self, document_bytes: bytes,
                              feature_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Process document from bytes (for smaller documents < 5MB)"""

        if not feature_types:
            feature_types = ["TABLES", "FORMS"]

        try:
            # Synchronous processing for small documents
            response = self.textract_client.analyze_document(
                Document={'Bytes': document_bytes},
                FeatureTypes=feature_types
            )

            return self._process_textract_results(response)

        except Exception as e:
            print(f"Textract processing error: {e}")
            return {"error": str(e)}

    def _wait_for_job_completion(self, job_id: str, max_wait: int = 300) -> Optional[Dict]:
        """Wait for Textract job to complete"""
        start_time = time.time()

        while time.time() - start_time < max_wait:
            response = self.textract_client.get_document_analysis(JobId=job_id)

            status = response['JobStatus']
            print(f"Job {job_id} status: {status}")

            if status == 'SUCCEEDED':
                return self._get_full_results(job_id)
            elif status == 'FAILED':
                print(f"Textract job {job_id} failed")
                return None

            time.sleep(5)  # Wait 5 seconds before checking again

        print(f"Textract job {job_id} timed out")
        return None

    def _get_full_results(self, job_id: str) -> Dict:
        """Get all pages of results from Textract job"""
        pages = []
        next_token = None

        while True:
            if next_token:
                response = self.textract_client.get_document_analysis(
                    JobId=job_id,
                    NextToken=next_token
                )
            else:
                response = self.textract_client.get_document_analysis(JobId=job_id)

            pages.extend(response.get('Blocks', []))

            next_token = response.get('NextToken')
            if not next_token:
                break

        response['Blocks'] = pages
        return response

    def _process_textract_results(self, response: Dict) -> Dict[str, Any]:
        """Process and structure Textract results for medical documents"""

        blocks = response.get('Blocks', [])

        # Organize blocks by type
        block_map = {block['Id']: block for block in blocks}

        result = {
            "text": [],
            "tables": [],
            "forms": [],
            "metadata": {
                "pages": response.get('DocumentMetadata', {}).get('Pages', 0),
                "blocks_analyzed": len(blocks)
            }
        }

        # Extract different types of content
        for block in blocks:
            block_type = block.get('BlockType')

            if block_type == 'PAGE':
                # Page-level information
                continue

            elif block_type == 'LINE':
                # Extract text lines
                text = block.get('Text', '')
                confidence = block.get('Confidence', 0)
                if text and confidence > 50:  # Filter low confidence text
                    result["text"].append({
                        "text": text,
                        "confidence": confidence,
                        "page": block.get('Page', 1)
                    })

            elif block_type == 'TABLE':
                # Extract table data
                table_data = self._extract_table(block, block_map)
                if table_data:
                    result["tables"].append(table_data)

            elif block_type == 'KEY_VALUE_SET':
                # Extract form fields (key-value pairs)
                if 'KEY' in block.get('EntityTypes', []):
                    kv_pair = self._extract_key_value(block, block_map)
                    if kv_pair:
                        result["forms"].append(kv_pair)

        # Post-process for medical context
        result = self._extract_medical_sections(result)

        return result

    def _extract_table(self, table_block: Dict, block_map: Dict) -> Optional[Dict]:
        """Extract table data from Textract blocks"""
        try:
            rows = []
            cells = []

            # Get relationships
            relationships = table_block.get('Relationships', [])
            for relationship in relationships:
                if relationship['Type'] == 'CHILD':
                    for child_id in relationship.get('Ids', []):
                        cell_block = block_map.get(child_id)
                        if cell_block and cell_block['BlockType'] == 'CELL':
                            cells.append(cell_block)

            # Organize cells into rows
            if cells:
                # Sort cells by row and column
                cells.sort(key=lambda x: (x.get('RowIndex', 0), x.get('ColumnIndex', 0)))

                current_row = []
                current_row_index = 1

                for cell in cells:
                    row_index = cell.get('RowIndex', 1)

                    if row_index != current_row_index:
                        if current_row:
                            rows.append(current_row)
                        current_row = []
                        current_row_index = row_index

                    # Get cell text
                    cell_text = self._get_text_from_relationships(
                        cell.get('Relationships', []), block_map
                    )
                    current_row.append(cell_text)

                if current_row:
                    rows.append(current_row)

            return {
                "rows": rows,
                "confidence": table_block.get('Confidence', 0),
                "page": table_block.get('Page', 1)
            }

        except Exception as e:
            print(f"Error extracting table: {e}")
            return None

    def _extract_key_value(self, key_block: Dict, block_map: Dict) -> Optional[Dict]:
        """Extract key-value pair from form fields"""
        try:
            key_text = ""
            value_text = ""

            # Get key text
            key_relationships = key_block.get('Relationships', [])
            for relationship in key_relationships:
                if relationship['Type'] == 'CHILD':
                    key_text = self._get_text_from_relationships([relationship], block_map)

            # Find associated value
            for relationship in key_relationships:
                if relationship['Type'] == 'VALUE':
                    for value_id in relationship.get('Ids', []):
                        value_block = block_map.get(value_id)
                        if value_block:
                            value_relationships = value_block.get('Relationships', [])
                            for val_rel in value_relationships:
                                if val_rel['Type'] == 'CHILD':
                                    value_text = self._get_text_from_relationships(
                                        [val_rel], block_map
                                    )

            if key_text:
                return {
                    "key": key_text.strip(),
                    "value": value_text.strip() if value_text else "",
                    "confidence": key_block.get('Confidence', 0),
                    "page": key_block.get('Page', 1)
                }

        except Exception as e:
            print(f"Error extracting key-value: {e}")

        return None

    def _get_text_from_relationships(self, relationships: List[Dict],
                                    block_map: Dict) -> str:
        """Get text from relationship blocks"""
        text_parts = []

        for relationship in relationships:
            if relationship['Type'] == 'CHILD':
                for child_id in relationship.get('Ids', []):
                    child_block = block_map.get(child_id)
                    if child_block:
                        if child_block['BlockType'] in ['WORD', 'LINE']:
                            text_parts.append(child_block.get('Text', ''))
                        elif child_block['BlockType'] == 'SELECTION_ELEMENT':
                            if child_block.get('SelectionStatus') == 'SELECTED':
                                text_parts.append('✓')

        return ' '.join(text_parts)

    def _extract_medical_sections(self, result: Dict) -> Dict:
        """Extract medical-specific sections from OCR results"""

        # Common medical document sections
        medical_sections = {
            "patient_info": [],
            "vital_signs": [],
            "lab_results": [],
            "medications": [],
            "diagnoses": [],
            "procedures": [],
            "notes": []
        }

        # Process forms for medical fields
        for form_field in result.get("forms", []):
            key_lower = form_field["key"].lower()

            # Categorize by key patterns
            if any(term in key_lower for term in ["patient", "name", "dob", "mrn", "id"]):
                medical_sections["patient_info"].append(form_field)
            elif any(term in key_lower for term in ["bp", "blood pressure", "pulse", "temp",
                                                   "heart rate", "respiratory", "o2", "oxygen"]):
                medical_sections["vital_signs"].append(form_field)
            elif any(term in key_lower for term in ["lab", "test", "result", "crp", "wbc",
                                                   "glucose", "hemoglobin"]):
                medical_sections["lab_results"].append(form_field)
            elif any(term in key_lower for term in ["medication", "drug", "dose", "rx"]):
                medical_sections["medications"].append(form_field)
            elif any(term in key_lower for term in ["diagnosis", "dx", "icd", "condition"]):
                medical_sections["diagnoses"].append(form_field)
            elif any(term in key_lower for term in ["procedure", "surgery", "operation"]):
                medical_sections["procedures"].append(form_field)

        # Process tables for lab results
        for table in result.get("tables", []):
            if table["rows"]:
                # Check if it's a lab results table
                header = table["rows"][0] if table["rows"] else []
                if any("test" in str(cell).lower() or "result" in str(cell).lower()
                      for cell in header):
                    medical_sections["lab_results"].append({
                        "type": "table",
                        "data": table
                    })

        # Combine text into notes
        all_text = ' '.join([item["text"] for item in result.get("text", [])])
        if all_text:
            medical_sections["notes"].append({
                "type": "free_text",
                "content": all_text[:5000]  # Limit to 5000 chars
            })

        result["medical_sections"] = medical_sections
        return result


# Singleton instance
textract_service = TextractService()