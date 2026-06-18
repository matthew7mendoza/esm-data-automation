"""
Executes multi-run compliance validation over the local inputs of LLM
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from collections import Counter

from google import genai
from google.genai import types

from src.schemas import MasterAuditPayloadSchema
from src.metrics_calculator import(
    calculate_percentage_agreement,
    calculate_gwets_ac1,
    calculate_fleiss_kappa,
    calculate_reasoning_stability
)

class StableLLMJudgeLab:

    """
    Testing framework for metadata evaluation.
    """

    def __init__(self, input_dir: str = "data/inputs", output_dir: str = "results/metrics"):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = genai.Client()

    def execute_multi_axis_evaluation(self, background: str, candidate_paste: str) -> str:

        """
        Sends clean string matricies directly to dev endpoint.
        """

        system_instruction = (
            "You are an elite, detached climate data compliance metrics auditor for NOAA GFDL.\n"
            "CRITICAL PROTOCOL:\n"
            "1. The candidate profile provided will be formatted as a Markdown table matrix. Parse its rows carefully.\n"
            "2. Locate and extract verbatim source text parameters and quotes BEFORE scoring.\n"
            "3. Fill out your reasoning trajectory to explain semantic mutations before setting values.\n"
            "4. Strictly categorize evaluations across explicit Objective and Subjective criteria fields."
        )

        user_prompt = (
            f"[CONTEXT: RAW TECHNICAL SOURCE DOCUMENTATION]\n{background}\n\n"
            f"[TARGET: COPY-PASTED COMPLIANCE MATRIX]\n{candidate_paste}"
        )

        response = self.client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=MasterAuditPayloadSchema,
                temperature=0.0,
            )
        )

        return response.text
    
    def run_stability_stress_test(self, prefix: str, k_iterations: int = 5) -> None:

        """
        Runs batch evaluation iterations over files to catch the stability trap.
        """

        paste_path = self.input_dir / f"{prefix}_paste.txt"
        source_path = self.input_dir / f"{prefix}_source.txt"

        if not (paste_path.exists() and source_path.exists()):
            print(f"Skipping profile [{prefix}]: Missing source or paste file.")
            return
        
        paste_content = paste_path.read_text(encoding="utf-8")
        source_content = source_path.read_text(encoding="utf-8")

        raw_runs_history = []
        for run_index in range(k_iterations):
            try:
                raw_output = self.execute_multi_axis_evaluation(source_content, paste_content)
                raw_runs_history.append(json.loads(raw_output))
            except Exception as err:
                print(f"Run failure on iteration # {run_index + 1}: {err}")
        
        if not raw_runs_history:
            return
        
        compiled_question_map: dict[str, dict[str, Any]] = {}
        for run in raw_runs_history:
            for category in run.get("categories", []):
                for item in category.get("items", []):
                    question_text = item.get("question")
                    if question_text not in compiled_question_map:
                        is_num = any(word in question_text.lower() for word in ["count", "word", "total"])
                        is_quote = any(word in question_text.lower() for word in ["verbatim", "string", "quote"])
                        strategy = "Numeric" if is_num else ("Quote" if is_quote else "Assertion")

                        compiled_question_map[question_text] = {"verdicts": [], "justifications": [], "strategy": strategy}
                    
                    compiled_question_map[question_text]["verdicts"].append(item.get("answer"))
                    compiled_question_map[question_text]["justifications"].append(item.get("justification"))

        final_metrics_report = {
            "metadata": {
                "profile_prefix": prefix,
                "execution_timestamp": datetime.now().isoformat(),
                "total_runs_k": len(raw_runs_history)
            },
            "item_level_stability_metrics": []
        }

        verdict_matrix_for_kappa = []
        for question_text, data in compiled_question_map.items():
            verdict_list, justification_list, strategy = data["verdicts"], data["justifications"], data["strategy"]
            verdict_matrix_for_kappa.append(verdict_list)

            final_metrics_report["item_level_stability_metrics"].append({
                "question": question_text,
                "inferred_strategy": strategy,
                "percentage_agreement_pa": round(calculate_percentage_agreement(verdict_list), 2),
                "gwets_ac1_gamma": round(calculate_gwets_ac1(verdict_list), 4),
                "reasoning_stability_r_stab": round(calculate_reasoning_stability(justification_list, strategy), 2),
                "raw_verdict_distribution": dict(Counter(verdict_list))
            })

        final_metrics_report["metadata"]["global_fleiss_kappa"] = round(
            calculate_fleiss_kappa(verdict_matrix_for_kappa), 4
        )

        output_file_path = self.output_dir / f"{prefix}_stability_trap_report.json"
        output_file_path.write_text(json.dumps(final_metrics_report, indent=4), encoding="utf-8")
        print(f"Compliance data report saved to -> {output_file_path}")
        
