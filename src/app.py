import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_from_directory, session

import database
import extractor
import generate_sample_pdfs

if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    app = Flask(
        __name__,
        template_folder=str(BUNDLE_DIR / "templates"),
        static_folder=str(BUNDLE_DIR / "static")
    )
else:
    BUNDLE_DIR = Path(__file__).parent
    app = Flask(__name__)

app.secret_key = "sigecar-maritime-agency-secret-key-2026"
SAMPLE_DIR = generate_sample_pdfs.SAMPLE_DIR


def format_file_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB".replace(".", ",")
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB".replace(".", ",")
    return f"{size_bytes} B"


def build_email_drafts(fields: dict, customer: dict | None):
    """
    RF08 / RN04 / RN05:
    Generates standardized email templates in BOTH English (Tech Shark Tank & UI Prototype Slide 7)
    and Portuguese (MVP Specification Section 11), using ONLY extracted/reviewed data and customer record.
    """
    def val_pt(key):
        v = (fields.get(key) or "").strip()
        return v if v and v not in ("-", "Não identificado") else "[Não informado]"

    def val_en(key, default_missing="[Not provided]"):
        v = (fields.get(key) or "").strip()
        if not v or v in ("-", "[Não informado]", "Não identificado"):
            return default_missing
        return v

    vessel_name_pt = val_pt("vessel_name")
    vessel_name_en = val_en("vessel_name")
    imo_pt = val_pt("imo")
    imo_en = val_en("imo")
    voyage_pt = val_pt("voyage")
    voyage_en = val_en("voyage")
    port_pt = val_pt("port")
    port_en = val_en("port")
    berth_pt = val_pt("berth")
    berth_en = val_en("berth")
    status_pt = val_pt("status")
    eta_pt = val_pt("eta")
    eta_en = val_en("eta")
    etb_pt = val_pt("etb")
    etb_en = val_en("etb")
    etc_pt = val_pt("etc")
    etc_en = val_en("etc", "Pending confirmation from terminal")
    etd_pt = val_pt("etd")
    etd_en = val_en("etd")
    cargo_pt = val_pt("cargo")
    cargo_en = val_en("cargo")
    notes_pt = val_pt("notes")
    notes_en = val_en("notes")

    status_map_en = {
        "atracada": "Berthed (Atracada)",
        "operando": "Operating (Operando)",
        "fundeada": "Anchored (Fundeada)",
        "aguardando atracação": "Awaiting Berth (Aguardando Atracação)",
        "desatracada": "Unberthed (Desatracada)"
    }
    status_en = status_map_en.get(status_pt.lower(), status_pt if status_pt != "[Não informado]" else "[Not provided]")
    eta_en_clean = eta_en.replace(" às ", " at ")

    company_name = customer["company_name"] if customer else "Client"
    short_team = company_name.split()[0] if customer else "Customer"
    dest_email = customer["destination_email"] if customer else ""

    # 1. English Template (Matches Prototype Slide 7 & Tech Shark Tank Briefing — Rebranded to SIGECAR)
    subject_en = f"Operational Update – {vessel_name_en} (IMO {imo_en}) – Port of {port_en}"
    en_lines = [
        f"Dear {short_team} Team,",
        "",
        f"Please find below the latest operational update for {vessel_name_en} (IMO: {imo_en}):",
    ]
    if voyage_en != "[Not provided]":
        en_lines.append(f"• Voyage / Process: {voyage_en}")
    en_lines.extend([
        f"• Port / Berth: {port_en} – Berth {berth_en}",
        f"• Current Status: {status_en}",
        f"• Operation Start: {eta_en_clean}",
    ])
    if etb_en != "[Not provided]":
        en_lines.append(f"• ETB: {etb_en}")
    en_lines.append(f"• Estimated Completion: {etc_en}")
    if etd_en != "[Not provided]":
        en_lines.append(f"• ETD: {etd_en}")
    if cargo_en != "[Not provided]":
        en_lines.append(f"• Cargo: {cargo_en}")
    if notes_en != "[Not provided]":
        en_lines.append(f"• Remarks: {notes_en}")

    en_lines.extend([
        "",
        "Best regards,",
        "Port Operations Team — SIGECAR"
    ])
    body_en = "\n".join(en_lines)

    # 2. Portuguese Template (Matches MVP Specification Section 11 exact format — Rebranded to SIGECAR)
    subject_pt = f"Atualização operacional – {vessel_name_pt}"
    pt_lines = [
        f"Olá, equipe {short_team}!",
        "",
        f"Segue a atualização operacional da embarcação {vessel_name_pt}:",
        f"• IMO: {imo_pt}.",
        f"• Viagem: {voyage_pt}.",
        f"• Porto e berço: Porto de {port_pt} – Berço {berth_pt}.",
        f"• Status: {status_pt}.",
        f"• ETA: {eta_pt}.",
        f"• ETB: {etb_pt}.",
        f"• ETC: {etc_pt}.",
        f"• ETD: {etd_pt}.",
        f"• Carga: {cargo_pt}.",
        f"• Observações: {notes_pt if notes_pt.endswith('.') else notes_pt + '.'}",
        "",
        "Atenciosamente,",
        "Equipe Operacional — SIGECAR"
    ]
    body_pt = "\n".join(pt_lines)

    return {
        "destination_email": dest_email,
        "en": {
            "subject": subject_en,
            "body": body_en
        },
        "pt": {
            "subject": subject_pt,
            "body": body_pt
        }
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    identifier = data.get("username", "")
    password = data.get("password", "")

    user = database.authenticate_user(identifier, password)
    if not user:
        return jsonify({
            "ok": False,
            "message": "Credenciais inválidas. Verifique seu usuário/e-mail e senha."
        }), 401

    session["user"] = user
    return jsonify({
        "ok": True,
        "message": f"Bem-vindo ao SIGECAR, {user['name']}!",
        "user": user
    })


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("user", None)
    return jsonify({"ok": True, "message": "Sessão encerrada com sucesso."})


@app.route("/api/bootstrap", methods=["GET"])
def api_bootstrap():
    samples = [
        {
            "filename": "01_complete_operational_report.pdf",
            "title": "01 • Complete Operational Report (MV Aurora Meridian • IMO 9312341)",
            "description": "Caso Normal (Inglês): todos os campos populados e consistentes com OceanBridge Logistics",
            "badge": "Test Pack 01",
            "type": "valid"
        },
        {
            "filename": "02_report_with_missing_fields.pdf",
            "title": "02 • Report with Missing Fields (MV Aurora Meridian • Sem IMO)",
            "description": "Dados Ausentes (Inglês): IMO, Terminal, Qtd. Carga, ATD e Atraso como [NOT PROVIDED]",
            "badge": "Test Pack 02",
            "type": "warning"
        },
        {
            "filename": "03_report_with_inconsistencies.pdf",
            "title": "03 • Report with Inconsistencies (Conflito Nome/IMO + ATA < ETA)",
            "description": "Inconsistência (Inglês): IMO 9312341 com nome MV Atlantic Star e chegada ATA anterior ao ETA",
            "badge": "Test Pack 03",
            "type": "warning"
        },
        {
            "filename": "04_reference_data.pdf",
            "title": "04 • Fictional Reference Data (Ground Truth Sheet)",
            "description": "Planilha de referência: OceanBridge Logistics Ltd. & MV Aurora Meridian (IMO 9312341)",
            "badge": "Reference 04",
            "type": "valid"
        },
        {
            "filename": "BOLETIM_ATLANTIC_STAR_1911.pdf",
            "title": "Protótipo Oficial (MV Atlantic Star • IMO 9387421)",
            "description": "6 campos encontrados e 1 campo pendente (Término previsto ausente) — Taxa 86%",
            "badge": "Protótipo Slides 3–8",
            "type": "valid"
        },
        {
            "filename": "BOLETIM_COMPLETO_9876543.pdf",
            "title": "Boletim Completo PT-BR (Atlantic Star • IMO 9876543)",
            "description": "Todos os 12 campos operacionais preenchidos (ETA, ETB, ETC, ETD, Carga, Observações)",
            "badge": "CT01 / CT06 / CT07",
            "type": "valid"
        },
        {
            "filename": "BOLETIM_IMO_NAO_CADASTRADO_1111111.pdf",
            "title": "IMO Não Cadastrado (MV Pacific Explorer • IMO 1111111)",
            "description": "Testa vínculo manual com cliente ou cadastro de nova embarcação na Etapa 4",
            "badge": "CT08 / CT11 / CT12",
            "type": "warning"
        },
        {
            "filename": "BOLETIM_BUSCA_POR_NOME_CT09.pdf",
            "title": "Busca Auxiliar por Nome (IMO ausente • Navio Atlantic Star)",
            "description": "Testa sugestão automática pelo nome do navio exigindo confirmação humana",
            "badge": "CT09 / CT10",
            "type": "warning"
        }
    ]
    logged_user = session.get("user")
    return jsonify({
        "authenticated": logged_user is not None,
        "user": logged_user or database.get_default_user(),
        "users": database.list_all_users(),
        "customers": database.list_all_customers(),
        "vessels": database.list_all_vessels(),
        "history": database.list_approval_history(),
        "samples": samples
    })


@app.route("/api/sample-file/<path:filename>", methods=["GET"])
def serve_sample_file(filename):
    return send_from_directory(SAMPLE_DIR, filename)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    sample_name = request.form.get("sample_name")
    if sample_name:
        sample_path = SAMPLE_DIR / sample_name
        if not sample_path.exists():
            return jsonify({"ok": False, "message": "Arquivo de exemplo não encontrado."}), 404
        filename = sample_path.name
        file_bytes = sample_path.read_bytes()
    elif "file" in request.files:
        f = request.files["file"]
        filename = f.filename or ""
        file_bytes = f.read()
    else:
        return jsonify({"ok": False, "message": "Nenhum arquivo enviado."}), 400

    valid, val_result = extractor.validate_and_read_pdf(filename, file_bytes)
    if not valid:
        if val_result.get("error_code") in ("CT04_CORRUPTED_PDF", "CT05_NO_SELECTABLE_TEXT", "CT04_EMPTY_FILE"):
            database.create_pdf_processing(
                original_file_name=filename,
                extracted_data={"error": val_result["message"], "error_code": val_result["error_code"]},
                status="Falha"
            )
        return jsonify({
            "ok": False,
            "error_code": val_result.get("error_code"),
            "message": val_result.get("message")
        }), 400

    raw_text = val_result["raw_text"]
    extraction = extractor.extract_fields_from_text(raw_text)
    if not extraction["recognized_pattern"]:
        database.create_pdf_processing(
            original_file_name=filename,
            extracted_data={"error": extraction["error_message"]},
            status="Falha"
        )
        return jsonify({
            "ok": False,
            "error_code": "UNRECOGNIZED_ANCHORS",
            "message": extraction["error_message"]
        }), 400

    fields = extraction["fields"]
    extracted_imo = fields.get("imo", "")
    extracted_name = fields.get("vessel_name", "")

    # RN01 / BR01: Primary exact match by IMO
    imo_match = None
    name_conflict = None
    if extracted_imo and len(extracted_imo) == 7 and extracted_imo.isdigit():
        imo_match = database.find_vessel_by_imo(extracted_imo)
        # Check if the extracted vessel name conflicts with the reference database vessel name for this IMO
        if (
            imo_match
            and extracted_name
            and extracted_name != "[Não informado]"
            and extracted_name.strip().lower() != imo_match["vessel_name"].strip().lower()
        ):
            name_conflict = {
                "pdf_vessel_name": extracted_name,
                "db_vessel_name": imo_match["vessel_name"],
                "imo": extracted_imo,
                "company_name": imo_match["company_name"]
            }
            v_meta = extraction["field_meta"].get("vessel_name")
            if v_meta:
                v_meta["state"] = "pending"
                v_meta["status_badge"] = f"Conflito c/ IMO {extracted_imo} ({imo_match['vessel_name']})"
            extraction["warnings"].insert(
                0,
                f"Inconsistência detectada: o PDF informa o navio '{extracted_name}', mas o IMO {extracted_imo} pertence a '{imo_match['vessel_name']}' no cadastro de referência!"
            )
            # Recompute summary counts after flagging vessel_name conflict
            active_metas = [m for m in extraction["field_meta"].values() if m["include_in_cards"]]
            total_active = len(active_metas)
            found_count = sum(1 for m in active_metas if m["state"] == "valid")
            pending_count = total_active - found_count
            extraction["summary"] = {
                "found": found_count,
                "pending": pending_count,
                "total": total_active,
                "read_rate": round((found_count / total_active) * 100) if total_active > 0 else 0
            }

    # RN02 / BR02 / RF04 / CT09: Auxiliary search by vessel name if IMO did not match
    name_suggestions = []
    if not imo_match and extracted_name and extracted_name != "[Não informado]":
        name_suggestions = database.search_vessels_by_name(extracted_name)

    matched_vessel_id = imo_match["vessel_id"] if imo_match else None
    matched_customer_id = imo_match["customer_id"] if imo_match else None

    processing_id, received_at = database.create_pdf_processing(
        original_file_name=filename,
        extracted_data=fields,
        vessel_id=matched_vessel_id,
        customer_id=matched_customer_id,
        status="Aguardando Revisão"
    )

    received_time_short = datetime.now().strftime("%H:%M")
    drafts = build_email_drafts(fields, imo_match)

    return jsonify({
        "ok": True,
        "processing_id": processing_id,
        "file_info": {
            "filename": filename,
            "size_bytes": val_result["size_bytes"],
            "size_formatted": format_file_size(val_result["size_bytes"]),
            "page_count": val_result["page_count"],
            "received_at": received_at,
            "received_time_short": received_time_short,
            "raw_text": raw_text
        },
        "extraction": extraction,
        "imo_match": imo_match,
        "name_conflict": name_conflict,
        "name_suggestions": name_suggestions,
        "drafts": drafts
    })


@app.route("/api/review", methods=["POST"])
def api_review():
    data = request.get_json(force=True)
    processing_id = data.get("processing_id")
    if not processing_id:
        return jsonify({"ok": False, "message": "ID de processamento ausente."}), 400

    fields = data.get("fields", {})
    vessel_id = data.get("vessel_id") or None
    customer_id = data.get("customer_id") or None
    save_permanent = bool(data.get("save_permanent", False))

    if not customer_id:
        return jsonify({
            "ok": False,
            "message": "Selecione ou vincule um cliente destinatário antes de confirmar a revisão (BR11)."
        }), 400

    normalized_fields = {}
    for fdef in extractor.FIELD_DEFINITIONS:
        k = fdef["key"]
        v = (fields.get(k) or "").strip()
        if not v or v in ("-", "Não identificado"):
            normalized_fields[k] = "[Não informado]"
        else:
            normalized_fields[k] = v

    linked_vessel = None
    if save_permanent:
        try:
            linked_vessel = database.save_permanent_vessel_link(
                vessel_name=normalized_fields.get("vessel_name", ""),
                imo=normalized_fields.get("imo", ""),
                customer_id=int(customer_id),
                vessel_id=int(vessel_id) if vessel_id else None
            )
            vessel_id = linked_vessel["vessel_id"]
        except ValueError as err:
            return jsonify({"ok": False, "message": str(err)}), 400

    database.update_pdf_processing(
        processing_id=int(processing_id),
        extracted_data=normalized_fields,
        vessel_id=int(vessel_id) if vessel_id else None,
        customer_id=int(customer_id) if customer_id else None,
        status="Aguardando Revisão"
    )

    customers = database.list_all_customers()
    selected_customer = next((c for c in customers if c["customer_id"] == int(customer_id)), None)
    drafts = build_email_drafts(normalized_fields, selected_customer)

    return jsonify({
        "ok": True,
        "processing_id": processing_id,
        "fields": normalized_fields,
        "vessel_id": vessel_id,
        "customer": selected_customer,
        "permanent_saved": save_permanent,
        "linked_vessel": linked_vessel,
        "vessels": database.list_all_vessels(),
        "drafts": drafts
    })


@app.route("/api/vessels", methods=["POST"])
def api_create_vessel():
    data = request.get_json(force=True)
    vessel_name = data.get("vessel_name", "")
    imo = data.get("imo", "")
    customer_id = data.get("customer_id")
    processing_id = data.get("processing_id")

    if not customer_id:
        return jsonify({"ok": False, "message": "Selecione um cliente para vincular à nova embarcação."}), 400

    try:
        new_vessel = database.create_vessel(
            vessel_name=vessel_name,
            imo=imo,
            customer_id=int(customer_id)
        )
    except ValueError as err:
        return jsonify({"ok": False, "message": str(err)}), 400

    if processing_id:
        proc = database.get_pdf_processing(int(processing_id))
        if proc:
            ext_data = proc["extracted_data"]
            ext_data["vessel_name"] = new_vessel["vessel_name"]
            ext_data["imo"] = new_vessel["imo"]
            database.update_pdf_processing(
                processing_id=int(processing_id),
                extracted_data=ext_data,
                vessel_id=new_vessel["vessel_id"],
                customer_id=new_vessel["customer_id"],
                status="Aguardando Revisão"
            )

    return jsonify({
        "ok": True,
        "message": f"Embarcação '{new_vessel['vessel_name']}' (IMO {new_vessel['imo']}) cadastrada com sucesso!",
        "vessel": new_vessel,
        "vessels": database.list_all_vessels()
    })


@app.route("/api/approve", methods=["POST"])
def api_approve():
    data = request.get_json(force=True)
    processing_id = data.get("processing_id")
    destination_email = data.get("destination_email", "")
    email_subject = data.get("email_subject", "")
    email_body = data.get("email_body", "")
    user = session.get("user") or database.get_default_user()

    if not processing_id:
        return jsonify({"ok": False, "message": "Nenhum processamento ativo para aprovar."}), 400

    try:
        report = database.create_email_report(
            processing_id=int(processing_id),
            destination_email=destination_email,
            email_subject=email_subject,
            email_body=email_body,
            approving_user_id=user["user_id"]
        )
    except ValueError as err:
        return jsonify({"ok": False, "message": str(err)}), 400

    return jsonify({
        "ok": True,
        "message": "Relatório aprovado e envio simulado registrado com sucesso no banco de dados!",
        "report": report,
        "history": database.list_approval_history()
    })


@app.route("/api/history", methods=["GET"])
def api_history():
    return jsonify({
        "ok": True,
        "history": database.list_approval_history(),
        "vessels": database.list_all_vessels(),
        "customers": database.list_all_customers()
    })


if __name__ == "__main__":
    database.init_db()
    generate_sample_pdfs.generate_all_samples()
    print("=" * 62)
    print("  SIGECAR - Sistema de Gestao de Cargas Portuarias")
    print("  Servidor iniciado em: http://127.0.0.1:5000")
    print("  Mantenha esta janela aberta enquanto utiliza o sistema.")
    print("=" * 62)
    if getattr(sys, "frozen", False):
        threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
