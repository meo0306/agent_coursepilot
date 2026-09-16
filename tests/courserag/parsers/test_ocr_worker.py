from pathlib import Path
from types import SimpleNamespace

import pytest

from courserag.parsers.ocr import worker


def test_rapidocr_current_output_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    output = SimpleNamespace(
        boxes=[[[1, 2], [11, 2], [11, 12], [1, 12]]],
        txts=["课程内容"],
        scores=[0.91],
    )
    module = SimpleNamespace(RapidOCR=lambda: lambda _path: output, __version__="3.9.1")
    monkeypatch.setattr(worker.importlib, "import_module", lambda _name: module)

    result = worker._rapidocr(Path("unused.png"), "ch")

    assert result == {
        "engine_version": "3.9.1",
        "model_name": "rapidocr-bundled",
        "regions": [
            {
                "text": "课程内容",
                "polygon": [[1, 2], [11, 2], [11, 12], [1, 12]],
                "confidence": 0.91,
            }
        ],
    }


def test_paddleocr_current_output_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    output = SimpleNamespace(
        json={
            "res": {
                "rec_polys": [[[3, 4], [13, 4], [13, 14], [3, 14]]],
                "rec_texts": ["教材内容"],
                "rec_scores": [0.88],
            }
        }
    )
    engine = SimpleNamespace(predict=lambda _path: [output])
    module = SimpleNamespace(PaddleOCR=lambda **_kwargs: engine, __version__="3.7.0")
    monkeypatch.setattr(worker.importlib, "import_module", lambda _name: module)

    result = worker._paddleocr(Path("unused.png"), "ch")

    assert result == {
        "engine_version": "3.7.0",
        "model_name": "paddleocr-ch",
        "regions": [
            {
                "text": "教材内容",
                "polygon": [[3, 4], [13, 4], [13, 14], [3, 14]],
                "confidence": 0.88,
            }
        ],
    }


def test_provider_cardinality_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = SimpleNamespace(boxes=[[[0, 0], [1, 0], [1, 1], [0, 1]]], txts=[], scores=[])
    module = SimpleNamespace(RapidOCR=lambda: lambda _path: output, __version__="3.9.1")
    monkeypatch.setattr(worker.importlib, "import_module", lambda _name: module)

    with pytest.raises(RuntimeError, match="inconsistent result cardinality"):
        worker._rapidocr(Path("unused.png"), "ch")
