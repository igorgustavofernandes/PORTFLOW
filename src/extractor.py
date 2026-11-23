import io
import re
from datetime import datetime
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB (RF01 / RNF01)
MISSING_MARKER_PT = "[Não informado]"
MISSING_MARKER_EN = "[Not provided]"

FIELD_DEFINITIONS = [
    {
        "key": "vessel_name",
        "label": "Embarcação",
        "form_label": "Nome da embarcação",
        "anchors": [
            r"Embarca[cç][aã]o\s*:",
            r"Nome\s+da\s+embarca[cç][aã]o\s*:",
            r"Nome\s+do\s+navio\s*:",
            r"Navio\s*:",
            r"Vessel\s+name\s*:",
            r"Ship\s+name\s*:"
        ],
        "core": True,
        "type": "text"
    },
    {
        "key": "imo",
        "label": "Número IMO",
        "form_label": "IMO",
        "anchors": [
            r"C[oó]digo\s+IMO\s*:",
            r"N[uú]mero\s+IMO\s*:",
            r"IMO\s+number\s*:",
            r"IMO\s*:"
        ],
        "core": True,
        "type": "imo"
    },
    {
        "key": "voyage",
        "label": "Número da Viagem",
        "form_label": "Viagem / Processo",
        "anchors": [
            r"N[uú]mero\s+da\s+viagem\s*:",
            r"Processo\s*:",
            r"Viagem\s*:",
            r"Voyage\s+number\s*:",
            r"Voyage\s*:"
        ],
        "core": False,
        "type": "alphanumeric"
    },
    {
        "key": "port",
        "label": "Porto",
        "form_label": "Porto",
        "anchors": [
            r"Porto\s*:",
            r"Port\s*:"
        ],
        "core": True,
        "type": "text"
    },
    {
        "key": "berth",
        "label": "Berço / Terminal",
        "form_label": "Berço / Terminal",
        "anchors": [
            r"Ber[cç]o\s*:",
            r"Berth\s*:",
            r"Terminal\s*:"
        ],
        "core": True,
        "type": "text"
    },
    {
        "key": "status",
        "label": "Status Operacional",
        "form_label": "Status",
        "anchors": [
            r"Status\s+operacional\s*:",
            r"Estado\s+operacional\s*:",
            r"Operational\s+status\s*:",
            r"Status\s*:"
        ],
        "core": True,
        "type": "status"
    },
    {
        "key": "eta",
        "label": "Início da Operação / ETA",
        "form_label": "Início da operação / ETA",
        "anchors": [
            r"In[ií]cio\s+da\s+opera[cç][aã]o\s*:",
            r"ETA\s*:"
        ],
        "core": True,
        "type": "datetime"
    },
    {
        "key": "etb",
        "label": "ETB (Atracação)",
        "form_label": "ETB",
        "anchors": [
            r"ETB\s*:"
        ],
        "core": False,
        "type": "datetime"
    },
    {
        "key": "etc",
        "label": "Término Previsto / ETC",
        "form_label": "Término previsto / ETC",
        "anchors": [
            r"T[eé]rmino\s+previsto\s*:",
            r"ETC\s*:"
        ],
        "core": True,
        "type": "datetime"
    },
    {
        "key": "etd",
        "label": "ETD / Saída",
        "form_label": "ETD / ATD",
        "anchors": [
            r"ETD\s*:"
        ],
        "core": False,
        "type": "datetime"
    },
    {
        "key": "cargo",
        "label": "Carga",
        "form_label": "Carga",
        "anchors": [
            r"Carga\s*:",
            r"Cargo\s*:"
        ],
        "core": False,
        "type": "text"
    },
    {
        "key": "notes",
        "label": "Observações",
        "form_label": "Observações",
        "anchors": [
            r"Observa[cç][oõ]es\s*:",
            r"Operational\s+remarks\s*:",
            r"Remarks\s*:"
        ],
        "core": False,
        "type": "multiline"
    }
]

DATE_PATTERNS = [
    re.compile(r"^\d{2}/\d{2}/\d{4}\s*(?:[-–—]|\b(?:[àa]s|at)\b)?\s*\d{2}:\d{2}(?:\s*[A-Z]{2,4})?$", re.IGNORECASE),
    re.compile(r"^\d{2}/\d{2}\s*(?:[-–—]|\b(?:[àa]s|at)\b)?\s*\d{2}:\d{2}(?:\s*[A-Z]{2,4})?$", re.IGNORECASE),
    re.compile(r"^\d{4}-\d{2}-\d{2}\s*(?:[-–—T]|\b(?:at)\b)?\s*\d{2}:\d{2}(?:\s*[A-Z]{2,4})?$", re.IGNORECASE),
    re.compile(r"^(?:[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s*[-–—,]?\s*\d{2}:\d{2}(?:\s*[A-Z]{2,4})?$", re.IGNORECASE)
]


