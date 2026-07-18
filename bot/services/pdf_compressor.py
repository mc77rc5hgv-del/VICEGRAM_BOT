"""Lossless PDF compression.

Uses pikepdf (a Python binding for qpdf) to shrink PDF files without touching
their visual content: streams are re-deflated at maximum compression,
duplicate/unreferenced objects are dropped, and objects are packed into
object streams. No page is rasterized and no image is recompressed, so the
result is byte-for-byte equivalent in appearance to the original.
"""

from dataclasses import dataclass
from pathlib import Path

import pikepdf


class PdfCompressionError(Exception):
    """Raised when a PDF cannot be processed."""


class PdfEncryptedError(PdfCompressionError):
    """Raised when a PDF is password protected."""


@dataclass
class CompressionResult:
    original_size: int
    compressed_size: int

    @property
    def saved_bytes(self) -> int:
        return max(self.original_size - self.compressed_size, 0)

    @property
    def saved_percent(self) -> float:
        if self.original_size == 0:
            return 0.0
        return (self.saved_bytes / self.original_size) * 100

    @property
    def improved(self) -> bool:
        return self.compressed_size < self.original_size


def compress_pdf_lossless(input_path: Path, output_path: Path) -> CompressionResult:
    """Compress a PDF file losslessly, writing the result to output_path."""
    try:
        with pikepdf.open(input_path) as pdf:
            pdf.remove_unreferenced_resources()
            pdf.save(
                output_path,
                compress_streams=True,
                stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                linearize=False,
            )
    except pikepdf.PasswordError as exc:
        raise PdfEncryptedError("PDF is password protected") from exc
    except pikepdf.PdfError as exc:
        raise PdfCompressionError(f"Failed to process PDF: {exc}") from exc

    return CompressionResult(
        original_size=input_path.stat().st_size,
        compressed_size=output_path.stat().st_size,
    )
