import ast
from pathlib import Path


def test_new_runtime_has_no_legacy_or_courserag_internal_imports() -> None:
    root = Path(__file__).resolve().parents[3] / "src/coursepilot/runtime"
    forbidden = (
        "coursepilot.rag",
        "courserag.parsers",
        "courserag.chunking",
        "courserag.indexing",
        "courserag.persistence",
        "chromadb",
        "langchain_chroma",
    )
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(item.name for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not [name for name in imports if name.startswith(forbidden)], path
