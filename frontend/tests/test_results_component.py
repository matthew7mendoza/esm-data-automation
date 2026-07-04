from typing import Any
import pytest
from frontend.components.results import extract_source_assets

class TestResultsComponentDataParsing:

    @pytest.mark.parametrize("payload, expected_list", [
        ("--- SOURCE CONTENT ASSET: file1.txt ---\nData here", ["file1.txt"]),
        ("--- SOURCE CONTENT ASSET: doc_A.pdf ---\n\n--- SOURCE CONTENT ASSET: doc_B.md ---", ["doc_A.pdf", "doc_B.md"]),
        ("No explicit assets mapped in this document.", []),
        ("--- SOURCE CONTENT ASSET:  weird_space.txt  ---", ["weird_space.txt "])
    ])
    def test_extract_source_assets_regex(self, payload: str, expected_list: list[str]) -> None:
        results: list[str] = extract_source_assets(source_context=payload)
        assert results == expected_list

    def test_extract_source_assets_handles_none(self) -> None:
        results: list[str] = extract_source_assets(source_context=None)
        assert results == []
