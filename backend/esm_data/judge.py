from __future__ import annotations

import asyncio
import itertools
import json
import logging
from collections import Counter
from dataclasses import InitVar, dataclass, field
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Final, Literal, Never, TypedDict, cast

import google.genai.errors
import openai
import yaml

from backend.esm_data.metrics import (
    calculate_gwets_ac1,
    calculate_percentage_agreement,
    calculate_reasoning_stability,
)
from backend.esm_data.models import (
    AgentConfigurationError,
    ComplianceScoringSchema,
    ItemId,
    RubricItemConfig,
)
from backend.esm_data.providers import LLMProvider

__all__ = [
    "AuditReportMetadata",
    "AuditStressTestReport",
    "ItemAuditStream",
    "LLMJudge",
    "QuestionRealiabilityMetrics",
]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ItemAuditStream:
    """
    Stores and manages the grading history for a single form question.
    This class tracks how the AI answered one specific question across all test runs
    """

    item_id: ItemId
    question: str
    strategy: Literal["Numeric", "Quote", "Assertion"]
    iterations: InitVar[int]

    verdicts: list[str] = field(init=False)
    justifications: list[str] = field(init=False)

    def __post_init__(self, iterations: int) -> None:
        """
        Based off # of test runs, pre-allocate empty placeholder list
        to accomodate the # of test runs
        """

        self.verdicts = ["No"] * iterations
        self.justifications = ["Omitted due to execution failure."] * iterations

    def __repr__(self) -> str:
        return (
            f"ItemAuditStream(item_id={self.item_id!r}, "
            f"strategy={self.strategy!r}, iterations={len(self.verdicts)})"
        )

    def __str__(self) -> str:
        """logging string"""
        return (
            f"AuditStream[{self.item_id}] (Strategy: {self.strategy}) "
            f"-> Questions: '{self.question[:40]}...'"
        )

    def compute_reliability(self) -> QuestionRealiabilityMetrics:
        """
        Calculate if the AI is reliable for any specific question by looking
        at the distribution of the test runs
        """

        return {
            "question": f"[{self.item_id} {self.question}]",
            "inferred_strategy": self.strategy,
            "percentage_agreement_pa": round(
                calculate_percentage_agreement(self.verdicts), 2
            ),
            "gwets_ac1_gamma": round(calculate_gwets_ac1(self.verdicts), 4),
            "reasoning_stability_r_stab": round(
                calculate_reasoning_stability(self.justifications, self.strategy), 2
            ),
            "raw_dict_distribution": Counter(self.verdicts),
        }


class QuestionRealiabilityMetrics(TypedDict):
    question: str
    inferred_strategy: str
    percentage_agreement_pa: float
    gwets_ac1_gamma: float
    reasoning_stability_r_stab: float
    raw_dict_distribution: Counter[str]


class AuditReportMetadata(TypedDict):
    profile_prefix: str
    execution_timestamp: str
    total_runs_i: int
    global_gwets_ac1: float


class AuditStressTestReport(TypedDict):
    metadata: AuditReportMetadata
    item_level_stability_metrics: list[QuestionRealiabilityMetrics]


