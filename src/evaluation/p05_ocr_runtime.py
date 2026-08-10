"""Compatibility CLI for resolving the P05 OCR runtime profile."""

from courserag.parsers.ocr.runtime_profile import main, prepare_runtime_profile

__all__ = ["prepare_runtime_profile"]


if __name__ == "__main__":
    main()
