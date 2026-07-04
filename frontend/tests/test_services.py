from unittest.mock import MagicMock, patch
import requests
import pytest
from frontend.services import send_audit_request, send_generation_request

class TestFrontendServices:

    @patch("frontend.services.st")
    @patch("frontend.services.requests.post")
    def test_send_audit_request_success_flow(self, mock_post: MagicMock, mock_st: MagicMock) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 200
        fake_metrics: dict[str, object] = {
            "metadata": {"global_gwets_ac1": 0.95},
            "item_level_stability_metrics": []
        }
        mock_response.json.return_value = fake_metrics
        mock_post.return_value = mock_response

        mock_st.session_state = MagicMock()

        result: dict[str, object] | None = send_audit_request(
            chosen_engine="Gemini",
            answers={"Q1": "Yes"},
            judge_iterations=3,
            source_context="Mock Context"
        )

        assert result == fake_metrics
        mock_st.success.assert_called_with("Audit complete!")
        mock_st.metric.assert_called_with("Agreement score (Gwet's AC1)", 0.95)

    @patch("frontend.services.st")
    @patch("frontend.services.requests.post")
    def test_send_audit_request_handles_server_rejection(self, mock_post: MagicMock, mock_st: MagicMock) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {"detail": "Validation Error"}
        mock_post.return_value = mock_response

        result: dict[str, object] | None = send_audit_request(
            chosen_engine="Gemini",
            answers={},
            judge_iterations=2,
            source_context=""
        )

        assert result is None
        mock_st.error.assert_called_with("Audit server error: Validation Error")

    @patch("frontend.services.st")
    @patch("frontend.services.requests.post")
    def test_send_audit_request_network_error(self, mock_post: MagicMock, mock_st: MagicMock) -> None:
        mock_post.side_effect = requests.exceptions.Timeout("Timeout")

        result: dict[str, object] | None = send_audit_request(
            chosen_engine="Gemini",
            answers={},
            judge_iterations=2,
            source_context=""
        )

        assert result is None
        mock_st.error.assert_any_call("Communication loss with audit server: Timeout")

    @patch("frontend.services.time.sleep")
    @patch("frontend.services.get_task_profile")
    @patch("frontend.services.st")
    @patch("frontend.services.requests.post")
    def test_send_generation_request_success(
        self,
        mock_post: MagicMock,
        mock_st: MagicMock,
        mock_get_profile: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"task_id": "task-abc"}
        mock_post.return_value = mock_response

        mock_st.session_state = MagicMock()
        mock_st.empty.return_value = MagicMock()

        mock_get_profile.side_effect = [
            {"status": "PENDING"},
            {"status": "COMPLETED", "report": "some_report", "source_context": "some_context", "custom_name": "MyTest"}
        ]

        mock_file: MagicMock = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.getvalue.return_value = b"bytes"
        mock_file.type = "application/pdf"

        send_generation_request(
            target_document="DMP",
            chosen_engine="Gemini",
            uploaded_files=[mock_file],
            custom_name="MyTest"
        )

        mock_st.success.assert_called_with("Answers successfully written!")
        assert mock_st.session_state.current_task_id == "task-abc"
        assert mock_st.session_state.current_task_custom_name == "MyTest"

    @patch("frontend.services.st")
    @patch("frontend.services.requests.post")
    def test_send_generation_request_network_error(self, mock_post: MagicMock, mock_st: MagicMock) -> None:
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection fail")

        mock_file: MagicMock = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.getvalue.return_value = b"bytes"
        mock_file.type = "application/pdf"

        send_generation_request(
            target_document="DMP",
            chosen_engine="Gemini",
            uploaded_files=[mock_file],
        )

        mock_st.error.assert_called_with("Could not reach background API layer... Error: Connection fail")
