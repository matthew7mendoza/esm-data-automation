import pytest
from pydantic import ValidationError
from backend.esm_data.models import ComplianceScoringSchema, ExtractedQAItem

class TestPydanticDomainModels:
    """
    Rule 4.3: Mandate immutable containers.
    Rule 1.1: Guard clauses (Pydantic handles this before logic executes).
    """

    def test_compliance_schema_valid_strict(self) -> None:
        """Ensures proper mapping of valid data into the Compliance model."""
        payload = {
            "answer": "Yes",
            "justification": "The text explicitly states the variable is TAS."
        }
        model = ComplianceScoringSchema(**payload)
        assert model.answer == "Yes"
        assert model.justification.startswith("The text explicitly")

    def test_compliance_schema_rejects_invalid_enum(self) -> None:
        """Ensures Literal/Enum bounds are strictly enforced (Rule 2.8)."""
        payload = {
            "answer": "Maybe", # Invalid! Should only accept Literal Yes/No/Partial
            "justification": "Not sure."
        }
        with pytest.raises(ValidationError) as exc_info:
            ComplianceScoringSchema(**payload)
        
        # Verify the error is specifically tied to the 'answer' field
        assert "answer" in str(exc_info.value)

    def test_extracted_qa_item_type_coercion(self) -> None:
        """Ensures the schema does not silently accept completely mistyped data."""
        payload = {
            "question": ["What is the variable?"], # Invalid: Expected str, got List
            "answer": 42 # Invalid: Expected str, got int
        }
        with pytest.raises(ValidationError):
            ExtractedQAItem(**payload)