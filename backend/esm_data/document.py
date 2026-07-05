"""
Convert files into structured string formats
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Final

from markitdown import MarkItDown

from backend.esm_data.models import CorruptedDocumentError, DocumentExtractionError

__all__ = ["EXTRACTOR_MAP", "extract_text"]

logger = logging.getLogger(__name__)
_converter: MarkItDown = MarkItDown()


def _extract_plain_text(path: Path, /) -> str:
    """
    Reads data files
    """
    try:
        return path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as decode_error:
        logger.error(
            f"Encoding mismatch on text parsing for: {path.name}", exc_info=True
        )
        raise CorruptedDocumentError(
            f"File '{path.name}' contains invalid non UTF-8 characters"
        ) from decode_error


def _extract_complex_doc(path: Path, /) -> str:
    """
    Reads complex files to markdown
    """

    try:
        result = _converter.convert(str(path))
        return result.text_content.strip()
    except OSError as os_error:
        logger.error(f"OS access error when reading {path.name}", exc_info=True)
        raise DocumentExtractionError(
            f"System unable to proccess file read at '{path.name}'"
        ) from os_error
    except ValueError as val_error:
        logger.error(f"MarkItDown unable to parse {path.name}", exc_info=True)
        raise CorruptedDocumentError(
            f"Invalid structure mapping in: '{path.name}'"
        ) from val_error


EXTRACTOR_MAP: Final[dict[str, Callable[[Path], str]]] = {
    ".txt": _extract_plain_text,
    ".md": _extract_plain_text,
    ".csv": _extract_plain_text,
    ".pdf": _extract_complex_doc,
    ".docx": _extract_complex_doc,
    ".xlsx": _extract_complex_doc,
    ".pptx": _extract_complex_doc,
}


def extract_text(file_path: str | Path, /) -> str:
    """
    Maps file extensions to correct text extractor
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found {path.absolute()}")

    if not (extractor_function := EXTRACTOR_MAP.get(path.suffix.lower())):
        raise ValueError(
            f"Unsupported file format mapping request: '{path.suffix.lower()}'"
        )

    return extractor_function(path).strip()
