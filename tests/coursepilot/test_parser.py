from openpyxl import Workbook

from coursepilot.rag.parsers import get_parser


def test_txt_parser(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("state space search", encoding="utf-8")

    parsed = get_parser(path).parse(path)

    assert parsed.sections[0].content == "state space search"


def test_markdown_parser(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# Chapter 1\n\nAI basics", encoding="utf-8")

    parsed = get_parser(path).parse(path)

    assert "AI basics" in parsed.sections[0].content


def test_xlsx_parser(tmp_path):
    path = tmp_path / "kg.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "KnowledgeGraph"
    sheet.append(["concept", "relation", "target"])
    sheet.append(["search", "is_a", "algorithm"])
    workbook.save(path)

    parsed = get_parser(path).parse(path)

    assert parsed.sections[0].title == "KnowledgeGraph"
    assert "search | is_a | algorithm" in parsed.sections[0].content
