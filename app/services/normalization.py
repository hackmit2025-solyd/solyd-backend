"""
Medical data normalization service for units, dates, and codes
"""
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import re


class MedicalNormalizer:
    """Normalizes medical data to standard formats"""

    # Unit conversion maps
    UNIT_CONVERSIONS = {
        # Mass units to mg
        "g": 1000.0,
        "mg": 1.0,
        "mcg": 0.001,
        "ug": 0.001,
        "μg": 0.001,
        "kg": 1000000.0,
        "lb": 453592.0,
        "oz": 28349.5,

        # Volume units to mL
        "l": 1000.0,
        "ml": 1.0,
        "dl": 100.0,
        "μl": 0.001,
        "ul": 0.001,

        # Concentration normalizations
        "mg/l": 1.0,
        "g/l": 1000.0,
        "mg/dl": 10.0,
        "g/dl": 10000.0,
        "mmol/l": None,  # Requires molecular weight
        "meq/l": None,  # Requires valence
        "iu/l": None,  # Substance-specific
    }

    # Common lab test reference ranges
    REFERENCE_RANGES = {
        "CRP": {"unit": "mg/L", "low": 0, "high": 10},
        "WBC": {"unit": "10^9/L", "low": 4.0, "high": 11.0},
        "Hemoglobin": {"unit": "g/dL", "low": 12.0, "high": 17.5},
        "Glucose": {"unit": "mg/dL", "low": 70, "high": 100},
        "Creatinine": {"unit": "mg/dL", "low": 0.6, "high": 1.2},
        "ALT": {"unit": "U/L", "low": 7, "high": 56},
        "AST": {"unit": "U/L", "low": 10, "high": 40},
        "TSH": {"unit": "mIU/L", "low": 0.4, "high": 4.0},
    }

    # Date format patterns
    DATE_PATTERNS = [
        (r'\d{4}-\d{2}-\d{2}', '%Y-%m-%d'),
        (r'\d{2}/\d{2}/\d{4}', '%m/%d/%Y'),
        (r'\d{2}-\d{2}-\d{4}', '%m-%d-%Y'),
        (r'\d{1,2}/\d{1,2}/\d{4}', '%m/%d/%Y'),
        (r'\d{4}/\d{2}/\d{2}', '%Y/%m/%d'),
    ]

    def normalize_value_with_unit(self, value: Any, unit: str,
                                 target_unit: Optional[str] = None) -> Tuple[float, str]:
        """Normalize a value with its unit to standard format"""
        # Clean the value
        if isinstance(value, str):
            # Extract numeric value from string
            numeric_match = re.search(r'[-+]?\d*\.?\d+', value.replace(',', ''))
            if numeric_match:
                value = float(numeric_match.group())
            else:
                return (None, unit)

        value = float(value)
        unit = unit.lower().strip() if unit else ""

        # If no target unit specified, keep original
        if not target_unit:
            return (value, unit)

        target_unit = target_unit.lower().strip()

        # Check if conversion is possible
        if unit in self.UNIT_CONVERSIONS and target_unit in self.UNIT_CONVERSIONS:
            if self.UNIT_CONVERSIONS[unit] and self.UNIT_CONVERSIONS[target_unit]:
                # Convert to base unit then to target
                base_value = value * self.UNIT_CONVERSIONS[unit]
                target_value = base_value / self.UNIT_CONVERSIONS[target_unit]
                return (round(target_value, 4), target_unit)

        return (value, unit)

    def normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize date string to ISO format (YYYY-MM-DD)"""
        if not date_str:
            return None

        # Already in ISO format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # Try different date patterns
        for pattern, format_str in self.DATE_PATTERNS:
            if re.match(pattern, date_str):
                try:
                    dt = datetime.strptime(date_str, format_str)
                    return dt.date().isoformat()
                except ValueError:
                    continue

        # Try parsing relative dates
        date_lower = date_str.lower()
        if "yesterday" in date_lower:
            from datetime import timedelta
            return (datetime.now().date() - timedelta(days=1)).isoformat()
        elif "today" in date_lower:
            return datetime.now().date().isoformat()
        elif "tomorrow" in date_lower:
            from datetime import timedelta
            return (datetime.now().date() + timedelta(days=1)).isoformat()

        return None

    def normalize_test_result(self, test_name: str, value: Any,
                            unit: str) -> Dict[str, Any]:
        """Normalize test result with reference ranges and flags"""
        result = {"test": test_name, "value": value, "unit": unit}

        # Get reference range if available
        if test_name in self.REFERENCE_RANGES:
            ref = self.REFERENCE_RANGES[test_name]

            # Try to normalize to standard unit
            normalized_value, normalized_unit = self.normalize_value_with_unit(
                value, unit, ref["unit"]
            )

            if normalized_value is not None:
                result["value"] = normalized_value
                result["unit"] = normalized_unit
                result["ref_low"] = ref["low"]
                result["ref_high"] = ref["high"]

                # Add interpretation flag
                if normalized_value < ref["low"]:
                    result["flag"] = "L"
                elif normalized_value > ref["high"]:
                    result["flag"] = "H"
                else:
                    result["flag"] = "N"

        return result

    def normalize_medication_dose(self, dose_str: str) -> Dict[str, Any]:
        """Parse and normalize medication dosage"""
        if not dose_str:
            return {}

        dose_str = dose_str.lower()
        result = {}

        # Extract dose amount and unit
        dose_match = re.search(r'(\d+(?:\.\d+)?)\s*([a-zμ]+)', dose_str)
        if dose_match:
            amount = float(dose_match.group(1))
            unit = dose_match.group(2)

            # Normalize unit
            if unit in ["mcg", "ug", "μg"]:
                unit = "mcg"
            elif unit == "g":
                amount = amount * 1000
                unit = "mg"

            result["dose"] = amount
            result["unit"] = unit

        # Extract frequency
        freq_patterns = {
            r'once\s+daily|qd|od': 'once daily',
            r'twice\s+daily|bid|bd': 'twice daily',
            r'three\s+times\s+daily|tid|tds': 'three times daily',
            r'four\s+times\s+daily|qid|qds': 'four times daily',
            r'every\s+(\d+)\s+hours?': r'every \1 hours',
            r'prn|as\s+needed': 'as needed',
            r'qhs|at\s+bedtime': 'at bedtime',
            r'qam|in\s+the\s+morning': 'in the morning'
        }

        for pattern, replacement in freq_patterns.items():
            if re.search(pattern, dose_str):
                if r'\1' in replacement:
                    match = re.search(pattern, dose_str)
                    result["frequency"] = replacement.replace(r'\1', match.group(1))
                else:
                    result["frequency"] = replacement
                break

        # Extract route
        route_patterns = {
            r'po|oral|by\s+mouth': 'oral',
            r'iv|intravenous': 'IV',
            r'im|intramuscular': 'IM',
            r'sc|subq|subcutaneous': 'SC',
            r'topical|apply': 'topical',
            r'inhale|inhalation': 'inhalation',
            r'nasal': 'nasal',
            r'rectal|pr': 'rectal'
        }

        for pattern, route in route_patterns.items():
            if re.search(pattern, dose_str):
                result["route"] = route
                break

        return result

    def normalize_gender(self, gender_str: str) -> Optional[str]:
        """Normalize gender/sex to standard codes"""
        if not gender_str:
            return None

        gender_lower = gender_str.lower().strip()

        gender_map = {
            'male': 'M',
            'm': 'M',
            'man': 'M',
            'boy': 'M',
            'female': 'F',
            'f': 'F',
            'woman': 'F',
            'girl': 'F',
            'other': 'O',
            'o': 'O',
            'unknown': 'U',
            'u': 'U'
        }

        return gender_map.get(gender_lower, None)

    def normalize_department(self, dept_str: str) -> str:
        """Normalize department names"""
        if not dept_str:
            return ""

        dept_lower = dept_str.lower().strip()

        dept_map = {
            'er': 'Emergency',
            'ed': 'Emergency',
            'emergency': 'Emergency',
            'emergency room': 'Emergency',
            'emergency department': 'Emergency',
            'icu': 'ICU',
            'intensive care': 'ICU',
            'intensive care unit': 'ICU',
            'im': 'Internal Medicine',
            'internal': 'Internal Medicine',
            'internal medicine': 'Internal Medicine',
            'cardio': 'Cardiology',
            'cardiology': 'Cardiology',
            'neuro': 'Neurology',
            'neurology': 'Neurology',
            'ortho': 'Orthopedics',
            'orthopedics': 'Orthopedics',
            'peds': 'Pediatrics',
            'pediatrics': 'Pediatrics',
            'psych': 'Psychiatry',
            'psychiatry': 'Psychiatry',
            'ob': 'Obstetrics',
            'obgyn': 'Obstetrics/Gynecology',
            'ob/gyn': 'Obstetrics/Gynecology',
            'surgery': 'Surgery',
            'surg': 'Surgery',
            'radiology': 'Radiology',
            'rad': 'Radiology',
            'oncology': 'Oncology',
            'onc': 'Oncology',
        }

        for key, value in dept_map.items():
            if key in dept_lower:
                return value

        # Return original with proper capitalization if not found
        return dept_str.title()


# Singleton instance
normalizer = MedicalNormalizer()