import os
import secrets
import sqlite3
import json
import sys
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_APP_DIR = Path(sys.executable).parent
else:
    BASE_APP_DIR = Path(__file__).parent

DB_PATH = Path(os.environ.get("PORTFLOW_DB_PATH", str(BASE_APP_DIR / "portflow.db")))
CREDENTIALS_PATH = BASE_APP_DIR / ".first_run_credentials.txt"


def get_initial_password():
    """Returns a configured demo password or creates a local first-run credential."""
    configured_password = os.environ.get("PORTFLOW_DEFAULT_PASSWORD")
    if configured_password:
        return configured_password

    if CREDENTIALS_PATH.exists():
        return CREDENTIALS_PATH.read_text(encoding="utf-8").strip()

    generated_password = secrets.token_urlsafe(18)
    CREDENTIALS_PATH.write_text(generated_password, encoding="utf-8")
    return generated_password


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Table: User (ERD fields: user_id, name, role + login fields: email, username, password)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS User (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            role VARCHAR(60) NOT NULL,
            email VARCHAR(150),
            username VARCHAR(60),
            password VARCHAR(150)
        );
    """)

    # Smooth migration if table existed without email/username/password columns
    existing_cols = [r["name"] for r in cursor.execute("PRAGMA table_info(User);").fetchall()]
    if "email" not in existing_cols:
        cursor.execute("ALTER TABLE User ADD COLUMN email VARCHAR(150);")
    if "username" not in existing_cols:
        cursor.execute("ALTER TABLE User ADD COLUMN username VARCHAR(60);")
    if "password" not in existing_cols:
        cursor.execute("ALTER TABLE User ADD COLUMN password VARCHAR(150);")

    # Upgrade legacy plaintext passwords to Werkzeug password hashes.
    for user_row in cursor.execute("SELECT user_id, password FROM User WHERE password IS NOT NULL").fetchall():
        stored_password = user_row["password"]
        if not stored_password.startswith(("scrypt:", "pbkdf2:")):
            cursor.execute(
                "UPDATE User SET password = ? WHERE user_id = ?",
                (generate_password_hash(stored_password), user_row["user_id"])
            )

    initial_password = get_initial_password()

    # 2. Table: Customer
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Customer (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name VARCHAR(150) NOT NULL,
            contact_name VARCHAR(100),
            destination_email VARCHAR(254) NOT NULL
        );
    """)

    # 3. Table: Vessel
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Vessel (
            vessel_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vessel_name VARCHAR(100) NOT NULL,
            imo CHAR(7) NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES Customer(customer_id)
        );
    """)

    # 4. Table: PDF_Processing
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS PDF_Processing (
            processing_id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_file_name VARCHAR(255) NOT NULL,
            received_at DATETIME NOT NULL,
            extracted_data_json TEXT NOT NULL,
            vessel_id INTEGER NULL,
            customer_id INTEGER NULL,
            status VARCHAR(30) NOT NULL,
            FOREIGN KEY (vessel_id) REFERENCES Vessel(vessel_id),
            FOREIGN KEY (customer_id) REFERENCES Customer(customer_id)
        );
    """)

    # 5. Table: Email_Report
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Email_Report (
            email_report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            processing_id INTEGER NOT NULL UNIQUE,
            destination_email VARCHAR(254) NOT NULL,
            email_subject VARCHAR(200) NOT NULL,
            email_body TEXT NOT NULL,
            approving_user_id INTEGER NOT NULL,
            approval_date DATETIME NOT NULL,
            FOREIGN KEY (processing_id) REFERENCES PDF_Processing(processing_id),
            FOREIGN KEY (approving_user_id) REFERENCES User(user_id)
        );
    """)

    # Seed or update initial users with login credentials (keeping vitor and admin, adding Igor, Julia, Nicolly, Maria, Thales)
    default_team_users = [
        ("Vitor Cabral", "Operador", "vitor@sigecar.com.br", "vitor", initial_password),
        ("Administrador SIGECAR", "Supervisor Operacional", "admin@sigecar.com.br", "admin", initial_password),
        ("Igor", "Operador", "igor@sigecar.com.br", "igor", initial_password),
        ("Julia", "Operadora", "julia@sigecar.com.br", "julia", initial_password),
        ("Nicolly", "Operadora", "nicolly@sigecar.com.br", "nicolly", initial_password),
        ("Maria", "Operadora", "maria@sigecar.com.br", "maria", initial_password),
        ("Thales", "Operador", "thales@sigecar.com.br", "thales", initial_password)
    ]

    # Ensure user_id 1 (Vitor Cabral) has email/username/password if created earlier
    cursor.execute("""
        UPDATE User
        SET email = COALESCE(email, 'vitor@sigecar.com.br'),
            username = COALESCE(username, 'vitor'),
            password = COALESCE(password, ?)
        WHERE user_id = 1 AND LOWER(name) LIKE 'vitor%'
    """, (generate_password_hash(initial_password),))

    for name, role, email, username, pwd in default_team_users:
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM User WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
            (username, email)
        )
        if cursor.fetchone()["cnt"] == 0:
            cursor.execute(
                "INSERT INTO User (name, role, email, username, password) VALUES (?, ?, ?, ?, ?)",
                (name, role, email, username, generate_password_hash(pwd))
            )

    default_customers = [
        ("TransMar Maritime Agency", "Operations Team", "ops@transmar-agency.com"),
        ("TransMar Logística Global", "Equipe Operacional", "operacoes@transmarlogistica.com.br"),
        ("OceanBridge Logistics Ltd.", "Sofia Martins", "operations@oceanbridge.example"),
        ("Oceanic Global Lines", "Port Desk", "ops@oceaniclines.com"),
        ("South Atlantic Carriers", "Dispatch Team", "dispatch@southatlantic.com")
    ]
    for comp_name, cont_name, dest_email in default_customers:
        cursor.execute("SELECT COUNT(*) as cnt FROM Customer WHERE LOWER(company_name) = LOWER(?)", (comp_name,))
        if cursor.fetchone()["cnt"] == 0:
            cursor.execute(
                "INSERT INTO Customer (company_name, contact_name, destination_email) VALUES (?, ?, ?)",
                (comp_name, cont_name, dest_email)
            )

    # Fetch customer IDs by company name for accurate seeding
    cust_map = {}
    for r in cursor.execute("SELECT customer_id, company_name FROM Customer").fetchall():
        cust_map[r["company_name"]] = r["customer_id"]

    default_vessels = [
        # Prototype vessel (Slides 3-8)
        ("MV Atlantic Star", "9387421", cust_map.get("TransMar Maritime Agency", 1)),
        # MVP Specification Test Case CT07 & Section 11 vessel
        ("Atlantic Star", "9876543", cust_map.get("TransMar Logística Global", 2)),
        # Classroom Reference Sheet & English Test Package vessel (CUST-001 / VSL-001)
        ("MV Aurora Meridian", "9312341", cust_map.get("OceanBridge Logistics Ltd.", 3)),
        # Additional demo vessel
        ("MV Southern Cross", "9456123", cust_map.get("Oceanic Global Lines", 4))
    ]
    for v_name, v_imo, c_id in default_vessels:
        cursor.execute("SELECT COUNT(*) as cnt FROM Vessel WHERE imo = ?", (v_imo,))
        if cursor.fetchone()["cnt"] == 0:
            cursor.execute(
                "INSERT INTO Vessel (vessel_name, imo, customer_id) VALUES (?, ?, ?)",
                (v_name, v_imo, c_id)
            )

    conn.commit()
    conn.close()


def authenticate_user(login_identifier: str, password: str):
    """Authenticates a user by email, username, or full name + password."""
    ident = (login_identifier or "").strip().lower()
    pwd = (password or "").strip()
    if not ident or not pwd:
        return None

    conn = get_connection()
    row = conn.execute("""
        SELECT user_id, name, role, email, username, password
        FROM User
        WHERE LOWER(email) = ? OR LOWER(username) = ? OR LOWER(name) = ?
        LIMIT 1
    """, (ident, ident, ident)).fetchone()

    if not row:
        conn.close()
        return None

    stored_password = row["password"] or ""
    try:
        valid_password = check_password_hash(stored_password, pwd)
    except (ValueError, TypeError):
        valid_password = False

    # One-time compatibility upgrade for legacy plaintext records.
    if not valid_password and stored_password == pwd:
        valid_password = True
        conn.execute(
            "UPDATE User SET password = ? WHERE user_id = ?",
            (generate_password_hash(pwd), row["user_id"])
        )
        conn.commit()

    if not valid_password:
        conn.close()
        return None

    user = {key: row[key] for key in ("user_id", "name", "role", "email", "username")}
    conn.close()
    return user


def find_vessel_by_imo(imo: str):
    """RN01 / BR01: Main lookup by exact 7-digit IMO number."""
    if not imo:
        return None
    clean_imo = imo.strip()
    conn = get_connection()
    row = conn.execute("""
        SELECT v.vessel_id, v.vessel_name, v.imo, v.customer_id,
               c.company_name, c.contact_name, c.destination_email
        FROM Vessel v
        JOIN Customer c ON v.customer_id = c.customer_id
        WHERE v.imo = ?
    """, (clean_imo,)).fetchone()
    conn.close()
    return dict(row) if row else None


def search_vessels_by_name(name_query: str):
    """RN02 / BR02 / RF04 / CT09: Auxiliary search by vessel name (requires human confirmation)."""
    if not name_query or name_query in ("[Não informado]", "Não identificado", "-"):
        return []
    clean_q = name_query.strip()
    conn = get_connection()
    rows = conn.execute("""
        SELECT v.vessel_id, v.vessel_name, v.imo, v.customer_id,
               c.company_name, c.contact_name, c.destination_email
        FROM Vessel v
        JOIN Customer c ON v.customer_id = c.customer_id
        WHERE LOWER(v.vessel_name) LIKE LOWER(?)
           OR LOWER(?) LIKE '%' || LOWER(v.vessel_name) || '%'
    """, (f"%{clean_q}%", clean_q)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_all_vessels():
    conn = get_connection()
    rows = conn.execute("""
        SELECT v.vessel_id, v.vessel_name, v.imo, v.customer_id,
               c.company_name, c.contact_name, c.destination_email
        FROM Vessel v
        JOIN Customer c ON v.customer_id = c.customer_id
        ORDER BY v.vessel_name ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_all_customers():
    conn = get_connection()
    rows = conn.execute("""
        SELECT customer_id, company_name, contact_name, destination_email
        FROM Customer
        ORDER BY company_name ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_all_users():
    conn = get_connection()
    rows = conn.execute("""
        SELECT user_id, name, role, email, username
        FROM User
        ORDER BY user_id ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_default_user():
    conn = get_connection()
    row = conn.execute("SELECT user_id, name, role, email, username FROM User ORDER BY user_id ASC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else {"user_id": 1, "name": "Vitor Cabral", "role": "Operador", "email": "vitor@sigecar.com.br", "username": "vitor"}


def create_vessel(vessel_name: str, imo: str, customer_id: int):
    """
    BR12 / BR13 / Validation Rules:
    - Vessel.imo must be exact 7 numeric digits and UNIQUE.
    - Vessel.customer_id must reference an existing customer.
    """
    clean_name = (vessel_name or "").strip()
    clean_imo = (imo or "").strip()

    if not clean_name:
        raise ValueError("O nome da embarcação é obrigatório.")

    if not (len(clean_imo) == 7 and clean_imo.isdigit()):
        raise ValueError("Erro: o número IMO deve conter exatamente 7 dígitos numéricos.")

    conn = get_connection()
    try:
        cust = conn.execute("SELECT customer_id FROM Customer WHERE customer_id = ?", (customer_id,)).fetchone()
        if not cust:
            raise ValueError("Erro: o cliente selecionado não existe no banco de dados.")

        existing = conn.execute("SELECT vessel_id, vessel_name FROM Vessel WHERE imo = ?", (clean_imo,)).fetchone()
        if existing:
            raise ValueError(f"Erro: o número IMO {clean_imo} já está cadastrado para a embarcação '{existing['vessel_name']}' (IMO duplicado bloqueado).")

        cursor = conn.execute(
            "INSERT INTO Vessel (vessel_name, imo, customer_id) VALUES (?, ?, ?)",
            (clean_name, clean_imo, int(customer_id))
        )
        vessel_id = cursor.lastrowid
        conn.commit()

        row = conn.execute("""
            SELECT v.vessel_id, v.vessel_name, v.imo, v.customer_id,
                   c.company_name, c.contact_name, c.destination_email
            FROM Vessel v
            JOIN Customer c ON v.customer_id = c.customer_id
            WHERE v.vessel_id = ?
        """, (vessel_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def save_permanent_vessel_link(vessel_name: str, imo: str, customer_id: int, vessel_id: int = None):
    """
    BR09 / RN09 / RF11 / CT12:
    Creates or updates the permanent link between a vessel and a customer upon operator confirmation.
    """
    conn = get_connection()
    try:
        clean_imo = (imo or "").strip()
        clean_name = (vessel_name or "").strip()

        if vessel_id:
            conn.execute(
                "UPDATE Vessel SET customer_id = ?, vessel_name = COALESCE(NULLIF(?, ''), vessel_name) WHERE vessel_id = ?",
                (int(customer_id), clean_name, int(vessel_id))
            )
            conn.commit()
            target_id = int(vessel_id)
        elif len(clean_imo) == 7 and clean_imo.isdigit():
            existing = conn.execute("SELECT vessel_id FROM Vessel WHERE imo = ?", (clean_imo,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE Vessel SET customer_id = ?, vessel_name = COALESCE(NULLIF(?, ''), vessel_name) WHERE vessel_id = ?",
                    (int(customer_id), clean_name, existing["vessel_id"])
                )
                target_id = existing["vessel_id"]
            else:
                cursor = conn.execute(
                    "INSERT INTO Vessel (vessel_name, imo, customer_id) VALUES (?, ?, ?)",
                    (clean_name or f"Embarcação IMO {clean_imo}", clean_imo, int(customer_id))
                )
                target_id = cursor.lastrowid
            conn.commit()
        else:
            raise ValueError("Para salvar o vínculo permanentemente, informe um IMO válido de 7 dígitos numéricos.")

        row = conn.execute("""
            SELECT v.vessel_id, v.vessel_name, v.imo, v.customer_id,
                   c.company_name, c.contact_name, c.destination_email
            FROM Vessel v
            JOIN Customer c ON v.customer_id = c.customer_id
            WHERE v.vessel_id = ?
        """, (target_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def create_pdf_processing(original_file_name: str, extracted_data: dict, vessel_id=None, customer_id=None, status="Aguardando Revisão"):
    """
    Creates a record in PDF_Processing.
    Allowed statuses (Section 13): 'Aguardando Revisão', 'Aprovado', 'Falha'.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO PDF_Processing (original_file_name, received_at, extracted_data_json, vessel_id, customer_id, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        original_file_name,
        now_str,
        json.dumps(extracted_data, ensure_ascii=False),
        int(vessel_id) if vessel_id else None,
        int(customer_id) if customer_id else None,
        status
    ))
    processing_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return processing_id, now_str


def update_pdf_processing(processing_id: int, extracted_data: dict, vessel_id=None, customer_id=None, status="Aguardando Revisão"):
    conn = get_connection()
    conn.execute("""
        UPDATE PDF_Processing
        SET extracted_data_json = ?,
            vessel_id = ?,
            customer_id = ?,
            status = ?
        WHERE processing_id = ?
    """, (
        json.dumps(extracted_data, ensure_ascii=False),
        int(vessel_id) if vessel_id else None,
        int(customer_id) if customer_id else None,
        status,
        int(processing_id)
    ))
    conn.commit()
    conn.close()


def get_pdf_processing(processing_id: int):
    conn = get_connection()
    row = conn.execute("""
        SELECT p.*,
               v.vessel_name as db_vessel_name, v.imo as db_imo,
               c.company_name as db_company_name, c.contact_name as db_contact_name, c.destination_email as db_destination_email
        FROM PDF_Processing p
        LEFT JOIN Vessel v ON p.vessel_id = v.vessel_id
        LEFT JOIN Customer c ON p.customer_id = c.customer_id
        WHERE p.processing_id = ?
    """, (int(processing_id),)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["extracted_data"] = json.loads(d["extracted_data_json"]) if d.get("extracted_data_json") else {}
    return d


def create_email_report(processing_id: int, destination_email: str, email_subject: str, email_body: str, approving_user_id: int = 1):
    """
    BR07 / BR08 / BR10 / BR14 / RF09 / RF10 / CT15:
    Records the final approval and simulated email report.
    Email_Report.processing_id is UNIQUE (1:0..1 relationship).
    """
    if not destination_email or not destination_email.strip():
        raise ValueError("O e-mail de destino é obrigatório para registrar a aprovação.")
    if not email_subject or not email_subject.strip():
        raise ValueError("O assunto do e-mail é obrigatório.")
    if not email_body or not email_body.strip():
        raise ValueError("O corpo da mensagem é obrigatório.")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT email_report_id FROM Email_Report WHERE processing_id = ?",
            (int(processing_id),)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE Email_Report
                SET destination_email = ?,
                    email_subject = ?,
                    email_body = ?,
                    approving_user_id = ?,
                    approval_date = ?
                WHERE processing_id = ?
            """, (
                destination_email.strip(),
                email_subject.strip(),
                email_body,
                int(approving_user_id),
                now_str,
                int(processing_id)
            ))
            report_id = existing["email_report_id"]
        else:
            cursor = conn.execute("""
                INSERT INTO Email_Report (processing_id, destination_email, email_subject, email_body, approving_user_id, approval_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                int(processing_id),
                destination_email.strip(),
                email_subject.strip(),
                email_body,
                int(approving_user_id),
                now_str
            ))
            report_id = cursor.lastrowid

        conn.execute(
            "UPDATE PDF_Processing SET status = 'Aprovado' WHERE processing_id = ?",
            (int(processing_id),)
        )
        conn.commit()

        row = conn.execute("""
            SELECT er.*, u.name as approving_user_name, u.role as approving_user_role,
                   p.original_file_name, p.received_at, p.status as processing_status,
                   p.extracted_data_json,
                   v.vessel_name, v.imo,
                   c.company_name
            FROM Email_Report er
            JOIN User u ON er.approving_user_id = u.user_id
            JOIN PDF_Processing p ON er.processing_id = p.processing_id
            LEFT JOIN Vessel v ON p.vessel_id = v.vessel_id
            LEFT JOIN Customer c ON p.customer_id = c.customer_id
            WHERE er.email_report_id = ?
        """, (report_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_approval_history():
    """CT16 / RN10: Retrieve history of approved communications and processing records."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT er.email_report_id, er.processing_id, er.destination_email,
               er.email_subject, er.email_body, er.approval_date,
               u.name as approving_user_name, u.role as approving_user_role,
               p.original_file_name, p.received_at, p.status, p.extracted_data_json,
               v.vessel_name as db_vessel_name, v.imo as db_imo,
               c.company_name as db_company_name
        FROM Email_Report er
        JOIN User u ON er.approving_user_id = u.user_id
        JOIN PDF_Processing p ON er.processing_id = p.processing_id
        LEFT JOIN Vessel v ON p.vessel_id = v.vessel_id
        LEFT JOIN Customer c ON p.customer_id = c.customer_id
        ORDER BY er.approval_date DESC, er.email_report_id DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        item = dict(r)
        item["extracted_data"] = json.loads(item["extracted_data_json"]) if item.get("extracted_data_json") else {}
        result.append(item)
    return result
