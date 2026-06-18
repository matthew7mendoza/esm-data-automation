"""
Statistic metrics for evaluating LLM judge stability.
"""

import re
from collections import Counter
from typing import Literal

def calculate_percentage_agreement(verdicts: list[str]) -> float:

    """
    Computes the raw proportion of matching binary classifications. (Yes / No)
    """

    if not verdicts:
        return 0.0
    
    counter = Counter(verdicts)
    most_common_count = counter.most_common(1)[0][1]
    return (most_common_count / len(verdicts) * 100.0)

def calculate_gwets_ac1(verdicts: list[str]) -> float:

    """
    Calculates Gwet's AC1
    """

    total_runs = len(verdicts)
    if total_runs <= 1:
        return 1.0
    
    counts = Counter(verdicts)
    n_yes, n_no = counts.get("Yes", 0), counts.get("No", 0)

    # Observed consistent agreement in LLM's responses
    p_a = (n_yes * (n_yes - 1) + n_no * (n_no - 1)) / (total_runs * (total_runs - 1))

    # Classification chance agreements
    p_yes, p_no = n_yes / total_runs, n_no / total_runs
    p_e = 2 * p_yes * p_no if (p_yes * p_no) > 0 else 1.0

    if p_e == 1.0:
        return 1.0 if p_a == 1.0 else 0.0
    
    return (p_a - p_e) / (1.0 - p_e)

def calculate_fleiss_kappa(verdict_matrix: list[list[str]]) -> float:

    """
    Computes Fleiss' Kappa across multiple runs of LLM's responses (Yes / No) for consistency"
    """

    num_items = len(verdict_matrix)
    if num_items == 0:
        return 0.0
    
    num_runs = len(verdict_matrix[0])
    if num_runs <= 1:
        return 1.0
    
    row_counts = [[row.count("Yes"), row.count("No")] for row in verdict_matrix]
    p_i = [(count[0] ** 2 + count[1] ** 2 - num_runs) / (num_runs * (num_runs - 1)) for count in row_counts]
    p_mean = sum(p_i) / num_items

    p_yes = sum(count[0] for count in row_counts) / (num_items * num_runs)
    p_no = sum(count[1] for count in row_counts) / (num_items * num_runs)
    p_e = p_yes ** 2 + p_no ** 2

    if p_e == 1.0:
        return 1.0 if p_mean == 1.0 else 0.0
    
    return (p_mean - p_e) / (1.0 - p_e)


def calculate_reasoning_stability(
        justifications: list[str],
        strategy: Literal["Numeric", "Quote", "Assertion"]) -> float:
    
    """
    Isolates rationals and returns consistency percentages
    """
    total_runs = len(justifications)
    if total_runs == 0:
        return 0.0
    
    fingerprints = []
    for text in justifications:
        normalized = text.strip().lower()
        if strategy == "Numeric":
            match = re.search(r"\b\d+\b", normalized)
            fingerprints.append(match.group(0) if match else normalized)
        elif strategy == "Quote":
            quotes = re.findall(r'["\'](.*?)["\']', normalized)
            fingerprints.append(" ".join(quotes) if quotes else normalized)
        else:
            fingerprints.append(" ".join(re.sub(r"[^\w\s]", "", normalized).split()))

    cluster_counts = Counter(fingerprints)
    dominant_cluster_size = cluster_counts.most_common(1)[0][1]

    return (dominant_cluster_size / total_runs) * 100.0