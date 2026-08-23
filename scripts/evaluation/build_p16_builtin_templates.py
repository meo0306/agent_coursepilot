from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "resources/templates/exporters/ppt_standard_lecture_v1.pptx"
DEST = ROOT / "resources/templates/exporters"

THEMES = {
    "p16_standard_lecture_v2.pptx": ("2f5597", "5b9bd5", "d9eaf7"),
    "p16_concept_explanation_v2.pptx": ("403c8c", "00a6a6", "d9f3f3"),
    "p16_case_seminar_v2.pptx": ("8f4e28", "ed7d31", "fce4d6"),
}


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for name, colors in THEMES.items():
        target = DEST / name
        with ZipFile(SOURCE) as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename.startswith("ppt/theme/") and item.filename.endswith(".xml"):
                    text = data.decode("utf-8")
                    replacements = {
                        "4F81BD": colors[0],
                        "C0504D": colors[1],
                        "9BBB59": colors[2],
                        "4BACC6": colors[1],
                    }
                    for old, new in replacements.items():
                        text = text.replace(old, new).replace(old.lower(), new)
                    data = text.encode("utf-8")
                output.writestr(item, data)
        print(target)


if __name__ == "__main__":
    main()
