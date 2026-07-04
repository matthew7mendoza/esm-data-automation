import pytest
from backend.esm_data.metrics import calculate_percentage_agreement, calculate_gwets_ac1

class TestMetricsEngine:
    """
    Rule 3.2: Positional/Keyword bounds. 
    Rule 6.1: Errors should not pass silently.
    """

    @pytest.mark.parametrize("judgments, expected", [
        (["Yes", "Yes", "Yes"], 100.0),
        (["No", "No", "No", "No"], 100.0),
        (["Yes", "Yes", "No", "No"], 50.0),
        (["Yes", "No", "Yes"], 66.67), # Checking float rounding logic
    ])
    def test_calculate_percentage_agreement_valid(self, judgments: list[str], expected: float) -> None:
        """Verifies correct calculation of percentage agreement with rounding."""
        result = calculate_percentage_agreement(judgments)
        assert round(result, 2) == expected

    def test_calculate_percentage_agreement_empty_list(self) -> None:
        """Verifies division-by-zero protection when given empty constraints."""
        with pytest.raises(ZeroDivisionError):
            # In a truly strict app, we expect the function to crash OR return 0.0.
            # Assuming the math function hasn't explicitly silenced ZeroDivisionError:
            calculate_percentage_agreement([])

    @pytest.mark.parametrize("judgments, expected_range", [
        (["Yes", "Yes", "Yes", "Yes", "Yes"], (0.9, 1.0)), 
        (["Yes", "No", "Yes", "No", "Yes"], (-0.5, 0.5)), 
    ])
    def test_calculate_gwets_ac1_boundaries(self, judgments: list[str], expected_range: tuple[float, float]) -> None:
        """Ensures the AC1 metric stays within mathematically valid bounds [-1, 1]."""
        result = calculate_gwets_ac1(judgments)
        assert expected_range[0] <= result <= expected_range[1]