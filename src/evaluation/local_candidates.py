"""Local-only P02 candidate extraction from the owner-supplied B0 samples.

The implementation intentionally depends on the frozen B0 parser surface.  It
does not invoke an LLM, approve Gold, or write source-derived content into the
tracked ``datasets`` tree.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from coursepilot.evals.b0_baseline import (
    SampleInput,
    discover_sample_inputs,
    sha256_file,
)
from coursepilot.rag.parsers import get_parser
from coursepilot.rag.types import ParsedDocument, ParsedSection
from courserag.evals.schemas import (
    CorpusDocument,
    DS0CorpusDataset,
    DS2EvidenceDataset,
    EvidenceRecord,
)
from evaluation.contracts import ReviewStatus, Sha256, SourceSpan, StrictModel
from evaluation.io import atomic_write_json

DEFAULT_OUTPUT_DIR = Path("storage_eval/p02_local_candidates")


class LocalCandidateArtifactSummary(StrictModel):
    document_id: str
    input_sha256: Sha256
    evidence_candidate_count: int = Field(ge=0)


class LocalCandidateSummary(StrictModel):
    schema_version: str = "course-eval.p02.local-candidate-summary.v1"
    generator: str = "legacy-parser-local-candidates-v1"
    gold_status: str = "candidate_only_not_approved"
    external_model_used: bool = False
    artifacts: list[LocalCandidateArtifactSummary]
    ds0_sha256: Sha256
    ds2_sha256: Sha256


@dataclass(frozen=True)
class TextWindow:
    text: str
    start: int
    end: int
    page: int | None


def generate_local_candidates(
    *,
    repository_root: Path,
    sample_dir: Path,
    output_dir: Path,
    summary_path: Path | None = None,
    max_per_document: int = 5,
) -> LocalCandidateSummary:
    if max_per_document < 1:
        raise ValueError("max_per_document must be positive")
    repository_root = repository_root.resolve()
    output_dir = _validate_output_path(output_dir, repository_root)
    inputs = discover_sample_inputs(sample_dir, repository_root)
    documents: list[CorpusDocument] = []
    evidence: list[EvidenceRecord] = []
    artifact_summaries: list[LocalCandidateArtifactSummary] = []

    for sample in inputs:
        parsed = get_parser(sample.path).parse(sample.path)
        document_id = f"local-{sample.sha256[:16]}"
        document_version = f"sha256:{sample.sha256[:16]}"
        documents.append(
            CorpusDocument(
                record_id=f"corpus-{sample.sha256[:16]}",
                review_status=ReviewStatus.CANDIDATE,
                candidate_source="p02_local_legacy_parser",
                document_id=document_id,
                filename=sample.path.name,
                mime_type=sample.media_type,
                sha256=sample.sha256,
                document_version=document_version,
                page_count=_page_count(parsed),
                included_in=["pilot_candidate"],
                redistribution_status="local_only_unverified",
            )
        )
        candidates = _evidence_candidates(
            sample,
            parsed,
            document_id=document_id,
            document_version=document_version,
            limit=max_per_document,
        )
        evidence.extend(candidates)
        artifact_summaries.append(
            LocalCandidateArtifactSummary(
                document_id=document_id,
                input_sha256=sample.sha256,
                evidence_candidate_count=len(candidates),
            )
        )

    ds0 = DS0CorpusDataset(
        dataset_id="courserag-local-candidates",
        dataset_version="p02-local-v1",
        documents=documents,
    )
    ds2 = DS2EvidenceDataset(
        dataset_id="courserag-local-candidates",
        dataset_version="p02-local-v1",
        evidence=evidence,
    )
    ds0_path = output_dir / "ds0_candidates.json"
    ds2_path = output_dir / "ds2_candidates.json"
    atomic_write_json(ds0_path, ds0.model_dump(mode="json"))
    atomic_write_json(ds2_path, ds2.model_dump(mode="json"))
    summary = LocalCandidateSummary(
        artifacts=artifact_summaries,
        ds0_sha256=sha256_file(ds0_path),
        ds2_sha256=sha256_file(ds2_path),
    )
    if summary_path is not None:
        atomic_write_json(summary_path, summary.model_dump(mode="json"))
    return summary


def _evidence_candidates(
    sample: SampleInput,
    parsed: ParsedDocument,
    *,
    document_id: str,
    document_version: str,
    limit: int,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for window in _text_windows(parsed.sections):
        candidate_number = len(records) + 1
        evidence_id = f"evidence-{sample.sha256[:12]}-{candidate_number:02d}"
        if window.page is not None:
            source_span = SourceSpan(
                document_id=document_id,
                document_version=document_version,
                document_sha256=sample.sha256,
                page_start=window.page,
                page_end=window.page,
            )
        else:
            source_span = SourceSpan(
                document_id=document_id,
                document_version=document_version,
                document_sha256=sample.sha256,
                char_start=window.start,
                char_end=window.end,
            )
        records.append(
            EvidenceRecord(
                record_id=evidence_id,
                review_status=ReviewStatus.CANDIDATE,
                candidate_source="p02_local_legacy_parser",
                evidence_id=evidence_id,
                source_span=source_span,
                source_type="native_text",
                gold_text=window.text,
                content_sha256=hashlib.sha256(window.text.encode("utf-8")).hexdigest(),
                semantic_unit_type="other",
            )
        )
        if len(records) >= limit:
            break
    return records


def _text_windows(sections: list[ParsedSection]) -> list[TextWindow]:
    windows: list[TextWindow] = []
    document_offset = 0
    for section in sections:
        content = section.content
        start = 0
        while start < len(content):
            while start < len(content) and content[start].isspace():
                start += 1
            if start >= len(content):
                break
            end = min(start + 600, len(content))
            if end < len(content):
                split = content.rfind(" ", start + 80, end)
                if split > start:
                    end = split
            text = content[start:end]
            if len(text.strip()) >= 80:
                windows.append(
                    TextWindow(
                        text=text,
                        start=document_offset + start,
                        end=document_offset + end,
                        page=section.page,
                    )
                )
            start = end
        document_offset += len(content) + 1
    return windows


def _page_count(parsed: ParsedDocument) -> int | None:
    pages = [section.page for section in parsed.sections if section.page is not None]
    return max(pages) if pages else None


def _validate_output_path(output_dir: Path, repository_root: Path) -> Path:
    resolved = output_dir.resolve()
    try:
        relative = resolved.relative_to(repository_root)
    except ValueError:
        return resolved
    allowed_root = (repository_root / "storage_eval").resolve()
    if not resolved.is_relative_to(allowed_root):
        raise ValueError(
            "source-derived candidate output inside the repository must be under storage_eval"
        )
    if relative.parts and relative.parts[0].casefold() == "datasets":
        raise ValueError("candidate output must never be written under datasets")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate local-only P02 evidence candidates without an external model."
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--sample-dir", type=Path, default=Path("data/sample_files"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary-path", type=Path)
    parser.add_argument("--max-per-document", type=int, default=5)
    args = parser.parse_args()
    summary = generate_local_candidates(
        repository_root=args.repository_root,
        sample_dir=args.sample_dir,
        output_dir=args.output_dir,
        summary_path=args.summary_path,
        max_per_document=args.max_per_document,
    )
    print(
        "generated "
        f"{sum(item.evidence_candidate_count for item in summary.artifacts)} "
        "local-only candidates; no external model and no Gold approval"
    )


if __name__ == "__main__":
    main()
