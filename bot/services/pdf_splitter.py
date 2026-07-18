"""Extracting a subset of pages from a PDF.

Pages are copied as-is (no re-rendering), so quality is untouched — this is
the same "lossless" guarantee as the compressor, just applied to a page
selection instead of the whole document.
"""

import re
from pathlib import Path

import pikepdf

from bot.services.pdf_errors import PdfCompressionError, PdfEncryptedError

_TOKEN_RE = re.compile(r"^\d+(-\d+)?$")


class PageRangeError(Exception):
    """Raised when a user-supplied page specification is invalid."""


def get_page_count(input_path: Path) -> int:
    try:
        with pikepdf.open(input_path) as pdf:
            return len(pdf.pages)
    except pikepdf.PasswordError as exc:
        raise PdfEncryptedError("PDF is password protected") from exc
    except pikepdf.PdfError as exc:
        raise PdfCompressionError(f"Failed to read PDF: {exc}") from exc


def parse_page_spec(spec: str, total_pages: int) -> list[int]:
    """Parse specs like "1-135" or "1,3,5-10" into a sorted list of pages."""
    tokens = [t for t in re.split(r"[,\s]+", spec.strip()) if t]
    if not tokens:
        raise PageRangeError("Не указаны номера страниц.")

    pages: set[int] = set()
    for token in tokens:
        if not _TOKEN_RE.match(token):
            raise PageRangeError(
                f"Не понял «{token}» — используйте формат вроде 1-135 или 1,5,10-20."
            )
        if "-" in token:
            start_str, end_str = token.split("-")
            start, end = int(start_str), int(end_str)
            if start > end:
                start, end = end, start
        else:
            start = end = int(token)

        if start < 1 or end > total_pages:
            raise PageRangeError(
                f"Страница вне диапазона: в файле {total_pages} стр., "
                f"а вы указали «{token}»."
            )
        pages.update(range(start, end + 1))

    if not pages:
        raise PageRangeError("Не указаны номера страниц.")

    return sorted(pages)


def format_pages_label(pages: list[int]) -> str:
    """Collapse a sorted page list into a compact label, e.g. [1,2,3,5] -> '1-3_5'."""
    ranges = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = p
    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    return "_".join(ranges)


def extract_pages(input_path: Path, output_path: Path, page_numbers: list[int]) -> None:
    """Write a new PDF containing only the given 1-indexed page numbers."""
    try:
        with pikepdf.open(input_path) as src:
            dst = pikepdf.Pdf.new()
            try:
                for page_number in page_numbers:
                    dst.pages.append(src.pages[page_number - 1])
                dst.save(output_path)
            finally:
                dst.close()
    except pikepdf.PasswordError as exc:
        raise PdfEncryptedError("PDF is password protected") from exc
    except pikepdf.PdfError as exc:
        raise PdfCompressionError(f"Failed to extract pages: {exc}") from exc
