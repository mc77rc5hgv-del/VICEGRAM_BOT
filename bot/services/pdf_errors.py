class PdfCompressionError(Exception):
    """Raised when a PDF cannot be processed."""


class PdfEncryptedError(PdfCompressionError):
    """Raised when a PDF is password protected."""
