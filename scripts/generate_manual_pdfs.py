#!/usr/bin/env python3
"""Render the two authoritative Arabic operating manuals as A4 PDFs."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown


ROOT = Path(__file__).resolve().parents[1]
MANUAL_DIR = ROOT / "manual"
CHROME = shutil.which("google-chrome") or shutil.which("chromium")

MANUALS = (
    ("01-دليل-السوبر-أدمن.md", "دليل-السوبر-أدمن.pdf", "دليل السوبر أدمن"),
    ("02-دليل-الموظفين-والتدريب.md", "دليل-الموظفين-والتدريب.pdf", "دليل الموظفين والتدريب"),
)

STYLE = """
@page { size: A4; margin: 16mm 15mm 18mm; }
* { box-sizing: border-box; }
html { direction: rtl; font-family: "Noto Sans Arabic", "Noto Naskh Arabic", sans-serif; }
body { color: #172033; font-size: 10.5pt; line-height: 1.65; margin: 0; }
h1 { color: #8b4a13; font-size: 22pt; margin: 0 0 12mm; text-align: center; }
h2 { border-bottom: 2px solid #d99a45; color: #7a3f10; font-size: 16pt; margin: 9mm 0 4mm; padding-bottom: 2mm; break-after: avoid; }
h3 { color: #9a5a1b; font-size: 12.5pt; margin: 6mm 0 2mm; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
table { border-collapse: collapse; font-size: 9pt; margin: 4mm 0; width: 100%; break-inside: avoid; }
th, td { border: 1px solid #c8ccd3; padding: 2mm; text-align: right; vertical-align: top; }
th { background: #f7ead8; color: #67350f; }
blockquote { background: #fff6e8; border-right: 4px solid #d99a45; margin: 4mm 0; padding: 2mm 4mm; }
code { direction: ltr; font-family: "DejaVu Sans Mono", monospace; font-size: 0.88em; unicode-bidi: embed; }
a { color: #8b4a13; text-decoration: none; }
hr { border: 0; border-top: 1px solid #d9dce2; margin: 7mm 0; }
ul, ol { padding-right: 7mm; }
input[type="checkbox"] { margin-left: 2mm; }
"""


def render(source_name: str, output_name: str, title: str) -> None:
    if not CHROME:
        raise SystemExit("google-chrome or chromium is required")
    source = MANUAL_DIR / source_name
    output = MANUAL_DIR / output_name
    body = markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=("tables", "fenced_code", "sane_lists"),
    )
    document = (
        '<!doctype html><html lang="ar" dir="rtl"><head>'
        '<meta charset="utf-8">'
        f"<title>{title}</title><style>{STYLE}</style></head>"
        f"<body>{body}</body></html>"
    )
    with tempfile.TemporaryDirectory(prefix="elkheima-manual-") as temp_dir:
        html_path = Path(temp_dir) / "manual.html"
        html_path.write_text(document, encoding="utf-8")
        subprocess.run(
            [
                CHROME,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                f"--print-to-pdf={output}",
                html_path.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        if not output.exists() or output.stat().st_size < 10_000:
            raise RuntimeError(f"PDF generation failed for {source_name}")
    print(f"generated {output.relative_to(ROOT)}")


def main() -> None:
    for manual in MANUALS:
        render(*manual)


if __name__ == "__main__":
    main()
