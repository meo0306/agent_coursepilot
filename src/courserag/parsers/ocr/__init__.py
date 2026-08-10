"""Page-level OCR provider abstractions introduced by P05."""

from courserag.parsers.ocr.providers import (
    PaddleOCRAdapter,
    RapidOCRAdapter,
    SubprocessOCRAdapter,
    TesseractAdapter,
)
from courserag.parsers.ocr.types import (
    OCRImageInput,
    OCRPageResult,
    OCRProvider,
    OCRProviderProfile,
    OCRRegionResult,
    OCRWarning,
)

__all__ = [
    "OCRImageInput",
    "OCRPageResult",
    "OCRProvider",
    "OCRProviderProfile",
    "OCRRegionResult",
    "OCRWarning",
    "PaddleOCRAdapter",
    "RapidOCRAdapter",
    "SubprocessOCRAdapter",
    "TesseractAdapter",
]
