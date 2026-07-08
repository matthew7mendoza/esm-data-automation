from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest


def mock_api_requests_get(
    request_url: str,
    *_positional_arguments: object,
    **_keyword_arguments: object,
) -> MagicMock:
    """
    Mock function for requests.get to return template list or empty task list.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    is_templates_url = "api/templates" in request_url
    if not is_templates_url:
        mock_response.json.return_value = []
        return mock_response

    mock_response.json.return_value = ["README", "TEMPLATE_A"]
    return mock_response


class TestStreamlitAppIntegration:
    @patch("requests.get")
    def test_app_initializes_cleanly(
        self,
        mock_get: MagicMock,
    ) -> None:
        mock_get.side_effect = mock_api_requests_get

        app_test_instance: AppTest = AppTest.from_file("frontend/app.py").run()

        assert not app_test_instance.exception
        assert "run_state" in app_test_instance.session_state
        assert app_test_instance.session_state["run_state"] == "idle"
        assert app_test_instance.session_state["job_running"] is False

        # the landing page is the overview placeholder, no workflow tabs yet
        assert app_test_instance.session_state["selected_template"] == "OVERVIEW"
        assert len(app_test_instance.tabs) == 0

        # navigating to a template page reveals the workflow tabs
        app_test_instance.sidebar.selectbox(key="template_selectbox").set_value(
            "TEMPLATE_A"
        ).run()
        assert not app_test_instance.exception
        assert len(app_test_instance.tabs) == 2
        assert "Document Generator" in app_test_instance.tabs[0].label
        assert "LLM Judge Evaluation" in app_test_instance.tabs[1].label

    @patch("requests.get")
    def test_app_preserves_page_during_job_run(
        self,
        mock_get: MagicMock,
    ) -> None:
        mock_get.side_effect = mock_api_requests_get

        app_test_instance: AppTest = AppTest.from_file("frontend/app.py").run()
        assert not app_test_instance.exception

        # first navigate to TEMPLATE_A to set selected_template
        app_test_instance.sidebar.selectbox(key="template_selectbox").set_value(
            "TEMPLATE_A"
        ).run()
        assert not app_test_instance.exception
        assert app_test_instance.session_state["selected_template"] == "TEMPLATE_A"

        # simulate job running state
        app_test_instance.session_state["job_running"] = True
        app_test_instance.run()
        assert not app_test_instance.exception

        # verify that the selected template is preserved and does not reset to OVERVIEW
        assert app_test_instance.session_state["selected_template"] == "TEMPLATE_A"
