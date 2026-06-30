"""
Pure statistical formula utilities measuring agreement distributions and inter-rater reliability metrics.
The Judge returns a list of ["Yes", "Yes", "No", "Yes"...] representing whether the filled out answers were accurate.
The functions here determine whether the list of the Judge's evalautions are consistent or not
"""

import re
from collections import Counter
from collections.abc import Callable
from typing import Literal


# (Dominant Votes / Total Votes) * 100
def calculate_percentage_agreement(verdicts: list[str]) -> float:
    """Computes the raw percentage proportion of matching binary classifications."""
    if not verdicts:
        return 0.0
    counter = Counter(verdicts)

    # most_common(1) -> order highest to lowest
    # [0][1] -> get number from highest tuple for most common count
    most_common_count = counter.most_common(1)[0][1]
    return (most_common_count / len(verdicts)) * 100.0


# (Actual Agreement - Chance Agreement) / (1 - Chance Agreement)
def calculate_gwets_ac1(verdicts: list[str]) -> float:
    """Calculates Gwet's AC1 configuration index adjusted for extreme trait rarity distributions."""
    total_runs = len(verdicts)
    if total_runs <= 1:
        return 1.0
    
    counts = Counter(verdicts)
    # counts.get(..., 0) -> get frequency of vote, default to 0 if none exist
    n_yes, n_no = counts.get("Yes", 0), counts.get("No", 0)

    # p_a -> calculate actual proportion of matching handshake pairs
    p_a = (n_yes * (n_yes - 1) + n_no * (n_no - 1)) / (total_runs * (total_runs - 1))
    p_yes, p_no = n_yes / total_runs, n_no / total_runs
    # p_e -> calculate chance baseline by multiplying opposites instead of squaring
    p_e = 2 * p_yes * p_no if (p_yes * p_no) > 0 else 1.0

    if p_e == 1.0:
        return 1.0 if p_a == 1.0 else 0.0
    
    return (p_a - p_e) / (1.0 - p_e)


# Helper functions for calculate_reasoning_stabiliy
def _extract_numeric(text: str) -> str:
    regex_match = re.search(r"\b\d+\b", text)
    return regex_match.group(0) if regex_match else text

def _extract_quote(text: str) -> str:
    quotes = re.findall(r'["\'](.*?)["\']', text)
    return " ".join(quotes) if quotes else text

def _extract_assertion(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", "", text).split())

STRATEGY_REGISTRY: dict[str, Callable[[str], str]] = {
    "Numeric": _extract_numeric,
    "Quote": _extract_quote,
    "Assertion": _extract_assertion
}

# (Size of Largest Identical Text Pile / Total Explanations Collected) * 100
def calculate_reasoning_stability(
    justifications: list[str],
    strategy: Literal["Numeric", "Quote", "Assertion"]
) -> float:
    """
    Pulls numbers and quotes from the AI's reasons and counts how many times 
    the same rationals appears to see whether answers are consistent 
    """

    total_runs = len(justifications)
    if total_runs == 0:
        return 0.0
    
    fingerprints = []

    extractor = STRATEGY_REGISTRY.get(strategy, _extract_assertion)

    for text in justifications:
        normalized = text.strip().lower()
        fingerprints.append(extractor(normalized))
    
    cluster_counts = Counter(fingerprints)
    dominant_cluster_size = cluster_counts.most_common(1)[0][1]
    return (dominant_cluster_size / total_runs) * 100.0