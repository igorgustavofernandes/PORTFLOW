# SIGECAR — Making a Shipping Agent's Day Easier

Protótipo funcional web SaaS desenvolvido em **Python (Flask + SQLite + pypdf)** para automação inteligente da leitura de boletins operacionais portuários em PDF e geração padronizada de atualizações por e-mail sob controle do agente marítimo, com **Sistema de Login e Rastreabilidade por Operador**.

---

## Como Executar

### Opção 1: Clique Duplo (Windows)
Dê dois cliques no arquivo `iniciar_sigecar.bat` (ou `iniciar_portflow.bat`) ou execute no terminal:

```powershell
cd C:\Users\lealt\.gemini\antigravity\scratch\portflow
python app.py
```

Em seguida, acesse no navegador (Google Chrome):
- **http://127.0.0.1:5000**

---

## Credenciais de Acesso (Tela de Login)

| Perfil | E-mail ou Usuário | Senha |
| :--- | :--- | :--- |
| **Vitor Cabral (Operador)** | `vitor@sigecar.com.br` ou `vitor` | `123456` |
| **Igor (Operador)** | `igor@sigecar.com.br` ou `igor` | `123456` |
| **Julia (Operadora)** | `julia@sigecar.com.br` ou `julia` | `123456` |
| **Nicolly (Operadora)** | `nicolly@sigecar.com.br` ou `nicolly` | `123456` |
| **Maria (Operadora)** | `maria@sigecar.com.br` ou `maria` | `123456` |
| **Thales (Operador)** | `thales@sigecar.com.br` ou `thales` | `123456` |
| **Administrador SIGECAR (Supervisor)** | `admin@sigecar.com.br` ou `admin` | `123456` |

*(A tela de login também possui botões de preenchimento rápido em 1 clique para facilitar a demonstração).*

---

## Estrutura do Projeto

- `app.py` — Servidor web Flask, autenticação de sessão (`/api/login`, `/api/logout`) e API REST das 6 etapas operacionais (`Upload`, `Extração`, `Revisão`, `Cadastro Manual`, `Geração de E-mail`, `Aprovação e Histórico`).
- `database.py` — Camada de persistência SQLite (`portflow.db`) seguindo o Diagrama Entidade-Relacionamento (`User`, `Customer`, `Vessel`, `PDF_Processing`, `Email_Report`).
- `extractor.py` — Motor de validação (`RF01`, `RNF01`, `RNF03`) e extração por âncoras (`Embarcação:`, `IMO:`, `Viagem:`, `Porto:`, `Berço:`, `Status:`, `ETA:`, `ETB:`, `ETC:`, `ETD:`, `Carga:`, `Observações:`).
- `generate_sample_pdfs.py` — Gerador automático dos arquivos PDF de demonstração na pasta `sample_pdfs/` para apresentação no *Tech Shark Tank* e validação dos cenários `CT01` a `CT17`.
- `test_portflow.py` — Suíte automatizada de testes cobrindo autenticação e todos os 17 cenários de aceitação (`CT01`–`CT17`).
- `templates/index.html`, `static/style.css`, `static/app.js` — Interface web SIGECAR fiel ao Design System oficial (`#11273D`, `#19364F`, `#178B91`, `#F5F8FA`, `#289469`, `#BE8026`, `#BE4C4C`).
