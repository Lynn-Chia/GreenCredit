"""Generate PDF versions of every .txt sample for upload testing."""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).parent
STYLES = getSampleStyleSheet()

mono = ParagraphStyle(
    "mono",
    parent=STYLES["Code"],
    fontName="Courier",
    fontSize=9,
    leading=11.5,
    textColor=HexColor("#101a14"),
)

title_style = ParagraphStyle(
    "title",
    parent=STYLES["Heading2"],
    textColor=HexColor("#0f6536"),
    spaceAfter=6,
)


def txt_to_pdf(txt_path: Path) -> Path:
    pdf_path = txt_path.with_suffix(".pdf")
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=txt_path.stem.replace("_", " ").title(),
    )
    flowables = [Paragraph(txt_path.stem.replace("_", " ").title(), title_style), Spacer(1, 6)]
    for raw in txt_path.read_text().splitlines():
        line = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if not line.strip():
            flowables.append(Spacer(1, 6))
            continue
        # Preserve leading whitespace by replacing with non-breaking spaces.
        leading = len(line) - len(line.lstrip(" "))
        line = (" " * leading) + line.lstrip(" ")
        flowables.append(Paragraph(line, mono))
    doc.build(flowables)
    return pdf_path


def main() -> None:
    txts = sorted(ROOT.rglob("*.txt"))
    if not txts:
        print("No .txt samples found.")
        return
    for t in txts:
        pdf = txt_to_pdf(t)
        print(f"  {pdf.relative_to(ROOT)}")
    print(f"\nGenerated {len(txts)} PDFs.")


if __name__ == "__main__":
    main()
