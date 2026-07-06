from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest


class TestStreamlitAppIntegration:
    @patch("frontend.app.fetch_server_templates")
    @patch("frontend.app.fetch_all_historical_tasks")
    @patch("frontend.components.sidebar.requests.get")
    def test_app_initializes_cleanly(
        self, mock_get: MagicMock, mock_historical: MagicMock, mock_templates: MagicMock
    ) -> None:
        mock_templates.return_value = ["TEMPLATE_A"]
        mock_historical.return_value = []

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        at: AppTest = AppTest.from_file("frontend/app.py").run()

        assert not at.exception
        assert "run_state" in at.session_state
        assert at.session_state["run_state"] == "idle"
        assert at.session_state["job_running"] is False

        # the landing page is the overview placeholder, no workflow tabs yet
        assert at.session_state["selected_template"] == "OVERVIEW"
        assert len(at.tabs) == 0

        # navigating to a template page reveals the workflow tabs
        at.sidebar.button(key="template_page_TEMPLATE_A").click().run()
        assert not at.exception
        assert len(at.tabs) == 2
        assert "Document Generator" in at.tabs[0].label
        assert "LLM Judge Evaluation" in at.tabs[1].label
