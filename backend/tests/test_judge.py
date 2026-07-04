import asyncio
from unittest.mock import AsyncMock, MagicMock

import google.genai.errors
import openai

from backend.esm_data.judge import LLMJudge
from backend.esm_data.providers import LLMProvider


def test_llm_judge_initialization() -> None:
    """Test that LLMJudge instantiates and loads system instructions correctly."""
    provider: MagicMock = MagicMock(spec=LLMProvider)
    judge = LLMJudge(provider=provider)
    assert judge.provider is provider
    assert "climate data compliance auditor" in judge.system_instruction


def test_llm_judge_handles_api_error_gracefully() -> None:
    """Test that google.genai.errors.APIError is caught in _evaluate_single_node."""
    provider: MagicMock = MagicMock(spec=LLMProvider)
    
    # We mock generate_structured_async to raise google.genai.errors.APIError
    api_error = google.genai.errors.APIError(
        code=429,
        response_json={"error": {"message": "Simulated Google Gemini Quota/API Error"}},
    )
    provider.generate_structured_async = AsyncMock(side_effect=api_error)

    judge = LLMJudge(provider=provider)
    semaphore = asyncio.Semaphore(1)

    async def run_test() -> tuple[str, int, str, str]:
        return await judge._evaluate_single_node(
            item_id="Check.1",
            question="Is the dataset global?",
            run_index=0,
            source_content="The geography is global.",
            paste_content='{"Q1": "Yes"}',
            semaphore=semaphore,
        )

    item_id, run_index, verdict, justification = asyncio.run(run_test())

    assert item_id == "Check.1"
    assert run_index == 0
    assert verdict == "No"
    assert "Execution Exception Intercepted" in justification
    assert "Simulated Google Gemini Quota/API Error" in justification


def test_llm_judge_handles_openai_error_gracefully() -> None:
    """Test that openai.OpenAIError is caught in _evaluate_single_node."""
    provider: MagicMock = MagicMock(spec=LLMProvider)
    
    # We mock generate_structured_async to raise openai.OpenAIError
    openai_error = openai.OpenAIError("Simulated OpenAI API Error")
    provider.generate_structured_async = AsyncMock(side_effect=openai_error)

    judge = LLMJudge(provider=provider)
    semaphore = asyncio.Semaphore(1)

    async def run_test() -> tuple[str, int, str, str]:
        return await judge._evaluate_single_node(
            item_id="Check.2",
            question="Is the dataset global?",
            run_index=1,
            source_content="The geography is global.",
            paste_content='{"Q1": "Yes"}',
            semaphore=semaphore,
        )

    item_id, run_index, verdict, justification = asyncio.run(run_test())

    assert item_id == "Check.2"
    assert run_index == 1
    assert verdict == "No"
    assert "Execution Exception Intercepted" in justification
    assert "Simulated OpenAI API Error" in justification
