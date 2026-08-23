from __future__ import annotations

from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

from coursepilot.domain.ppt import PPTArtifact
from coursepilot.templates.ppt import PPTTemplateProfile


def _layout_for(
    presentation: Any,
    artifact: PPTArtifact,
    slide_id: str,
    profile: PPTTemplateProfile | None,
):
    if profile is None:
        return (
            presentation.slide_layouts[6]
            if len(presentation.slide_layouts) > 6
            else presentation.slide_layouts[1]
        )
    plan = next((item for item in artifact.architecture.plans if item.slide_id == slide_id), None)
    if plan is None:
        raise ValueError(f"PPT_TEMPLATE_SLIDE_PLAN_MISSING:{slide_id}")
    layout_name = profile.slide_type_layout_map.get(
        plan.slide_type
    ) or profile.slide_type_layout_map.get(plan.layout_role)
    if not layout_name:
        raise ValueError(f"PPT_TEMPLATE_LAYOUT_MAPPING_MISSING:{plan.slide_type}")
    for layout in presentation.slide_layouts:
        if str(layout.name) == layout_name:
            return layout
    raise ValueError(f"PPT_TEMPLATE_LAYOUT_MISSING:{layout_name}")


class PPTXVersionedExporter:
    """Export editable slides using the selected template profile."""

    def export(
        self,
        artifact: PPTArtifact,
        output_path: str | Path,
        *,
        template_path: str | Path | None = None,
        profile: PPTTemplateProfile | None = None,
        slide_render_hints: dict[str, dict[str, Any]] | None = None,
    ) -> Path:
        presentation: Any = Presentation(str(template_path)) if template_path else Presentation()
        while len(presentation.slides._sldIdLst):
            slide_id = presentation.slides._sldIdLst[0]
            presentation.part.drop_rel(slide_id.rId)
            presentation.slides._sldIdLst.remove(slide_id)
        for content in artifact.slides:
            hints = (slide_render_hints or {}).get(content.slide_id, {})
            layout = _layout_for(presentation, artifact, content.slide_id, profile)
            slide = presentation.slides.add_slide(layout)
            title = slide.shapes.title or slide.shapes.add_textbox(
                0, 0, presentation.slide_width, 700000
            )
            title.text = content.title
            if hints.get("title_top"):
                title.left = Inches(0.5)
                title.top = Inches(0.25)
                title.width = presentation.slide_width - Inches(1.0)
                title.height = Inches(0.85)
            body = next(
                (
                    shape
                    for shape in slide.placeholders
                    if any(
                        token in str(getattr(shape, "name", "")).lower()
                        for token in ("content", "body")
                    )
                ),
                None,
            )
            if body is None:
                body = slide.shapes.add_textbox(
                    700000, 1300000, presentation.slide_width - 1400000, 4200000
                )
            frame = body.text_frame
            frame.clear()
            lines = content.bullets or ([content.body_text] if content.body_text else [])
            for i, line in enumerate(lines):
                paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
                paragraph.text = line
                paragraph.level = 0
                if hints.get("compact_text"):
                    paragraph.font.size = Pt(18)
            table_tsv = hints.get("editable_table_tsv")
            if isinstance(table_tsv, str) and table_tsv.strip():
                rows = [row.split("\t") for row in table_tsv.strip().splitlines()]
                columns = max((len(row) for row in rows), default=0)
                if rows and columns:
                    table_shape = slide.shapes.add_table(
                        len(rows), columns, Inches(0.45), Inches(1.45), Inches(9.0), Inches(5.6)
                    )
                    table = table_shape.table
                    for row_index, row in enumerate(rows):
                        for column_index in range(columns):
                            cell = table.cell(row_index, column_index)
                            cell.text = row[column_index] if column_index < len(row) else ""
                            for paragraph in cell.text_frame.paragraphs:
                                paragraph.font.size = Pt(9 if len(rows) > 12 else 12)
                    body.text = ""
            elif content.assets and hints.get("materialize_assets"):
                shape = slide.shapes.add_shape(
                    MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5.2), Inches(2.0), Inches(4.1), Inches(2.8)
                )
                shape.text = "\n".join(a.description for a in content.assets)
                shape.name = "P16_Editable_Instructional_Diagram"
                for paragraph in shape.text_frame.paragraphs:
                    paragraph.font.size = Pt(16)
            elif content.assets:
                shape = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, 700000, 5900000, 3000000, 700000
                )
                shape.text = "Asset placeholder: " + ", ".join(
                    a.description for a in content.assets
                )
                shape.name = "P16_Replaceable_Asset_Placeholder"
            notes = slide.notes_slide.notes_text_frame
            notes.text = content.speaker_notes
            if content.citations:
                notes.text += "\nCitations: " + ", ".join(c.evidence_id for c in content.citations)
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        presentation.save(str(destination))
        return destination