class LLMJudge:
    """
    LLM Judge which evaluates the AI's answers to the questions
    """

    __slots__ = ("provider", "system_instruction")

    STRATEGY_KEYWORDS: Final[dict[str, list[str]]] = {
        "Numeric": ["count", "word", "total", "volume", "number"],
        "Quote": ["verbatim", "string", "quote", "text", "url"],
    }

    provider: LLMProvider
    system_instruction: str

    def __init__(self, provider: LLMProvider, instructions: str | None = None) -> None:
        if not provider:
            raise ValueError("An active LLM API key must be provided!")
        self.provider = provider
        self.system_instruction = (
            instructions
            if instructions is not None
            else self._load_judge_instructions()
        )

    def __repr__(self) -> str:
        """Technical output string"""
        return f"LLMJudge(provider={self.provider!r})"

    def __str__(self) -> str:
        """readable logging string"""
        engine_name = self.provider.__class__.__name__
        return f"LLM Judge Node [Activate Evaluator Engine: {engine_name}]"

    def _load_judge_instructions(self) -> str:
        """
        Reads system instructionsfor the judge from templates.yaml file
        """
        ### POTENTIAL NAME CHANGE, BEWARE POTENTIAL NAME CHANGE
        ### WHEN YOU CHANGE THE NAME CHANGE UPDATE THE DIRECTORY PATH
        ## ALERT
        config_path = Path(str(files("backend.esm_data"))) / "templates.yaml"
        if not config_path.exists():
            raise AgentConfigurationError(
                f"templates.yaml file missing at path: {config_path.resolve()}"
            )

        try:
            with open(config_path, encoding="utf-8") as file:
                data = yaml.safe_load(file)
                return cast(str, data["JUDGE_INSTRUCTIONS"])
        except KeyError as key_error:
            raise AgentConfigurationError(
                "The required key 'JUDGE_INSTRUCTIONS' was missing "
                "inside of templates.yaml"
            ) from key_error
        except (OSError, yaml.YAMLError) as serialization_error:
            raise AgentConfigurationError(
                "Failed to cleanly decode external YAML runtime template structure..."
            ) from serialization_error

    def _infer_evaluation_strategy(
        self, question_text: str
    ) -> Literal["Numeric", "Quote", "Assertion"]:
        """
        Looks at the wording of the question to decide if the AI
        should look for a number, quote, or a general fact
        """

        question_lower = question_text.lower()
        for strategy, keywords in self.STRATEGY_KEYWORDS.items():
            if any(word in question_lower for word in keywords):
                return cast(Literal["Numeric", "Quote", "Assertion"], strategy)
        return "Assertion"

    async def _evaluate_single_node(
        self,
        *,
        item_id: str,
        question: str,
        run_index: int,
        source_content: str,
        paste_content: str,
        semaphore: asyncio.Semaphore,
    ) -> tuple[str, int, str, str]:
        """
        Handles isolated async grading call
        """

        async with semaphore:
            user_prompt = (
                f"CHECKPOINT REQUIREMENT TO EVALUATE:\n{question}\n\n"
                f"[SOURCE DOCUMENT CONTEXT]\n{source_content}\n\n"
                f"[COMPLIANCE OUTPUT TO EVALUATE]\n{paste_content}"
            )

            try:
                response: ComplianceScoringSchema = (
                    await self.provider.generate_structured_async(
                        prompt=user_prompt,
                        system_instruction=self.system_instruction,
                        response_schema=ComplianceScoringSchema,
                    )
                )

                if not response:
                    return item_id, run_index, "No", "Omitted due to empty response."

                return item_id, run_index, response.answer, response.justification

            except (
                openai.OpenAIError,
                google.genai.errors.APIError,
                ValueError,
                TypeError,
                RuntimeError,
            ) as api_operational_fault:
                logger.error(
                    "Async evaluation operational fault on item "
                    f"{item_id}, run {run_index}: {api_operational_fault}"
                )
                return (
                    item_id,
                    run_index,
                    "No",
                    f"Execution Exception Intercepted: {api_operational_fault}",
                )

    async def run_stability_stress_test_async(
        self,
        *,
        source_content: str,
        paste_content: str,
        prefix_label: str,
        i_iterations: int = 5,
    ) -> AuditStressTestReport | dict[str, Never]:
        """
        Parsed generated answers, runs Judges in parallel for a single
        question across multiple runs and returns accuracy report.
        """

        try:
            raw_answers: dict[str, str] = json.loads(paste_content)
        except json.JSONDecodeError as string_parse_fault:
            logger.error(
                "Failed to parse paste_content string to map execution "
                f"rubric schema: {string_parse_fault}"
            )
            return {}

        rubric_items: list[RubricItemConfig] = [
            RubricItemConfig(
                id=f"Check.{index}",
                question=question,
                strategy=self._infer_evaluation_strategy(question),
            )
            for index, (question, _) in enumerate(raw_answers.items())
        ]

        if not rubric_items:
            return {}

        audit_registry: dict[str, ItemAuditStream] = {
            item.id: ItemAuditStream(
                item_id=ItemId(item.id),
                question=item.question,
                strategy=item.strategy,
                iterations=i_iterations,
            )
            for item in rubric_items
        }

        semaphore = asyncio.Semaphore(10)

        tasks = [
            self._evaluate_single_node(
                item_id=stream.item_id,
                question=stream.question,
                run_index=run_index,
                source_content=source_content,
                paste_content=paste_content,
                semaphore=semaphore,
            )
            for stream, run_index in itertools.product(
                audit_registry.values(), range(i_iterations)
            )
        ]

        # Fire all API tasks in parralel!
        results = await asyncio.gather(*tasks)

        for item_id, run_index, verdict, justification in results:
            stream = audit_registry[item_id]
            stream.verdicts[run_index] = verdict
            stream.justifications[run_index] = justification

        item_metrics = [
            stream.compute_reliability() for stream in audit_registry.values()
        ]

        global_gwet_average = 0.0
        if item_metrics:
            global_gwet_average = sum(
                metric["gwets_ac1_gamma"] for metric in item_metrics
            ) / len(item_metrics)

        return {
            "metadata": {
                "profile_prefix": prefix_label,
                "execution_timestamp": datetime.now().isoformat(),
                "total_runs_i": i_iterations,
                "global_gwets_ac1": round(global_gwet_average, 4),
            },
            "item_level_stability_metrics": item_metrics,
        }
