import io
import json
import os
import tempfile
from pathlib import Path

# Keep automated tests isolated from the developer's real database and sample PDFs.
_TEST_TEMP_DIR = tempfile.TemporaryDirectory(prefix="portflow-tests-")
_TEST_DATA_DIR = Path(_TEST_TEMP_DIR.name)
os.environ["PORTFLOW_DB_PATH"] = str(_TEST_DATA_DIR / "portflow.db")
os.environ["PORTFLOW_SAMPLE_DIR"] = str(_TEST_DATA_DIR / "sample_pdfs")

import app as portflow_app
import database
import extractor
import generate_sample_pdfs


def run_all_tests():
    # Use a deterministic password only inside the automated test environment.
    os.environ["PORTFLOW_DEFAULT_PASSWORD"] = "123456"

    # Reset DB for clean test run
    if database.DB_PATH.exists():
        database.DB_PATH.unlink()
    database.init_db()
    generate_sample_pdfs.generate_all_samples()

    client = portflow_app.app.test_client()
    sample_dir = generate_sample_pdfs.SAMPLE_DIR

    print("=== EXECUTANDO CENARIOS DE TESTE SIGECAR (LOGIN + CT01 a CT17) ===")

    # AUTH01: Login com credenciais inválidas -> Rejeitado (401)
    res = client.post("/api/login", json={"username": "vitor@sigecar.com.br", "password": "wrongpassword"})
    assert res.status_code == 401 and res.get_json()["ok"] is False
    print("[PASS] AUTH01 - Login com senha incorreta -> Acesso bloqueado (401)")

    # AUTH02: Login com todos os 7 usuários da equipe (vitor, admin, igor, julia, nicolly, maria, thales)
    for uname in ["vitor", "admin", "igor", "julia", "nicolly", "maria", "thales"]:
        res = client.post("/api/login", json={"username": uname, "password": "123456"})
        assert res.status_code == 200 and res.get_json()["ok"] is True, f"Falha no login de {uname}"
    # Re-login as Vitor Cabral for CT15/CT16 assertions
    res = client.post("/api/login", json={"username": "vitor@sigecar.com.br", "password": "123456"})
    assert res.status_code == 200 and res.get_json()["user"]["name"] == "Vitor Cabral"
    print("[PASS] AUTH02 - Login validado para todos os 7 usuarios (Vitor, Admin, Igor, Julia, Nicolly, Maria, Thales)")

    # CT01: Importar PDF válido de até 5 MB -> Arquivo aceito
    res = client.post("/api/upload", data={"sample_name": "BOLETIM_ATLANTIC_STAR_1911.pdf"})
    assert res.status_code == 200 and res.get_json()["ok"] is True
    print("[PASS] CT01 - Importar PDF valido de ate 5 MB -> Arquivo aceito")

    # CT02: Importar arquivo TXT -> Arquivo rejeitado
    res = client.post("/api/upload", data={"sample_name": "ARQUIVO_INVALIDO_CT02.txt"})
    assert res.status_code == 400 and res.get_json()["error_code"] == "CT02_INVALID_FORMAT"
    print("[PASS] CT02 - Importar arquivo TXT -> Arquivo rejeitado")

    # CT03: Importar PDF acima de 5 MB -> Arquivo rejeitado
    oversized_bytes = b"%PDF-1.4\n" + (b"0" * (5 * 1024 * 1024 + 100))
    ok, err = extractor.validate_and_read_pdf("BIG_FILE.pdf", oversized_bytes)
    assert ok is False and err["error_code"] == "CT03_SIZE_EXCEEDED"
    print("[PASS] CT03 - Importar PDF acima de 5 MB -> Arquivo rejeitado")

    # CT04: Importar PDF corrompido -> Aviso de falha
    res = client.post("/api/upload", data={"sample_name": "BOLETIM_CORROMPIDO_CT04.pdf"})
    assert res.status_code == 400 and res.get_json()["error_code"] == "CT04_CORRUPTED_PDF"
    print("[PASS] CT04 - Importar PDF corrompido -> Aviso de falha")

    # CT05: Importar PDF sem texto selecionável -> Aviso de falha
    res = client.post("/api/upload", data={"sample_name": "BOLETIM_SEM_TEXTO_CT05.pdf"})
    assert res.status_code == 400 and res.get_json()["error_code"] == "CT05_NO_SELECTABLE_TEXT"
    print("[PASS] CT05 - Importar PDF sem texto selecionavel -> Aviso de falha")

    # CT06 & CT07: Extrair PDF completo & Consultar IMO 9876543 -> Campos apresentados + Embarcação e cliente localizados
    res = client.post("/api/upload", data={"sample_name": "BOLETIM_COMPLETO_9876543.pdf"})
    data = res.get_json()
    assert data["ok"] is True
    assert data["extraction"]["summary"]["found"] == 12
    assert data["imo_match"]["imo"] == "9876543"
    assert "TransMar" in data["imo_match"]["company_name"]
    print("[PASS] CT06 & CT07 - Extrair PDF completo e consultar IMO 9876543 -> Embarcacao e cliente localizados")

    # CT08: Consultar IMO 1111111 -> Cadastro não encontrado
    res = client.post("/api/upload", data={"sample_name": "BOLETIM_IMO_NAO_CADASTRADO_1111111.pdf"})
    data_unreg = res.get_json()
    assert data_unreg["ok"] is True
    assert data_unreg["imo_match"] is None
    unreg_proc_id = data_unreg["processing_id"]
    print("[PASS] CT08 - Consultar IMO 1111111 -> Cadastro nao encontrado")

    # CT09: Buscar embarcação pelo nome -> Sugestão apresentada para confirmação
    res = client.post("/api/upload", data={"sample_name": "BOLETIM_BUSCA_POR_NOME_CT09.pdf"})
    data_name = res.get_json()
    assert data_name["ok"] is True
    assert data_name["imo_match"] is None
    assert len(data_name["name_suggestions"]) > 0
    print("[PASS] CT09 - Buscar embarcacao pelo nome -> Sugestao apresentada para confirmacao")

    # CT10: Processar PDF com campo ausente -> Campo indicado como não informado
    res = client.post("/api/upload", data={"sample_name": "BOLETIM_ATLANTIC_STAR_1911.pdf"})
    data_missing = res.get_json()
    assert data_missing["extraction"]["fields"]["etc"] == "[Não informado]"
    print("[PASS] CT10 - Processar PDF com campo ausente -> Campo indicado como [Nao informado]")

    # CT11, CT12, CT13: Vincular manualmente, salvar vínculo permanente e editar informações extraídas
    edited_fields = data_unreg["extraction"]["fields"].copy()
    edited_fields["berth"] = "220"
    res = client.post("/api/review", json={
        "processing_id": unreg_proc_id,
        "fields": edited_fields,
        "vessel_id": None,
        "customer_id": 1,
        "save_permanent": True
    })
    rev_data = res.get_json()
    assert rev_data["ok"] is True
    assert rev_data["permanent_saved"] is True
    assert rev_data["fields"]["berth"] == "220"
    # Verify IMO 1111111 is now permanently available in DB
    assert database.find_vessel_by_imo("1111111") is not None
    print("[PASS] CT11, CT12, CT13 - Vinculacao manual, salvamento permanente e edicao de dados")

    # CT14, CT15, CT16: Editar rascunho, Aprovar comunicação e Consultar histórico de aprovação
    custom_body = rev_data["drafts"]["en"]["body"] + "\n\n[Operator Custom Note Added]"
    res = client.post("/api/approve", json={
        "processing_id": unreg_proc_id,
        "destination_email": rev_data["drafts"]["destination_email"],
        "email_subject": rev_data["drafts"]["en"]["subject"],
        "email_body": custom_body
    })
    app_data = res.get_json()
    assert app_data["ok"] is True
    assert len(app_data["history"]) >= 1
    assert "[Operator Custom Note Added]" in app_data["history"][0]["email_body"]
    assert app_data["history"][0]["approving_user_name"] == "Vitor Cabral"
    print("[PASS] CT14, CT15, CT16, CT17 - Edicao de rascunho, aprovacao humana e historico rastreavel")

    # TEST PACK 01..04 (English Tabular Reports & Fictional Reference Data)
    for eng_pdf in [
        "01_complete_operational_report.pdf",
        "02_report_with_missing_fields.pdf",
        "03_report_with_inconsistencies.pdf",
        "04_reference_data.pdf"
    ]:
        res = client.post("/api/upload", data={"sample_name": eng_pdf})
        d_eng = res.get_json()
        assert res.status_code == 200 and d_eng["ok"] is True, f"Falha em {eng_pdf}: {d_eng}"
        print(f"[PASS] {eng_pdf} -> Extraido com sucesso (Taxa: {d_eng['extraction']['summary']['read_rate']}%, Avisos: {len(d_eng['extraction']['warnings'])})")

    # Re-reset DB to clean demo state (so IMO 1111111 starts unregistered for live presentation demo)
    database.DB_PATH.unlink()
    database.init_db()
    print("=== TODOS OS 17 CENARIOS DE TESTE PASSARAM COM SUCESSO! ===")


if __name__ == "__main__":
    run_all_tests()
