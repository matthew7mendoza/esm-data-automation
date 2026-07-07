"""
Global variables for all of frontend
"""

from typing import Final

__all__ = [
    "BACKEND_URL",
    "MODEL_CONFIGURATIONS",
    "TEMPLATE_DESCRIPTIONS",
    "TEMPLATE_DISPLAY_NAMES",
    "TEMPLATE_SORT_ORDER",
]

BACKEND_URL: Final[str] = "http://localhost:8000"

# templates listed here appear first in the sidebar, in this order;
# any others keep the order the backend returns
TEMPLATE_SORT_ORDER: Final[list[str]] = ["README", "DMP"]

# maps the backend template key to a friendlier display label
TEMPLATE_DISPLAY_NAMES: Final[dict[str, str]] = {
    "DMP": "Data Management Plan",
    "README": "README",
}

# write a short description of each form here, shown under the page header
TEMPLATE_DESCRIPTIONS: Final[dict[str, str]] = {
    "DMP": (
        "A NOAA Data Management Plan describing the project's data: "
        "coverage, contacts, lineage, documentation, access, and preservation."
    ),
    "README": (
        "The README serves as the primary documentation for the dataset. It provides "
        "an overview of the dataset's contents, organization, file "
        "structure, variables, "
        "metadata, data formats, processing methods, quality assurance "
        "procedures, access "
        "information, licensing, and citation guidance. Its purpose is to help users "
        "understand, navigate, and correctly interpret the data for "
        "analysis and research.\n"
        "\n"
        "You can use this README Generator tool to create a 'first pass' "
        "at your README "
        "document. This 'first pass' will attempt to fill in as many "
        "fields as possible "
        "using the information submitted by the user. This tool is "
        "designed to facilitate "
        "and improve the users experience creating a README document "
        "through prompted and "
        "structured AI integration.\n"
        "\n"
        "To get started, you will upload documentation related to your dataset. "
        "Examples of this include:\n"
        "- Publications explicitly discussing the model or dataset to be "
        "described by the README.\n"
        "- Text files of extracted NetCDF metadata from files of the dataset.\n"
        "\n"
        "A completed README can be used to:\n"
        "- Publish alongside a dataset.\n"
        "- Submit to acquire a dataset DOI "
        "([Princeton Data Portal](https://datacommons.princeton.edu/describe/))\n"
        "\n"
        "*Note: This README Generator tool is a proof-of-concept "
        "application that utilizes "
        "the latest Google Gemini Large Language Model (LLM). Any and all information "
        "filled in by the AI can be modified or removed by the user as needed. It is "
        "highly recommended to review all generated fields for potential errors. User "
        "submitted information may be used for app improvement later on.*"
    ),
}

MODEL_CONFIGURATIONS: Final[dict[str, str]] = {"Gemini": "gemini", "Nvidia": "nemotron"}
