import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass, field, InitVar
from datetime import datetime
from pathlib import Path
from typing import Any
import yaml

from src.providers import LLMProvider
from src.models import (
    ComplianceScoringSchema,
    RubricItemConfig,
    AgentConfigurationError
)
from src.metrics import (
    calculate_gwets_ac1, 
    calculate_percentage_agreement,
    calculate_reasoning_stability
)

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class ItemAuditStream:
    """
    Stores and manages the grading history for a single form question.
    This class tracks how the AI answered one specific question across all test runs
    """
    item_id: str
    question: str
    strategy: str
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

    def compute_reliability(self) -> dict[str, Any]:
        """
        Calculate if the AI is reliable for any specific question by looking 
        at the distribution of the test runs
        """

        return {
            "question": f"[{self.item_id} {self.question}]",
            "inferred_strategy": self.strategy,
            "percentage_agreement_pa": round(calculate_percentage_agreement(self.verdicts), 2),
            "gwets_ac1_gamma": round(calculate_gwets_ac1(self.verdicts), 4),
            "reasoning_stability_r_stab": round(calculate_reasoning_stability(self.justifications, self.strategy), 2),
            "raw_dict_distribution": Counter(self.verdicts)
        }
    

class LLMJudge:
    """
    LLM Judge which evaluates the AI's answers to the questions
    """

    STRATEGY_KEYWORDS = {
        "Numeric": ["count", "word", "total", "volume", "number"],
        "Quote": ["verbatim", "string", "quote", "text", "url"]
    }

    provider: LLMProvider
    system_instruction: str

    def __init__(self, provider: LLMProvider) -> None:
        if not provider:
            raise ValueError("An active LLM API key must be provided!")
        self.provider = provider
        self.system_instruction = self._load_judge_instructions()

    def _load_judge_instructions(self) -> str:
        """
        Reads system instructionsfor the judge from templates.yaml file
        """

        config_path = Path(__file__).parent / "templates.yaml"
        if not config_path.exists():
            raise AgentConfigurationError(f"templates.yaml file missing at path: {config_path.resolve()}")
        
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
                return data["JUDGE_INSTRUCTIONS"]
        except KeyError as key_error:
            raise AgentConfigurationError("The requred key 'JUDGE_INSTRUCTIONS' was missing inside of templates.yaml") from key_error
        except Exception as yaml_error:
            raise AgentConfigurationError("Failed to cleanly decode exterminal YAML runtime template structure.") from yaml_error
        
    def _infer_evaluation_strategy(self, question_text: str) -> str:
        """
        Looks at the wording of the question to decide if the AI 
        should look for a number, quote, or a general fact
        """

        question_lower = question_text.lower()
        for strategy, keywords in self.STRATEGY_KEYWORDS.items():
            if any(word in question_lower for word in keywords):
                return strategy
        return "Assertion"
    
    async def run_stability_stress_test_async(
        self,
        source_content: str,
        paste_content: str,
        prefix_label: str,
        i_iterations: int = 5
    ) -> dict[str, Any]:
        """
        Parsed generated answers, runs Judges in parralel for a single question across multiple runs
        returns accuracy report
        """

        try:
            raw_answers: dict[str, Any] = json.loads(paste_content)
        except Exception as parse_error:
            logger.error(f"Failed to parse paste_content string to map execution rubric: {parse_error}")
            return {}
        
        rubric_items: list[RubricItemConfig] = []
        for index, (question, _) in enumerate(raw_answers.items(), start=1):
            strategy = self._infer_evaluation_strategy(question)
            rubric_items.append(RubricItemConfig(
                id=f"Check.{index}",
                question=question,
                strategy=strategy
            ))

        if not rubric_items:
            return {}
        
        audit_registry: dict[str, ItemAuditStream] = {
            item.id: ItemAuditStream(
                item_id=item.id,
                question=item.question,
                strategy=item.strategy,
                iterations=i_iterations
            )
            for item in rubric_items
        }

        semaphore = asyncio.Semaphore(10)

        async def worker_task(item_id: str, question: str, run_index: int) -> tuple[str, int, str, str]:
            """
            Helper function that handles single grading call to Judge
            """

            async with semaphore:
                user_prompt = (
                    f"CHECKPOINT REQUIREMENT TO EVALUATE:\n{question}\n\n"
                    f"[SOURCE DOCUMENT CONTEXT]\n{source_content}\n\n"
                    f"[COMPLIANCE OUTPUT TO EVALUATE]\n{paste_content}"
                )
                try:
                    response: ComplianceScoringSchema = await self.provider.generate_structured_async(
                        prompt=user_prompt,
                        system_instruction=self.system_instruction,
                        response_schema=ComplianceScoringSchema
                    )
                    if response:
                        return item_id, run_index, response.answer, response.justification
                
                except Exception as execution_error:
                    logger.error(f"Async evaluation fault on item {item_id}, run {run_index}: {execution_error}")
                    return item_id, run_index, "No", f"Execution Exception Intercepted: {execution_error}"
                
                return item_id, run_index, "No", "Omitted due to empty response."
            
        tasks = [
            worker_task(stream.item_id, stream.question, run_index)
            for stream in audit_registry.values()
            for run_index in range(i_iterations)
        ]
            
        # Fire all API tasks in parralel!
        results = await asyncio.gather(*tasks)

        for item_id, run_index, verdict, justification in results:
            stream = audit_registry[item_id]
            stream.verdicts[run_index] = verdict
            stream.justifications[run_index] = justification 

        item_metrics = [stream.compute_reliability() for stream in audit_registry.values()]

        global_gwet_average = 0.0
        if item_metrics:
            global_gwet_average = sum(metric["gwets_ac1_gamma"] for metric in item_metrics) / len(item_metrics)

        return {
            "metadata": {
                "profile_prefix": prefix_label,
                "execution_timestamp": datetime.now().isoformat(),
                "total_runs_i": i_iterations,
                "global_gwets_ac1": round(global_gwet_average, 4)
            },
            "item_level_stability_metrics": item_metrics
        }
