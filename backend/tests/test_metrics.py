from typing import Literal
import pytest
from backend.esm_data.metrics import (
    calculate_percentage_agreement,
    calculate_gwets_ac1,
    calculate_reasoning_stability,
)

class TestMetricsEngine:

    @pytest.mark.parametrize("judgments, expected", [
        (["Yes", "Yes", "Yes"], 100.0),
        (["No", "No", "No", "No"], 100.0),
        (["Yes", "Yes", "No", "No"], 50.0),
        (["Yes", "No", "Yes"], 66.67),
    ])
    def test_calculate_percentage_agreement_valid(self, judgments: list[str], expected: float) -> None:
        result = calculate_percentage_agreement(judgments)
        assert round(result, 2) == expected

    def test_calculate_percentage_agreement_empty_list(self) -> None:
        result = calculate_percentage_agreement([])
        assert result == 0.0

    @pytest.mark.parametrize("judgments, expected_range", [
        (["Yes", "Yes", "Yes", "Yes", "Yes"], (0.9, 1.0)),
        (["Yes", "No", "Yes", "No", "Yes"], (-0.5, 0.5)),
        (["Yes"], (1.0, 1.0)),
        ([], (1.0, 1.0)),
    ])
    def test_calculate_gwets_ac1_boundaries(self, judgments: list[str], expected_range: tuple[float, float]) -> None:
        result = calculate_gwets_ac1(judgments)
        assert expected_range[0] <= result <= expected_range[1]

    @pytest.mark.parametrize("justifications, strategy, expected", [
        (["The value is 42.", "Found 42 on line 1.", "It was 100."], "Numeric", 66.67),
        (["It says 'hello' here.", "We read 'hello' now.", "Nothing."], "Quote", 66.67),
        (["A. B.", "A.  B", "C"], "Assertion", 66.67),
        ([], "Numeric", 0.0),
    ])
    def test_calculate_reasoning_stability_valid(
        self,
        justifications: list[str],
        strategy: Literal["Numeric", "Quote", "Assertion"],
        expected: float,
    ) -> None:
        result = calculate_reasoning_stability(justifications, strategy)
        assert round(result, 2) == expected
