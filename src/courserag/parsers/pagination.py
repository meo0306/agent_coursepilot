"""Reproducible DOCX rendering and monotonic block-to-page alignment."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol

import fitz

from courserag.domain.document import (
    BlockIR,
    DocxPageAnchor,
    ParsedDocumentIR,
    ParseWarning,
    RendererManifest,
    canonical_json_bytes,
    sha256_bytes,
)


class RendererError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandExecutor(Protocol):
    def __call__(
        self,
        arguments: Sequence[str],
        *,
        timeout_seconds: int,
        environment: Mapping[str, str],
    ) -> CommandResult: ...


def run_command(
    arguments: Sequence[str],
    *,
    timeout_seconds: int,
    environment: Mapping[str, str],
) -> CommandResult:
    completed = subprocess.run(
        list(arguments),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        env=dict(environment),
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class RendererProfile:
    profile_id: str
    provider: str
    renderer_version: str
    locale: str
    timezone: str
    pdf_filter: str
    font_manifest_path: Path
    font_package: str
    font_package_version: str
    required_font_families: tuple[str, ...]
    profile_sha256: str
    font_manifest_sha256: str
    low_alignment_confidence: float

    @classmethod
    def load(cls, profile_path: Path) -> RendererProfile:
        raw_profile = profile_path.read_bytes()
        values = json.loads(raw_profile)
        font_path = profile_path.parent / str(values["expected_font_manifest"])
        font_bytes = font_path.read_bytes()
        font_values = json.loads(font_bytes)
        font_manifest_sha256 = str(font_values["font_manifest_sha256"])
        if len(font_manifest_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in font_manifest_sha256
        ):
            raise ValueError("renderer font Manifest SHA-256 is invalid")
        return cls(
            profile_id=str(values["profile_id"]),
            provider=str(values["provider"]),
            renderer_version=str(values["renderer_version"]),
            locale=str(values["locale"]),
            timezone=str(values["timezone"]),
            pdf_filter=str(values["pdf_filter"]),
            font_manifest_path=font_path,
            font_package=str(font_values["package"]),
            font_package_version=str(font_values["package_version"]),
            required_font_families=tuple(str(font) for font in font_values["required_families"]),
            profile_sha256=sha256_bytes(canonical_json_bytes(values)),
            font_manifest_sha256=font_manifest_sha256,
            low_alignment_confidence=float(values["low_alignment_confidence"]),
        )


@dataclass(frozen=True)
class RenderedPage:
    physical_page_index: int
    display_page_label: str | None
    section_page_index: int | None
    normalized_text: str
    width: float
    height: float


@dataclass(frozen=True)
class DocxPaginationSnapshot:
    raw_pdf: bytes
    canonical_pdf: bytes
    pages: tuple[RenderedPage, ...]
    manifest: RendererManifest
    warnings: tuple[ParseWarning, ...] = ()


def canonicalize_pdf(content: bytes) -> bytes:
    """Remove volatile PDF metadata while preserving rendered content and page geometry."""

    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise RendererError("renderer output is not a readable PDF") from exc
    canonical = fitz.open()
    try:
        for source_page in document:
            target_page = canonical.new_page(
                width=float(source_page.rect.width),
                height=float(source_page.rect.height),
            )
            target_page.show_pdf_page(target_page.rect, document, source_page.number)
        page_labels = document.get_page_labels()
        if page_labels:
            canonical.set_page_labels(page_labels)
        canonical.set_metadata({})
        return canonical.tobytes(garbage=4, clean=True, deflate=True, no_new_id=True)
    finally:
        canonical.close()
        document.close()


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if not character.isspace())


_PAGE_LABEL = re.compile(r"^(?:[-—– ]*)?(?P<label>(?:[ivxlcdm]+|\d+))(?:[-—– ]*)?$", re.I)


def _source_visible_page_label(page: fitz.Page) -> str | None:
    native = page.get_label().strip()
    if native:
        return native
    height = float(page.rect.height)
    candidates: list[tuple[float, str]] = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks", sort=True):
        del x0, x1
        stripped = str(text).strip()
        match = _PAGE_LABEL.fullmatch(stripped)
        if match is None:
            continue
        if float(y0) <= height * 0.12 or float(y1) >= height * 0.88:
            candidates.append((max(float(y0), height - float(y1)), match.group("label")))
    return min(candidates, default=(0.0, None), key=lambda item: item[0])[1]


def _rendered_text_in_reading_order(page: fitz.Page) -> str:
    blocks = [
        (float(x0), float(y0), float(x1), float(y1), str(text))
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks", sort=False)
        if str(text).strip()
    ]
    if len(blocks) < 2:
        return "\n".join(block[4] for block in blocks)
    middle = float(page.rect.width) / 2
    left = [block for block in blocks if block[2] <= middle * 1.08]
    right = [block for block in blocks if block[0] >= middle * 0.92]
    crossing = [block for block in blocks if block[0] < middle * 0.92 and block[2] > middle * 1.08]
    if left and right and len(crossing) <= max(2, len(blocks) // 5):
        column_top = min(block[1] for block in left + right)
        top_crossing = sorted(
            (block for block in crossing if block[1] < column_top),
            key=lambda block: (block[1], block[0]),
        )
        bottom_crossing = [block for block in crossing if block not in top_crossing]
        ordered = (
            top_crossing
            + sorted(left, key=lambda block: (block[1], block[0]))
            + sorted(right, key=lambda block: (block[1], block[0]))
            + sorted(bottom_crossing, key=lambda block: (block[1], block[0]))
        )
    else:
        ordered = sorted(blocks, key=lambda block: (block[1], block[0]))
    return "\n".join(block[4] for block in ordered)


def _page_snapshot(content: bytes) -> tuple[tuple[RenderedPage, ...], str]:
    with fitz.open(stream=content, filetype="pdf") as document:
        pages: list[RenderedPage] = []
        manifest_pages: list[dict[str, object]] = []
        for page_index, page in enumerate(document, start=1):
            label = _source_visible_page_label(page)
            normalized_text = _normalize_text(_rendered_text_in_reading_order(page))
            pages.append(
                RenderedPage(
                    physical_page_index=page_index,
                    display_page_label=label,
                    section_page_index=int(label)
                    if label is not None and label.isdigit()
                    else None,
                    normalized_text=normalized_text,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                )
            )
            manifest_pages.append(
                {
                    "physical_page_index": page_index,
                    "display_page_label": label,
                    "width": round(float(page.rect.width), 4),
                    "height": round(float(page.rect.height), 4),
                    "normalized_text_sha256": sha256_bytes(normalized_text.encode()),
                }
            )
    return tuple(pages), sha256_bytes(canonical_json_bytes(manifest_pages))


class DocxPaginationRenderer:
    def __init__(
        self,
        profile: RendererProfile,
        *,
        soffice_path: str = "soffice",
        timeout_seconds: int = 300,
        command_executor: CommandExecutor = run_command,
        font_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.profile = profile
        self.soffice_path = soffice_path
        self.timeout_seconds = timeout_seconds
        self.command_executor = command_executor
        self.font_resolver = font_resolver or self._resolve_font

    def render(
        self, content: bytes, *, requested_fonts: Sequence[str] = ()
    ) -> DocxPaginationSnapshot:
        environment = dict(os.environ)
        environment.update(
            {
                "LANG": self.profile.locale,
                "LC_ALL": self.profile.locale,
                "TZ": self.profile.timezone,
            }
        )
        version = self.command_executor(
            (self.soffice_path, "--version"),
            timeout_seconds=30,
            environment=environment,
        )
        if version.returncode != 0 or self.profile.renderer_version not in version.stdout:
            raise RendererError("LibreOffice version does not match the frozen renderer profile")
        package = self.command_executor(
            ("dpkg-query", "-W", "-f=${Version}", self.profile.font_package),
            timeout_seconds=30,
            environment=environment,
        )
        if package.returncode != 0 or package.stdout.strip() != self.profile.font_package_version:
            raise RendererError("font package version does not match the frozen renderer profile")
        for required_font in self.profile.required_font_families:
            resolved = self.font_resolver(required_font)
            if resolved is None or required_font.casefold() not in resolved.casefold():
                raise RendererError("required renderer font family is unavailable")
        with tempfile.TemporaryDirectory(prefix="courserag-docx-render-") as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.docx"
            output_dir = root / "output"
            user_profile = root / "user-profile"
            output_dir.mkdir()
            user_profile.mkdir()
            source_path.write_bytes(content)
            arguments = (
                self.soffice_path,
                "--headless",
                "--nologo",
                "--nodefault",
                "--nolockcheck",
                f"-env:UserInstallation={user_profile.as_uri()}",
                "--convert-to",
                f"pdf:{self.profile.pdf_filter}",
                "--outdir",
                str(output_dir),
                str(source_path),
            )
            result = self.command_executor(
                arguments,
                timeout_seconds=self.timeout_seconds,
                environment=environment,
            )
            output_path = output_dir / "source.pdf"
            if result.returncode != 0 or not output_path.is_file():
                raise RendererError("LibreOffice failed to create the pagination snapshot")
            raw_pdf = output_path.read_bytes()
        return self.build_snapshot(raw_pdf, requested_fonts=requested_fonts, arguments=arguments)

    def build_snapshot(
        self,
        raw_pdf: bytes,
        *,
        requested_fonts: Sequence[str] = (),
        arguments: Sequence[str] = ("soffice", "--headless", "--convert-to", "pdf"),
    ) -> DocxPaginationSnapshot:
        canonical_pdf = canonicalize_pdf(raw_pdf)
        pages, page_manifest_sha256 = _page_snapshot(canonical_pdf)
        substitutions: dict[str, str] = {}
        warnings: list[ParseWarning] = []
        for font in sorted(set(requested_fonts)):
            resolved = self.font_resolver(font)
            if resolved is None or resolved.casefold() != font.casefold():
                substitutions[font] = resolved or "missing"
                warnings.append(
                    ParseWarning(
                        code="FONT_SUBSTITUTION",
                        message="Requested DOCX font is missing or was substituted.",
                        details={"requested_font": font, "resolved_font": resolved},
                    )
                )
        manifest = RendererManifest(
            provider=self.profile.provider,
            renderer_version=self.profile.renderer_version,
            profile_sha256=self.profile.profile_sha256,
            font_manifest_sha256=self.profile.font_manifest_sha256,
            raw_pdf_sha256=sha256_bytes(raw_pdf),
            canonical_pdf_sha256=sha256_bytes(canonical_pdf),
            page_manifest_sha256=page_manifest_sha256,
            page_count=len(pages),
            command_arguments=tuple(
                Path(item).name if "courserag-docx-render-" in item else item for item in arguments
            ),
            environment={
                "LANG": self.profile.locale,
                "LC_ALL": self.profile.locale,
                "TZ": self.profile.timezone,
            },
            font_substitutions=substitutions,
        )
        return DocxPaginationSnapshot(
            raw_pdf=raw_pdf,
            canonical_pdf=canonical_pdf,
            pages=pages,
            manifest=manifest,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _resolve_font(font: str) -> str | None:
        try:
            completed = subprocess.run(
                ("fc-match", "--format=%{family}", font),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout.split(",", maxsplit=1)[0].strip() or None


def align_docx_blocks(
    document: ParsedDocumentIR,
    snapshot: DocxPaginationSnapshot,
    *,
    low_confidence_threshold: float,
) -> ParsedDocumentIR:
    if document.source_format != "docx" or len(document.pages) != 1:
        raise ValueError("DOCX pagination alignment requires one logical DOCX page")
    joined = "".join(page.normalized_text for page in snapshot.pages)
    page_offsets: list[tuple[int, int, RenderedPage]] = []
    offset = 0
    for page in snapshot.pages:
        page_end_offset = offset + len(page.normalized_text)
        page_offsets.append((offset, page_end_offset, page))
        offset = page_end_offset
    cursor = 0
    warnings = list(document.warnings) + list(snapshot.warnings)
    aligned_blocks: list[BlockIR] = []
    for block in document.pages[0].blocks:
        needle = _normalize_text(block.text)
        if not needle:
            aligned_blocks.append(block)
            continue
        start: int | None = None
        block_end: int | None = None
        confidence = 0.0
        if needle:
            exact = joined.find(needle, cursor)
            if exact < 0:
                exact = joined.find(needle)
            if exact >= 0:
                start, block_end, confidence = exact, exact + len(needle), 1.0
            else:
                search_end = min(len(joined), cursor + max(2_000, len(needle) * 8))
                match = SequenceMatcher(
                    None, needle, joined[cursor:search_end], autojunk=False
                ).find_longest_match()
                confidence = match.size / len(needle)
                if match.size:
                    start = cursor + match.b
                    block_end = start + match.size
                if confidence < low_confidence_threshold:
                    page_matches: list[tuple[float, int, int]] = []
                    candidate_page_indexes: set[int] = set()
                    current_page_index = next(
                        (
                            index
                            for index, (begin, finish, _) in enumerate(page_offsets)
                            if begin <= cursor < max(begin + 1, finish)
                        ),
                        len(page_offsets) - 1,
                    )
                    candidate_page_indexes.update(
                        index
                        for index in (
                            current_page_index - 1,
                            current_page_index,
                            current_page_index + 1,
                        )
                        if 0 <= index < len(page_offsets)
                    )
                    seed_length = min(16, max(4, len(needle) // 4))
                    seed_starts = {
                        0,
                        max(0, len(needle) // 2 - seed_length // 2),
                        max(0, len(needle) - seed_length),
                    }
                    seeds = {
                        needle[seed_start : seed_start + seed_length] for seed_start in seed_starts
                    }
                    candidate_page_indexes.update(
                        index
                        for index, (_, _, rendered_page) in enumerate(page_offsets)
                        if any(seed in rendered_page.normalized_text for seed in seeds)
                    )
                    for page_index in candidate_page_indexes:
                        begin, _, rendered_page = page_offsets[page_index]
                        candidate = SequenceMatcher(
                            None,
                            needle,
                            rendered_page.normalized_text,
                            autojunk=False,
                        ).find_longest_match()
                        page_matches.append(
                            (
                                candidate.size / len(needle),
                                begin + candidate.b,
                                candidate.size,
                            )
                        )
                    page_matches.sort(reverse=True)
                    if page_matches:
                        best_score, best_start, best_size = page_matches[0]
                        next_score = page_matches[1][0] if len(page_matches) > 1 else -1.0
                        if best_score >= low_confidence_threshold and (
                            best_score == 1.0 or best_score - next_score >= 0.02
                        ):
                            confidence = best_score
                            start = best_start
                            block_end = best_start + best_size
        start_page = next(
            (
                page
                for begin, finish, page in page_offsets
                if start is not None and begin <= start < max(begin + 1, finish)
            ),
            None,
        )
        end_page = next(
            (
                page
                for begin, finish, page in page_offsets
                if block_end is not None and begin < block_end <= max(begin + 1, finish)
            ),
            start_page,
        )
        if start_page is None or confidence < low_confidence_threshold:
            anchor = DocxPageAnchor(
                renderer_provider=snapshot.manifest.provider,
                renderer_version=snapshot.manifest.renderer_version,
                render_profile_sha256=snapshot.manifest.profile_sha256,
                canonical_pdf_sha256=snapshot.manifest.canonical_pdf_sha256,
                alignment_confidence=confidence,
            )
            warnings.append(
                ParseWarning(
                    code="LOW_DOCX_ALIGNMENT_CONFIDENCE",
                    message="DOCX block could not be assigned a page without guessing.",
                    block_id=block.block_id,
                    details={"alignment_confidence": confidence},
                )
            )
        else:
            assert start_page is not None
            anchor = DocxPageAnchor(
                physical_page_index=start_page.physical_page_index,
                physical_page_end_index=(
                    end_page.physical_page_index
                    if end_page is not None
                    else start_page.physical_page_index
                ),
                display_page_label=start_page.display_page_label,
                section_page_index=start_page.section_page_index,
                renderer_provider=snapshot.manifest.provider,
                renderer_version=snapshot.manifest.renderer_version,
                render_profile_sha256=snapshot.manifest.profile_sha256,
                canonical_pdf_sha256=snapshot.manifest.canonical_pdf_sha256,
                alignment_confidence=confidence,
                page_width=start_page.width,
                page_height=start_page.height,
            )
            if start is not None and start >= cursor:
                cursor = max(cursor, block_end or cursor)
        aligned_blocks.append(
            block.model_copy(update={"page_anchor": anchor, "confidence": confidence})
        )
    logical_page = document.pages[0].model_copy(update={"blocks": tuple(aligned_blocks)})
    return document.model_copy(
        update={
            "pages": (logical_page,),
            "warnings": tuple(warnings),
            "renderer_manifest": snapshot.manifest,
        }
    )
