"""
Global variables for all of frontend
"""

from typing import Final

__all__ = ["BACKEND_URL", "MODEL_CONFIGURATIONS"]

BACKEND_URL: Final[str] = "http://localhost:8000"

MODEL_CONFIGURATIONS: Final[dict[str, str]] = {"Gemini": "gemini", "Nvidia": "nemotron"}
