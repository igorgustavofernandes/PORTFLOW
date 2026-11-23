import os
import shutil
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    DEFAULT_SAMPLE_DIR = Path(sys.executable).parent / "sample_pdfs"
    BUNDLED_SAMPLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "sample_pdfs"
else:
    DEFAULT_SAMPLE_DIR = Path(__file__).parent / "sample_pdfs"
    BUNDLED_SAMPLE_DIR = DEFAULT_SAMPLE_DIR

SAMPLE_DIR = Path(os.environ.get("PORTFLOW_SAMPLE_DIR", str(DEFAULT_SAMPLE_DIR)))


def _escape_pdf_text(text: str) -> bytes:
    """Encodes string in cp1252 (WinAnsiEncoding) and escapes PDF string literals."""
    raw = text.encode("cp1252", errors="replace")
    out = bytearray()
    for b in raw:
        if b in (40, 41, 92):  # '(', ')', '\'
            out.append(92)
        out.append(b)
    return bytes(out)


def build_valid_pdf(title_left: str, title_right: str, lines: list[str], footer: str = "Documento padronizado pronto para leitura automática.") -> bytes:
    """
    Generates a clean, valid single-page PDF 1.4 document with WinAnsiEncoding
    so Portuguese accents render cleanly in Chrome PDF viewer and extract with pypdf.
    """
    stream_cmds = []

    # Header title
    stream_cmds.append(b"BT /F2 13 Tf 50 760 Td (")
    stream_cmds.append(_escape_pdf_text(title_left))
    stream_cmds.append(b") Tj ET")

    stream_cmds.append(b"BT /F1 10 Tf 460 760 Td (")
    stream_cmds.append(_escape_pdf_text(title_right))
    stream_cmds.append(b") Tj ET")

    # Horizontal divider line
    stream_cmds.append(b"0.07 0.15 0.24 RG 1.2 w 50 742 m 545 742 l S")

    # Content lines
    y = 712
    for line in lines:
        if not line:
            y -= 12
            continue
        stream_cmds.append(f"BT /F1 11 Tf 50 {y} Td (".encode("ascii"))
        stream_cmds.append(_escape_pdf_text(line))
        stream_cmds.append(b") Tj ET")
        y -= 24

    # Footer divider and note
    if footer:
        stream_cmds.append(b"0.85 0.88 0.91 RG 0.8 w 50 110 m 545 110 l S")
        stream_cmds.append(b"BT /F1 9.5 Tf 50 92 Td (")
        stream_cmds.append(_escape_pdf_text(footer))
        stream_cmds.append(b") Tj ET")

    content_stream = b"\n".join(stream_cmds)

    objects = []
    # 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # 2: Pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    # 3: Page
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n"
    )
    # 4: Font regular (Helvetica with WinAnsiEncoding)
    objects.append(
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n"
    )
    # 5: Font bold (Helvetica-Bold with WinAnsiEncoding)
    objects.append(
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n"
    )
    # 6: Content stream
    objects.append(
        f"6 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
        + content_stream
        + b"\nendstream\nendobj\n"
    )

    pdf_out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf_out))
        pdf_out.extend(obj)

    xref_pos = len(pdf_out)
    pdf_out.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf_out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf_out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    pdf_out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf_out)


def build_blank_pdf_no_text() -> bytes:
    """Generates a valid PDF with no text layer (to test CT05 - scanned/blank PDF)."""
    content_stream = b"0.9 0.9 0.9 rg 50 50 495 742 re f"
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("ascii") + content_stream + b"\nendstream\nendobj\n"
    ]
    pdf_out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf_out))
        pdf_out.extend(obj)
    xref_pos = len(pdf_out)
    pdf_out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        pdf_out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf_out.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii"))
    return bytes(pdf_out)


