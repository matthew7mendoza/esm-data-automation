import pytest
from pydantic import ValidationError
from backend.esm_data.models import (
    SpearAutomationError,
    DocumentExtractionError,
    CorruptedDocumentError,
    AgentConfigurationError,
    AgentExecutionError,
    RubricItemConfig,
    NoveltyEntrySchema,
    ComplianceScoringSchema,
    ComplianceCategoryGroup,
    MasterAuditPayloadSchema,
    AnswerPair,
    FormResponses,
    TaskStatusResponse,
    AuditRequest,
    TemplateCreateRequest,
)

class TestPydanticDomainModels:

    def test_compliance_scoring_schema_valid(self) -> None:
        payload = {
            "item_id": "1.1",
            "question": "Is the variable TAS?",
            "justification": "The text explicitly states the variable is TAS.",
            "answer": "Yes"
        }
        model = ComplianceScoringSchema(**payload)
        assert model.item_id == "1.1"
        assert model.question == "Is the variable TAS?"
        assert model.justification == "The text explicitly states the variable is TAS."
        assert model.answer == "Yes"

    def test_compliance_scoring_schema_invalid_answer(self) -> None:
        payload = {
            "item_id": "1.1",
            "question": "Is the variable TAS?",
            "justification": "Maybe.",
            "answer": "Maybe"
        }
        with pytest.raises(ValidationError):
            ComplianceScoringSchema(**payload)

    def test_compliance_scoring_schema_missing_fields(self) -> None:
        payload = {
            "item_id": "1.1",
            "answer": "Yes"
        }
        with pytest.raises(ValidationError):
            ComplianceScoringSchema(**payload)

    def test_rubric_item_config_valid(self) -> None:
        payload = {
            "id": "2.A",
            "question": "What is the numeric value?",
            "strategy": "Numeric"
        }
        model = RubricItemConfig(**payload)
        assert model.id == "2.A"
        assert model.question == "What is the numeric value?"
        assert model.strategy == "Numeric"

    def test_rubric_item_config_invalid_strategy(self) -> None:
        payload = {
            "id": "2.A",
            "question": "What is the numeric value?",
            "strategy": "InvalidStrategy"
        }
        with pytest.raises(ValidationError):
            RubricItemConfig(**payload)

    def test_novelty_entry_schema_valid(self) -> None:
        payload = {
            "relevance": 1,
            "originality": 2,
            "gap_addressing": 3,
            "non_obviousness": 0
        }
        model = NoveltyEntrySchema(**payload)
        assert model.relevance == 1
        assert model.originality == 2
        assert model.gap_addressing == 3
        assert model.non_obviousness == 0

    def test_novelty_entry_schema_invalid_bounds(self) -> None:
        with pytest.raises(ValidationError):
            NoveltyEntrySchema(relevance=2, originality=2, gap_addressing=3, non_obviousness=0)
        with pytest.raises(ValidationError):
            NoveltyEntrySchema(relevance=1, originality=4, gap_addressing=3, non_obviousness=0)
        with pytest.raises(ValidationError):
            NoveltyEntrySchema(relevance=1, originality=2, gap_addressing=-1, non_obviousness=0)

    def test_compliance_category_group_valid(self) -> None:
        item = ComplianceScoringSchema(
            item_id="1.1",
            question="Q1",
            justification="Justification",
            answer="Yes"
        )
        payload = {
            "category_name": "Category A",
            "items": [item]
        }
        model = ComplianceCategoryGroup(**payload)
        assert model.category_name == "Category A"
        assert len(model.items) == 1
        assert model.items[0].item_id == "1.1"

    def test_master_audit_payload_schema_valid(self) -> None:
        item = ComplianceScoringSchema(
            item_id="1.1",
            question="Q1",
            justification="Justification",
            answer="Yes"
        )
        group = ComplianceCategoryGroup(category_name="Cat", items=[item])
        model = MasterAuditPayloadSchema(categories=[group])
        assert len(model.categories) == 1
        assert model.categories[0].category_name == "Cat"

    def test_answer_pair_valid(self) -> None:
        model = AnswerPair(question="What is this?", answer="This is a test.")
        assert model.question == "What is this?"
        assert model.answer == "This is a test."

    def test_answer_pair_invalid_types(self) -> None:
        with pytest.raises(ValidationError):
            AnswerPair(question=["What is this?"], answer=42)

    def test_form_responses_valid(self) -> None:
        pair = AnswerPair(question="Q", answer="A")
        model = FormResponses(extracted_answers=[pair], missing_information=["Q2"])
        assert len(model.extracted_answers) == 1
        assert model.missing_information == ["Q2"]

    def test_task_status_response_valid(self) -> None:
        model = TaskStatusResponse(
            task_id="task-123",
            status="PENDING",
            custom_name="CustomName",
            report=None,
            source_context=None,
            detail=None
        )
        assert model.task_id == "task-123"
        assert model.status == "PENDING"
        assert model.custom_name == "CustomName"

    def test_audit_request_valid(self) -> None:
        model = AuditRequest(
            source_context="Context text",
            answers={"Q1": "Yes"},
            iterations=3
        )
        assert model.source_context == "Context text"
        assert model.answers == {"Q1": "Yes"}
        assert model.iterations == 3

    def test_template_create_request_valid(self) -> None:
        model = TemplateCreateRequest(
            name="DOI",
            description="DOI template",
            questions=["Q1", "Q2"]
        )
        assert model.name == "DOI"
        assert model.description == "DOI template"
        assert model.questions == ["Q1", "Q2"]

    def test_custom_exceptions(self) -> None:
        with pytest.raises(SpearAutomationError):
            raise SpearAutomationError("Base error")
        with pytest.raises(DocumentExtractionError):
            raise DocumentExtractionError("Extraction error")
        with pytest.raises(CorruptedDocumentError):
            raise CorruptedDocumentError("Corrupted error")
        with pytest.raises(AgentConfigurationError):
            raise AgentConfigurationError("Config error")
        with pytest.raises(AgentExecutionError):
            raise AgentExecutionError("Execution error")