def is_valid_date_format(value: str) -> bool:
    val = value.strip().rstrip(".")
    if any(p.match(val) for p in DATE_PATTERNS):
        return True
    # Also accept structured operational timeline strings containing valid dates or "In progress" / "Not yet departed"
    if re.search(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4},?\s+\d{2}:\d{2}", val):
        return True
    if val.lower().startswith(("in progress", "not yet departed", "em andamento")):
        return True
    return False


def _is_missing_token(val: str) -> bool:
    if not val:
        return True
    clean = val.strip().lower()
    return clean in (
        "-", "—", "–", "n/a",
        "[não informado]", "[nao informado]", "não informado", "não identificado",
        "[not provided]", "not provided"
    )


def _parse_english_datetime(dt_str: str):
    """Parses '18 Nov 2026, 06:00 BRT' into a datetime object for chronological comparison."""
    if not dt_str:
        return None
    clean = re.sub(r"\s+[A-Z]{2,4}$", "", dt_str.strip())
    for fmt in ("%d %b %Y, %H:%M", "%d %B %Y, %H:%M", "%d/%m/%Y %H:%M", "%d/%m/%Y - %H:%M"):
        try:
            return datetime.strptime(clean, fmt)
        except ValueError:
            pass
    return None


def validate_and_read_pdf(filename: str, file_bytes: bytes):
    """
    Validates PDF format, size (<= 5 MB), corruption, and selectable text layer.
    Returns (ok: bool, result_or_error: dict).
    """
    if not filename or not filename.lower().endswith(".pdf"):
        return False, {
            "error_code": "CT02_INVALID_FORMAT",
            "message": "Arquivo rejeitado: formato inválido. Selecione apenas arquivos PDF (.pdf)."
        }

    size_bytes = len(file_bytes)
    if size_bytes == 0:
        return False, {
            "error_code": "CT04_EMPTY_FILE",
            "message": "Aviso de falha: o arquivo enviado está vazio ou corrompido."
        }

    if size_bytes > MAX_FILE_SIZE_BYTES:
        size_mb = round(size_bytes / (1024 * 1024), 2)
        return False, {
            "error_code": "CT03_SIZE_EXCEEDED",
            "message": f"Arquivo rejeitado: o arquivo possui {size_mb} MB e excede o limite máximo de 5 MB (RNF01)."
        }

    if not file_bytes.lstrip().startswith(b"%PDF-"):
        return False, {
            "error_code": "CT04_CORRUPTED_PDF",
            "message": "Aviso de falha: arquivo PDF corrompido ou cabeçalho inválido."
        }

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)
        if page_count == 0:
            return False, {
                "error_code": "CT04_NO_PAGES",
                "message": "Aviso de falha: o documento PDF não contém páginas válidas."
            }

        pages_text = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            pages_text.append(txt.strip())

        full_text = "\n".join(t for t in pages_text if t).strip()
    except (PdfReadError, Exception) as exc:
        return False, {
            "error_code": "CT04_CORRUPTED_PDF",
            "message": f"Aviso de falha: não foi possível ler o PDF (arquivo corrompido). Detalhe: {str(exc)}"
        }

    if not full_text or len(re.sub(r"\s+", "", full_text)) < 5:
        return False, {
            "error_code": "CT05_NO_SELECTABLE_TEXT",
            "message": "Aviso de falha: o PDF não possui camada de texto selecionável (documento digitalizado sem OCR)."
        }

    return True, {
        "page_count": page_count,
        "size_bytes": size_bytes,
        "raw_text": full_text
    }


