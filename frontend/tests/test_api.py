from typing import Any, cast
from unittest.mock import MagicMock, patch

import requests

from backend.esm_data.models import TaskId
from frontend.api import (
    fetch_all_historical_tasks,
    fetch_server_templates,
    get_task_profile,
    update_task_report,
)
from frontend.protocols import TaskProfileDict


class TestFrontendAPIClient:
    @patch("frontend.api.requests.get")
    def test_fetch_server_templates_success(self, mock_get: MagicMock) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["CUSTOM_DOC", "README"]
        mock_get.return_value = mock_response

        result: list[str] = fetch_server_templates()
        assert result == ["CUSTOM_DOC", "README"]
        mock_get.assert_called_once()

    @patch("frontend.api.requests.get")
    def test_fetch_server_templates_fallback_on_timeout(
        self, mock_get: MagicMock
    ) -> None:
        mock_get.side_effect = requests.exceptions.Timeout("Connection lost")
        result: list[str] = fetch_server_templates()
        assert result == ["DMP", "README"]

    @patch("frontend.api.requests.get")
    def test_fetch_server_templates_non_200(self, mock_get: MagicMock) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        result: list[str] = fetch_server_templates()
        assert result == ["DMP", "README"]

    @patch("frontend.api.requests.get")
    def test_get_task_profile_success(self, mock_get: MagicMock) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"task_id": "1234", "status": "COMPLETED"}
        mock_get.return_value = mock_response

        result: TaskProfileDict | None = get_task_profile(task_id=TaskId("1234"))
        assert result == cast(Any, {"task_id": "1234", "status": "COMPLETED"})

    @patch("frontend.api.requests.get")
    def test_get_task_profile_suppresses_error_and_returns_none(
        self, mock_get: MagicMock
    ) -> None:
        mock_get.side_effect = requests.exceptions.ConnectionError("Server dead")
        result: TaskProfileDict | None = get_task_profile(task_id=TaskId("1234"))
        assert result is None

    @patch("frontend.api.requests.get")
    def test_get_task_profile_non_200_returns_none(self, mock_get: MagicMock) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        result: TaskProfileDict | None = get_task_profile(task_id=TaskId("1234"))
        assert result is None

    @patch("frontend.api.requests.get")
    def test_fetch_all_historical_tasks_success(self, mock_get: MagicMock) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"task_id": "1234"}]
        mock_get.return_value = mock_response

        result: list[dict[str, object]] = fetch_all_historical_tasks()
        assert result == [{"task_id": "1234"}]

    @patch("frontend.api.requests.get")
    def test_fetch_all_historical_tasks_returns_empty_list_on_fail(
        self, mock_get: MagicMock
    ) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result: list[dict[str, object]] = fetch_all_historical_tasks()
        assert result == []

    @patch("frontend.api.requests.patch")
    def test_update_task_report_success(self, mock_patch: MagicMock) -> None:
        mock_response: MagicMock = MagicMock()
        mock_response.status_code = 200
        mock_patch.return_value = mock_response

        result: bool = update_task_report(
            task_id="1234", extracted_answers={"Q1": "A1"}, missing_information=[]
        )
        assert result is True
        mock_patch.assert_called_once()

    @patch("frontend.api.requests.patch")
    def test_update_task_report_failure(self, mock_patch: MagicMock) -> None:
        mock_patch.side_effect = requests.exceptions.Timeout("Connection timed out")
        result: bool = update_task_report(
            task_id="1234", extracted_answers={"Q1": "A1"}, missing_information=[]
        )
        assert result is False