def generate_all_samples():
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    if BUNDLED_SAMPLE_DIR != SAMPLE_DIR and BUNDLED_SAMPLE_DIR.exists():
        for item in BUNDLED_SAMPLE_DIR.iterdir():
            if item.is_file():
                target = SAMPLE_DIR / item.name
                if not target.exists():
                    shutil.copy2(item, target)

    # 1. Exact Prototype PDF (Slides 3, 4, 5, 7, 8)
    pdf1 = build_valid_pdf(
        "BOLETIM OPERACIONAL PORTUÁRIO",
        "PARANAGUÁ",
        [
            "Embarcação: MV Atlantic Star",
            "IMO: 9387421",
            "Porto: Paranaguá",
            "Berço: 214",
            "Status: Atracada",
            "Início da operação: 19/11 às 06:40",
            "Término previsto: -"
        ]
    )
    (SAMPLE_DIR / "BOLETIM_ATLANTIC_STAR_1911.pdf").write_bytes(pdf1)

    # 2. Exact MVP Specification Section 11 PDF (CT06 / CT07 - IMO 9876543 complete)
    pdf2 = build_valid_pdf(
        "BOLETIM OPERACIONAL PORTUÁRIO",
        "PARANAGUÁ",
        [
            "Embarcação: Atlantic Star",
            "IMO: 9876543",
            "Viagem: VJ2026-014",
            "Porto: Paranaguá",
            "Berço: 201",
            "Status: Operando",
            "ETA: 17/11/2026 - 08:00",
            "ETB: 17/11/2026 - 09:00",
            "ETC: 17/11/2026 - 17:00",
            "ETD: 17/11/2026 - 18:00",
            "Carga: Contêineres",
            "Observações: Aguardando liberação."
        ]
    )
    (SAMPLE_DIR / "BOLETIM_COMPLETO_9876543.pdf").write_bytes(pdf2)

    # 3. Unregistered Vessel IMO 1111111 (CT08 / CT11 / CT12 - Manual link & Vessel registration)
    pdf3 = build_valid_pdf(
        "BOLETIM OPERACIONAL PORTUÁRIO",
        "PARANAGUÁ",
        [
            "Embarcação: MV Pacific Explorer",
            "IMO: 1111111",
            "Viagem: VJ2026-088",
            "Porto: Paranaguá",
            "Berço: 218",
            "Status: Atracada",
            "Início da operação: 19/11/2026 09:15",
            "Término previsto: 20/11/2026 18:00",
            "Carga: Granel Sólido",
            "Observações: Operação iniciada normalmente no Berço 218."
        ]
    )
    (SAMPLE_DIR / "BOLETIM_IMO_NAO_CADASTRADO_1111111.pdf").write_bytes(pdf3)

    # 4. Auxiliary Search by Vessel Name (CT09 - IMO missing, Name matches "Atlantic Star")
    pdf4 = build_valid_pdf(
        "BOLETIM OPERACIONAL PORTUÁRIO",
        "PARANAGUÁ",
        [
            "Embarcação: Atlantic Star",
            "IMO: -",
            "Viagem: VJ2026-022",
            "Porto: Paranaguá",
            "Berço: 204",
            "Status: Atracada",
            "Início da operação: 19/11/2026 10:00",
            "Término previsto: 19/11/2026 22:00"
        ]
    )
    (SAMPLE_DIR / "BOLETIM_BUSCA_POR_NOME_CT09.pdf").write_bytes(pdf4)

    # 5. Scanned / No Selectable Text PDF (CT05)
    pdf5 = build_blank_pdf_no_text()
    (SAMPLE_DIR / "BOLETIM_SEM_TEXTO_CT05.pdf").write_bytes(pdf5)

    # 6. Corrupted PDF (CT04)
    (SAMPLE_DIR / "BOLETIM_CORROMPIDO_CT04.pdf").write_bytes(b"%PDF-1.4\nCORRUPTED_BINARY_STREAM_INVALID_XREF")

    # 7. Invalid TXT file (CT02)
    (SAMPLE_DIR / "ARQUIVO_INVALIDO_CT02.txt").write_text(
        "Embarcação: MV Atlantic Star\nIMO: 9387421\nEste arquivo é TXT e deve ser rejeitado (CT02).",
        encoding="utf-8"
    )


if __name__ == "__main__":
    generate_all_samples()
    print("Sample files generated successfully in:", SAMPLE_DIR)
