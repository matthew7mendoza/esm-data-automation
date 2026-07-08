
from unittest.mock import MagicMock, patch

import pytest

from frontend.components.results import (
    extract_source_assets,
    render_answers_and_missing_sections,
)


class MockSessionState(dict[str, object]):
    """
    A dictionary subclass that allows attribute access to mock
    Streamlit's session state.
    """

    def __getattr__(self, name: str) -> object:
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name: str, value: object) -> None:
        self[name] = value


class TestResultsComponentDataParsing:
    @pytest.mark.parametrize(
        "payload, expected_list",
        [
            ("--- SOURCE CONTENT ASSET: file1.txt ---\nData here", ["file1.txt"]),
            (
                "--- SOURCE CONTENT ASSET: doc_A.pdf ---\n\n"
                "--- SOURCE CONTENT ASSET: doc_B.md ---",
                ["doc_A.pdf", "doc_B.md"],
            ),
            ("No explicit assets mapped in this document.", []),
            ("--- SOURCE CONTENT ASSET:  weird_space.txt  ---", ["weird_space.txt "]),
        ],
    )
    def test_extract_source_assets_regex(
        self, payload: str, expected_list: list[str]
    ) -> None:
        results: list[str] = extract_source_assets(source_context=payload)
        assert results == expected_list

    def test_extract_source_assets_handles_none(self) -> None:
        results: list[str] = extract_source_assets(source_context=None)
        assert results == []


class TestResultsComponentRender:
    @patch("frontend.components.results.st")
    @patch("frontend.components.results.update_task_report")
    def test_render_answers_and_missing_sections_no_task_id(
        self, _mock_update: MagicMock, mock_st: MagicMock
    ) -> None:
        mock_st.session_state = MockSessionState()
        render_answers_and_missing_sections()
        mock_st.header.assert_not_called()

    @patch("frontend.components.results.st")
    @patch("frontend.components.results.update_task_report")
    def test_render_answers_and_missing_sections_success(
        self, mock_update: MagicMock, mock_st: MagicMock
    ) -> None:
        session_state = MockSessionState(
            {
                "current_task_id": "test-task",
                "generator_report": {
                    "extracted_answers": {"Question 1": "Answer 1"},
                    "missing_information": ["Question 2"],
                },
            }
        )
        mock_st.session_state = session_state

        mock_form = MagicMock()
        mock_st.form.return_value = mock_form

        tab_ext = MagicMock()
        tab_miss = MagicMock()
        mock_st.tabs.return_value = (tab_ext, tab_miss)

        mock_st.text_area.side_effect = ["Answer 1 Edited", "Answer 2 Filled"]

        col1 = MagicMock()
        mock_st.columns.return_value = (col1, MagicMock())

        mock_st.form_submit_button.return_value = True
        mock_update.return_value = True

        render_answers_and_missing_sections()

        mock_update.assert_called_once_with(
            task_id="test-task",
            extracted_answers={
                "Question 1": "Answer 1 Edited",
                "Question 2": "Answer 2 Filled",
            },
            missing_information=["Question 2"],
        )
        mock_st.toast.assert_called_once_with("Changes saved successfully!")
        mock_st.rerun.assert_called_once()
        assert session_state.generator_report == {
            "extracted_answers": {
                "Question 1": "Answer 1 Edited",
                "Question 2": "Answer 2 Filled",
            },
            "missing_information": ["Question 2"],
        }