def _extract_english_tabular_report(text: str):
    """
    Parses the English PORTFLOW Classroom Test Package PDFs:
    - 01_complete_operational_report.pdf
    - 02_report_with_missing_fields.pdf
    - 03_report_with_inconsistencies.pdf
    - 04_reference_data.pdf
    Returns a dict of raw key-value pairs and custom field warnings if matched.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Exact row labels used in 01, 02, 03, 04 PDFs
    known_row_labels = {
        "report id": "report_id",
        "report date": "report_date",
        "reporting operator": "reporting_operator",
        "source email": "source_email",
        "document type": "document_type",
        "customer id": "customer_id",
        "customer / company": "company_name",
        "company name": "company_name",
        "customer contact": "contact_name",
        "contact name": "contact_name",
        "customer destination email": "destination_email",
        "destination email": "destination_email",
        "vessel id": "vessel_id",
        "vessel name": "vessel_name",
        "imo number": "imo",
        "imo": "imo",
        "voyage number (sample)": "voyage",
        "voyage number": "voyage",
        "port": "port",
        "terminal": "berth",
        "berth": "berth",
        "operation": "operation_type",
        "cargo description": "cargo_desc",
        "cargo quantity": "cargo_qty",
        "cargo unit": "cargo_unit",
        "eta (estimated arrival)": "eta_raw",
        "ata (actual arrival)": "ata_raw",
        "etb (estimated berthing)": "etb",
        "atd (actual departure)": "etd",
        "operation start": "op_start",
        "operation end": "op_end",
        "operational status": "status",
        "delay / interruption reason": "delay_reason",
        "operational remarks": "remarks_raw",
        "next update": "next_update"
    }

    section_headers = {
        "field", "value", "reference value", "report metadata", "customer", "customer record",
        "vessel", "port and operation", "operational timeline", "status and remarks",
        "validation checks", "additional notes", "portflow"
    }

    kv = {}
    i = 0
    while i < len(lines):
        line_clean = lines[i]
        line_lower = line_clean.lower()

        if line_lower in known_row_labels:
            target_key = known_row_labels[line_lower]
            # Collect value lines until the next known label or section header
            val_lines = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_lower = nxt.lower()
                if (
                    nxt_lower in known_row_labels
                    or nxt_lower in section_headers
                    or nxt_lower.startswith("this document is fictional")
                    or nxt_lower.startswith("all names, identifiers, companies")
                ):
                    break
                # For single-line fields (everything except remarks_raw), take only 1 line
                val_lines.append(nxt)
                if target_key != "remarks_raw":
                    j += 1
                    break
                j += 1

            if val_lines and target_key not in kv:
                kv[target_key] = " ".join(val_lines).strip()
            i = j
            continue

        # Also check inline table format (e.g. "Vessel name MV Aurora Meridian")
        for lbl_lower, target_key in known_row_labels.items():
            if line_lower.startswith(lbl_lower + " ") and target_key not in kv:
                inline_val = line_clean[len(lbl_lower):].strip().lstrip(":").strip()
                if inline_val and not inline_val.lower().startswith("is the reference"):
                    kv[target_key] = inline_val
                    break
        i += 1

    return kv


def extract_fields_from_text(raw_text: str):
    """
    Extracts operational data using case-insensitive anchors in both Portuguese and English,
    supporting both colon-delimited ('IMO: 9387421') and tabular ('IMO number \\n 9312341') PDF layouts.
    """
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # 1. Try colon-delimited anchor extraction first
    anchor_patterns = []
    for fdef in FIELD_DEFINITIONS:
        for pat in fdef["anchors"]:
            anchor_patterns.append((fdef["key"], pat))

    occurrences = []
    for key, pat in anchor_patterns:
        for m in re.finditer(rf"(?:^|\n|\s)({pat})", text, flags=re.IGNORECASE):
            occurrences.append({
                "key": key,
                "anchor_start": m.start(1),
                "value_start": m.end(1),
                "matched_anchor": m.group(1)
            })

    occurrences.sort(key=lambda x: x["anchor_start"])

    extracted_occurrences = {}
    for idx, occ in enumerate(occurrences):
        key = occ["key"]
        start_pos = occ["value_start"]
        end_pos = occurrences[idx + 1]["anchor_start"] if idx + 1 < len(occurrences) else len(text)
        segment = text[start_pos:end_pos]

        fdef = next(f for f in FIELD_DEFINITIONS if f["key"] == key)
        if fdef["type"] != "multiline":
            first_line = segment.split("\n")[0].strip()
            val = first_line
        else:
            lines = []
            for line in segment.split("\n"):
                clean_l = line.strip()
                if any(footer in clean_l.lower() for footer in [
                    "documento padronizado pronto para leitura",
                    "sigecar - boletim",
                    "portflow - boletim",
                    "fim do boletim",
                    "this document is fictional",
                    "all names, identifiers"
                ]):
                    break
                if clean_l:
                    lines.append(clean_l)
            val = " ".join(lines).strip()

        if fdef["type"] != "multiline" and val.endswith("."):
            val = val[:-1].strip()

        val = val.lstrip("•*- ").strip()
        if val:
            extracted_occurrences.setdefault(key, []).append(val)

    # 2. Check English Tabular Format (01, 02, 03, 04 classroom PDFs)
    custom_field_badges = {}
    custom_warnings = []
    tabular_kv = _extract_english_tabular_report(text)

    if tabular_kv:
        # Map simple direct fields if not already found via colon anchors
        for direct_key in ("vessel_name", "imo", "voyage", "port", "berth", "status", "etb", "etd"):
            if direct_key not in extracted_occurrences and direct_key in tabular_kv:
                extracted_occurrences[direct_key] = [tabular_kv[direct_key]]

        # Composite ETA / ATA / Operation start handling + Chronology Check (03_report_with_inconsistencies.pdf)
        if "eta" not in extracted_occurrences:
            eta_raw = tabular_kv.get("eta_raw", "")
            ata_raw = tabular_kv.get("ata_raw", "")
            op_start = tabular_kv.get("op_start", "")

            if eta_raw and ata_raw and not _is_missing_token(eta_raw) and not _is_missing_token(ata_raw):
                dt_eta = _parse_english_datetime(eta_raw)
                dt_ata = _parse_english_datetime(ata_raw)
                if dt_eta and dt_ata and dt_ata < dt_eta:
                    # Chronological inconsistency detected! (ATA earlier than ETA)
                    extracted_occurrences["eta"] = [f"ETA: {eta_raw} | ATA: {ata_raw}"]
                    custom_field_badges["eta"] = ("pending", "Inconsistência: ATA anterior ao ETA")
                    custom_warnings.append(
                        f"Inconsistência cronológica detectada: a chegada real (ATA: {ata_raw}) é anterior à chegada estimada (ETA: {eta_raw})."
                    )
                else:
                    extracted_occurrences["eta"] = [op_start if (op_start and not _is_missing_token(op_start)) else eta_raw]
            elif op_start or eta_raw:
                extracted_occurrences["eta"] = [op_start or eta_raw]

        # Composite ETC / Operation end / Next update
        if "etc" not in extracted_occurrences:
            op_end = tabular_kv.get("op_end", "")
            next_upd = tabular_kv.get("next_update", "")
            if op_end and not _is_missing_token(op_end):
                if next_upd and not _is_missing_token(next_upd):
                    extracted_occurrences["etc"] = [f"{op_end} (Próx. atualização: {next_upd})"]
                else:
                    extracted_occurrences["etc"] = [op_end]
            elif next_upd:
                extracted_occurrences["etc"] = [next_upd]

        # Composite Cargo (Cargo description + Cargo quantity + Cargo unit + Operation)
        if "cargo" not in extracted_occurrences:
            c_desc = tabular_kv.get("cargo_desc", "")
            c_qty = tabular_kv.get("cargo_qty", "")
            c_unit = tabular_kv.get("cargo_unit", "")
            op_type = tabular_kv.get("operation_type", "")

            if c_desc and not _is_missing_token(c_desc):
                if "cargo_qty" in tabular_kv and _is_missing_token(c_qty):
                    # Missing cargo quantity (02_report_with_missing_fields.pdf)
                    extracted_occurrences["cargo"] = [f"{c_desc} — Quantidade: [Não informado]"]
                    custom_field_badges["cargo"] = ("pending", "Quantidade de carga não informada")
                    custom_warnings.append("A quantidade da carga (Cargo quantity) não foi informada no documento.")
                elif c_qty:
                    unit_part = f" {c_unit}" if (c_unit and not _is_missing_token(c_unit)) else ""
                    op_part = f" ({op_type})" if (op_type and not _is_missing_token(op_type)) else ""
                    extracted_occurrences["cargo"] = [f"{c_desc} — {c_qty}{unit_part}{op_part}"]
                else:
                    extracted_occurrences["cargo"] = [c_desc]

        # Composite Operational Remarks + Delay / Interruption reason
        if "notes" not in extracted_occurrences:
            rem = tabular_kv.get("remarks_raw", "")
            delay = tabular_kv.get("delay_reason", "")
            if rem or delay:
                if "delay_reason" in tabular_kv and _is_missing_token(delay):
                    # Missing delay reason (02_report_with_missing_fields.pdf)
                    base_rem = rem if not _is_missing_token(rem) else ""
                    combined = f"{base_rem} | Motivo de atraso: [Não informado]".lstrip(" |")
                    extracted_occurrences["notes"] = [combined]
                    custom_field_badges["notes"] = ("pending", "Motivo de atraso não informado")
                    custom_warnings.append("O campo 'Delay / interruption reason' está ausente ([NOT PROVIDED]).")
                elif delay and not _is_missing_token(delay) and delay.lower() != "no delay reported":
                    extracted_occurrences["notes"] = [f"{rem} (Atraso: {delay})".strip()]
                elif rem:
                    extracted_occurrences["notes"] = [rem]

    if not extracted_occurrences:
        return {
            "recognized_pattern": False,
            "error_message": "Aviso de falha: o PDF possui texto, mas não apresenta dados operacionais nem âncoras reconhecidas.",
            "fields": {},
            "field_meta": {},
            "summary": {"found": 0, "pending": 7, "total": 7, "read_rate": 0}
        }

    has_extended_fields = any(
        k in extracted_occurrences for k in ("voyage", "etb", "etd", "cargo", "notes")
    )

    fields = {}
    field_meta = {}
    warnings = list(custom_warnings)

    for fdef in FIELD_DEFINITIONS:
        key = fdef["key"]
        raw_vals = extracted_occurrences.get(key, [])

        non_empty_vals = [v for v in raw_vals if not _is_missing_token(v)]
        unique_vals = []
        for v in non_empty_vals:
            if v not in unique_vals:
                unique_vals.append(v)

        is_duplicate = len(unique_vals) > 1
        raw_val = unique_vals[0] if unique_vals else ""

        if fdef["type"] == "imo" and raw_val:
            m_imo = re.search(r"\b(\d{7})\b", raw_val)
            if m_imo:
                raw_val = m_imo.group(1)

        is_missing = _is_missing_token(raw_val)

        status_badge = "Encontrado"
        state = "valid"
        display_value = raw_val

        if is_missing:
            display_value = MISSING_MARKER_PT
            state = "pending"
            status_badge = "Pendente na revisão"
        else:
            if fdef["type"] == "imo":
                if len(raw_val) == 7 and raw_val.isdigit():
                    status_badge = "7 dígitos válidos"
                else:
                    state = "pending"
                    status_badge = "Formato IMO inválido (exige 7 dígitos)"
                    warnings.append(f"O código IMO '{raw_val}' não possui 7 dígitos numéricos.")
            elif fdef["type"] == "datetime":
                if is_valid_date_format(raw_val):
                    status_badge = "Horário validado"
                else:
                    state = "pending"
                    status_badge = "Formato de data requer revisão"
                    warnings.append(f"A data/hora em '{fdef['label']}' ({raw_val}) requer conferência manual.")
            elif fdef["type"] == "status":
                status_badge = "Encontrado no PDF"

            if is_duplicate:
                state = "pending"
                status_badge = f"Ambiguidade detectada ({ ' / '.join(unique_vals) })"
                warnings.append(f"O campo '{fdef['label']}' aparece duplicado no PDF ({', '.join(unique_vals)}). Confira o valor correto.")

            if key in custom_field_badges:
                state, status_badge = custom_field_badges[key]

        include_in_cards = fdef["core"] or has_extended_fields or (not is_missing)

        fields[key] = display_value
        field_meta[key] = {
            "key": key,
            "label": fdef["label"],
            "form_label": fdef["form_label"],
            "value": display_value,
            "raw_value": "" if is_missing else raw_val,
            "is_missing": is_missing,
            "is_duplicate": is_duplicate,
            "state": state,
            "status_badge": status_badge,
            "core": fdef["core"],
            "include_in_cards": include_in_cards
        }

    active_metas = [m for m in field_meta.values() if m["include_in_cards"]]
    total_active = len(active_metas)
    found_count = sum(1 for m in active_metas if m["state"] == "valid")
    pending_count = total_active - found_count
    read_rate = round((found_count / total_active) * 100) if total_active > 0 else 0

    return {
        "recognized_pattern": True,
        "has_extended_fields": has_extended_fields,
        "fields": fields,
        "field_meta": field_meta,
        "warnings": warnings,
        "summary": {
            "found": found_count,
            "pending": pending_count,
            "total": total_active,
            "read_rate": read_rate
        }
    }
