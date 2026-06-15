import logging
from pathlib import Path
from markitdown import MarkItDown

from src.exceptions import DocumentExtractionError, CorruptedDocumentError

logger = logging.getLogger(__name__)
_converter = MarkItDown()

def _extract_plain_text(path: Path) -> str:
    """
    Handles text files.
    """
    try:
        return path.read_text(encoding = "utf-8").strip()
    
    except UnicodeDecodeError as decode_err:
        logger.error("Encoding failure in %s: %s", path.name, decode_err)
        raise CorruptedDocumentError(f"File {path.name} is not valid UTF-8 text.") from decode_err

    
def _extract_complex_doc(path: Path) -> str:
    """
    Microsoft's tool to convert PDFs, DOCX, XLSX, ect... into Markdown,
    easier for LLM to comprehend.
    """

    try:
        result = _converter.convert(str(path))
        return result.text_content.strip()
    except OSError as os_err:
        logger.error("OS Error while accessing %s: %s", path.name, os_err)
        raise DocumentExtractionError(f"OS unable to read {path.name}") from os_err
    except ValueError as val_err:
        logger.error("MarkItDown failed to parse %s: %s", path.name, val_err)
        raise CorruptedDocumentError(f"Corrupted or invalid structure in {path.name}") from val_err

EXTRACTOR_MAP = {
    ".txt": _extract_plain_text,
    ".md": _extract_plain_text,
    ".csv": _extract_plain_text,
    ".pdf": _extract_complex_doc,
    ".docx": _extract_complex_doc,
    ".xlsx": _extract_complex_doc,
    ".pptx": _extract_complex_doc
}

def extract_text(file_path: str | Path) -> str:
    """
    Reads files and extracts text based off file format.
    Supported Formats: .txt, .md, .csv, .pdf, .docx, .xlsx, .pptx
    """

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Could not find file: {path.absolute()}")
    
    extension = path.suffix.lower()
    extractor_function = EXTRACTOR_MAP.get(path.suffix.lower())

    if not extractor_function:
        raise ValueError(f"Unsupported file type: {extension}")
    
    return extractor_function(path).strip()