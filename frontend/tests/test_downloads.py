from unittest.mock import MagicMock, patch

from frontend.views.generator import _render_step_three_download


class TestDownloadFileNaming:
    @patch("frontend.views.generator.st")
    @patch("frontend.views.generator.build_final_document_string")
    def test_download_filename_custom_name_sanitized(
        self, mock_build: MagicMock, mock_st: MagicMock
    ) -> None:
        mock_st.session_state = {"current_task_custom_name": "Project*#1/Cool"}
        mock_st.radio.return_value = "Markdown (.md)"
        mock_build.return_value = "# Final Doc"

        _render_step_three_download(
            target_document="DMP", extracted={}, missing=[], disabled=False
        )

        mock_st.download_button.assert_called_once_with(
            label="Download Document (.md)",
            data="# Final Doc",
            file_name="Project_#1_Cool.md",
            mime="text/markdown",
            type="primary",
            disabled=False,
        )

    @patch("frontend.views.generator.st")
    @patch("frontend.views.generator.build_final_document_string")
    def test_download_filename_fallback_to_template(
        self, mock_build: MagicMock, mock_st: MagicMock
    ) -> None:
        mock_st.session_state = {"current_task_custom_name": ""}
        mock_st.radio.return_value = "Markdown (.md)"
        mock_build.return_value = "# Final Doc"

        _render_step_three_download(
            target_document="DMP", extracted={}, missing=[], disabled=False
        )

        mock_st.download_button.assert_called_once_with(
            label="Download Document (.md)",
            data="# Final Doc",
            file_name="DMP_completed.md",
            mime="text/markdown",
            type="primary",
            disabled=False,
        )
