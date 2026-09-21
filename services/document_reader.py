"""
Document reader functions - extract text from various file formats.

Supports: TXT, RTF, PDF, DOCX, DOC, HTML, ZIP archives.
"""

import re
import zipfile
from pathlib import Path

try:
    from PyPDF2 import PdfReader

    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    from docx import Document

    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# =============================================================================
# Module-level constants
# =============================================================================


def _get_supported_formats() -> list[str]:
    """Get list of supported file formats based on available libraries."""
    formats = ["txt", "rtf", "zip"]
    if PYPDF2_AVAILABLE or PDFPLUMBER_AVAILABLE:
        formats.append("pdf")
    if DOCX_AVAILABLE:
        formats.extend(["docx", "doc"])
    if BS4_AVAILABLE:
        formats.append("html")
    return formats


# Compute once at module import
SUPPORTED_FORMATS = _get_supported_formats()


# =============================================================================
# Main reading functions
# =============================================================================


def read_file(filepath: str) -> str:
    """
    Read text content from a file.

    Args:
        filepath: Path to the file

    Returns:
        Extracted text content or error message
    """
    path = Path(filepath)
    if not path.exists():
        return f"[Error] File not found: {filepath}"

    ext = path.suffix.lower().lstrip(".")

    # No extension - try to detect content
    if not ext:
        if _is_html_content(filepath):
            return _read_html(filepath)
        return _read_txt(filepath)

    # Map extension to reader function
    readers = {
        "txt": _read_txt,
        "pdf": _read_pdf,
        "docx": _read_docx,
        "doc": _read_docx,
        "rtf": _read_rtf,
        "html": _read_html,
        "htm": _read_html,
        "zip": _read_zip,
    }

    reader = readers.get(ext)
    if reader:
        return reader(filepath)

    return f"[Unsupported format] {ext}: {filepath}"


def read_directory(directory: str, recursive: bool = True) -> str:
    """
    Read all supported files from a directory.

    Args:
        directory: Path to the directory
        recursive: Whether to search subdirectories

    Returns:
        Combined text content from all files
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return ""

    files = list(dir_path.rglob("*")) if recursive else list(dir_path.glob("*"))
    files = sorted([f for f in files if f.is_file() and not f.name.startswith(".")])

    results = []
    results.append(f"=== Directory Content: {dir_path.name} ===")

    for filepath in files:
        ext = filepath.suffix.lower().lstrip(".")
        if ext not in SUPPORTED_FORMATS and ext != "zip" and ext:
            continue

        content = read_file(str(filepath))
        if len(content) > 10000:
            content = content[:10000] + "\n[... truncated ...]"

        results.append(f"\n{'='*40}\nFile: {filepath.relative_to(dir_path)}\n{'='*40}")
        results.append(content)

    return "\n".join(results)


# =============================================================================
# Format-specific readers
# =============================================================================


def _read_txt(filepath: str) -> str:
    """Read text file with encoding detection."""
    encodings = ["utf-8", "cp1251", "utf-16", "iso-8859-5"]
    for encoding in encodings:
        try:
            with open(filepath, encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _read_pdf(filepath: str) -> str:
    """Read PDF file using pdfplumber or PyPDF2."""
    text = []

    if PDFPLUMBER_AVAILABLE:
        try:
            with pdfplumber.open(filepath) as pdf:
                text = [p.extract_text() or "" for p in pdf.pages]
            return "\n".join(text).strip()
        except Exception:
            pass

    if PYPDF2_AVAILABLE:
        try:
            reader = PdfReader(filepath)
            text = [p.extract_text() or "" for p in reader.pages]
            return "\n".join(text).strip()
        except Exception as e:
            return str(e)

    return ""


def _read_docx(filepath: str) -> str:
    """Read DOCX/DOC file using python-docx."""
    if not DOCX_AVAILABLE:
        return ""

    try:
        doc = Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs]

        tables = []
        for table in doc.tables:
            for row in table.rows:
                tables.append(" | ".join([c.text.strip() for c in row.cells]))

        return "\n".join(paragraphs + tables).strip()
    except Exception as e:
        return str(e)


def _read_rtf(filepath: str) -> str:
    """Read RTF file (basic parsing)."""
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Remove RTF formatting codes
        text = re.sub(r"\\a-z+\\d*", "", content)
        text = re.sub(r"[{}]", "", text)
        return re.sub(r"\\.[^ ]+", "", text).strip()
    except Exception as e:
        return str(e)


def _read_html(filepath: str) -> str:
    """Read HTML file using BeautifulSoup."""
    if not BS4_AVAILABLE:
        return ""

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Remove script/style tags
        for tag in soup(["script", "style", "meta", "link"]):
            tag.decompose()

        text_parts = []

        # Extract text from common tags
        for tag in soup.find_all(["p", "h1", "h2", "h3", "div", "li"]):
            text = tag.get_text(separator=" ", strip=True)
            if len(text) > 3:
                text_parts.append(text)

        # Extract tables
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                text_parts.append("\n".join(rows))

        return "\n".join(text_parts)
    except Exception as e:
        return str(e)


def _read_zip(filepath: str) -> str:
    """Read text files from ZIP archive."""
    try:
        result = [f"=== ZIP Archive: {Path(filepath).name} ==="]

        with zipfile.ZipFile(filepath, "r") as z:
            for name in z.namelist():
                if name.startswith("__MACOSX") or name.endswith("/"):
                    continue

                if any(name.endswith(e) for e in [".txt", ".xml", ".json", ".md"]):
                    try:
                        content = z.read(name).decode("utf-8", errors="ignore")
                        result.append(f"---\n{content[:5000]}")
                    except Exception:
                        pass

        return "\n\n".join(result)
    except Exception as e:
        return str(e)


# =============================================================================
# Helper functions
# =============================================================================


def _is_html_content(filepath: str) -> bool:
    """Check if file contains HTML content."""
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            head = f.read(500).lower()
            return any(x in head for x in ["<html", "<!doctype html", "<body"])
    except Exception:
        return False


def get_supported_formats() -> list[str]:
    """
    Get list of supported file formats.

    Returns:
        List of supported file extensions
    """
    return SUPPORTED_FORMATS.copy()
