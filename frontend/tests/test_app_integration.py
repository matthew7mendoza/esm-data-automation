from unittest.mock import MagicMock, patch
from streamlit.testing.v1 import AppTest

class TestStreamlitAppIntegration:

    @patch("frontend.app.fetch_server_templates")
    @patch("frontend.app.fetch_all_historical_tasks")
    def test_app_initializes_cleanly(self, mock_historical: MagicMock, mock_templates: MagicMock) -> None:
        mock_templates.return_value = ["TEMPLATE_A"]
        mock_historical.return_value = []

        at: AppTest = AppTest.from_file("frontend/app.py").run()

        assert not at.exception
        assert "run_state" in at.session_state
        assert at.session_state["run_state"] == "idle"
        assert at.session_state["job_running"] is False
        assert len(at.tabs) == 2
        assert "Document Generator" in at.tabs[0].label
        assert "LLM Judge Evaluation" in at.tabs[1].label
