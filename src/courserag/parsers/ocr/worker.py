"""Isolated OCR engine entry point. The parent process owns limits and validation."""

from __future__ import annotations

import csv
import importlib
import io
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path


def _as_points(value: object) -> list[list[int]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    points: list[list[int]] = []
    for point in value:
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) < 2:
            return []
        x, y = point[0], point[1]
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return []
        points.append([round(x), round(y)])
    return points


def _as_list(value: object) -> list[object]:
    """Normalize provider list/tuple/ndarray values without importing NumPy."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        converted = to_list()
        if converted is value:
            return []
        return _as_list(converted)
    return []


def _rapidocr_rows(payload: object) -> list[tuple[object, object, object]]:
    boxes = _as_list(getattr(payload, "boxes", None))
    texts = _as_list(getattr(payload, "txts", None))
    scores = _as_list(getattr(payload, "scores", None))
    if boxes or texts or scores:
        if not (len(boxes) == len(texts) == len(scores)):
            raise RuntimeError("RapidOCR returned inconsistent result cardinality")
        return list(zip(boxes, texts, scores, strict=True))

    rows: list[tuple[object, object, object]] = []
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        for row in payload:
            if isinstance(row, Sequence) and not isinstance(row, (str, bytes)) and len(row) >= 3:
                rows.append((row[0], row[1], row[2]))
    return rows


def _rapidocr(path: Path, _language: str) -> dict[str, object]:
    module = importlib.import_module("rapidocr")
    engine_type = getattr(module, "RapidOCR", None)
    if not callable(engine_type):
        raise RuntimeError("RapidOCR entry point is unavailable")
    engine = engine_type()
    raw = engine(str(path))
    payload = raw[0] if isinstance(raw, tuple) else raw
    regions: list[dict[str, object]] = []
    for polygon_value, text, score in _rapidocr_rows(payload):
        polygon = _as_points(polygon_value)
        if polygon and isinstance(text, str) and isinstance(score, (int, float)):
            regions.append({"text": text, "polygon": polygon, "confidence": float(score)})
    version = str(getattr(module, "__version__", "unknown"))
    return {"engine_version": version, "model_name": "rapidocr-bundled", "regions": regions}


def _tesseract(path: Path, language: str) -> dict[str, object]:
    process = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", language, "tsv"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    regions: list[dict[str, object]] = []
    for row in csv.DictReader(io.StringIO(process.stdout.decode("utf-8")), delimiter="\t"):
        text = row.get("text", "").strip()
        if not text:
            continue
        confidence = float(row.get("conf", "-1"))
        if confidence < 0:
            continue
        left = int(row["left"])
        top = int(row["top"])
        right = left + int(row["width"])
        bottom = top + int(row["height"])
        regions.append(
            {
                "text": text,
                "polygon": [[left, top], [right, top], [right, bottom], [left, bottom]],
                "confidence": confidence / 100.0,
            }
        )
    version = subprocess.run(
        ["tesseract", "--version"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    ).stdout.splitlines()[0]
    return {"engine_version": version, "model_name": f"tesseract-{language}", "regions": regions}


def _paddleocr(path: Path, language: str) -> dict[str, object]:
    module = importlib.import_module("paddleocr")
    engine_type = getattr(module, "PaddleOCR", None)
    if not callable(engine_type):
        raise RuntimeError("PaddleOCR entry point is unavailable")
    engine = engine_type(
        lang=language,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    raw = engine.predict(str(path))
    regions: list[dict[str, object]] = []
    for result in _as_list(raw):
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()
        if not isinstance(payload, Mapping):
            continue
        result_payload = payload.get("res", payload)
        if not isinstance(result_payload, Mapping):
            continue
        polygons = _as_list(result_payload.get("rec_polys"))
        texts = _as_list(result_payload.get("rec_texts"))
        scores = _as_list(result_payload.get("rec_scores"))
        if not (len(polygons) == len(texts) == len(scores)):
            raise RuntimeError("PaddleOCR returned inconsistent result cardinality")
        for polygon_value, text, score in zip(polygons, texts, scores, strict=True):
            polygon = _as_points(polygon_value)
            if polygon and isinstance(text, str) and isinstance(score, (int, float)):
                regions.append({"text": text, "polygon": polygon, "confidence": float(score)})
    version = str(getattr(module, "__version__", "unknown"))
    return {"engine_version": version, "model_name": f"paddleocr-{language}", "regions": regions}


def main(arguments: Sequence[str] | None = None) -> int:
    values = list(arguments or sys.argv[1:])
    if len(values) != 3:
        raise SystemExit("usage: worker PROVIDER IMAGE_PATH LANGUAGE")
    provider, image_path, language = values
    handlers = {"rapidocr": _rapidocr, "tesseract": _tesseract, "paddleocr": _paddleocr}
    handler = handlers.get(provider)
    if handler is None:
        raise SystemExit("unsupported OCR provider")
    result = handler(Path(image_path), language)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
