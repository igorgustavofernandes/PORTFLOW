# PORTFLOW

**Intelligent Document Processing and Operational Workflow for Maritime Agencies**

PORTFLOW is a functional web prototype developed to streamline the processing of operational PDF documents in maritime agencies. The prototype is branded as **SIGECAR** in its user interface.

## About the project

Maritime agents receive operational documents containing information about vessel movements, cargo operations, interruptions and schedules. Reviewing these documents and preparing client updates manually can be time-consuming and susceptible to human error.

PORTFLOW supports the upload and processing of operational PDFs, information review, manual data registration, preparation of standardized email reports, approval and historical tracking.

## Key features

- PDF upload and validation.
- Extraction of operational information from PDF documents.
- Review and correction of extracted data.
- Manual registration of operational information.
- Preparation of standardized operational email reports.
- Approval workflow and history.
- Operator identification and traceability.

## Technologies

| Technology | Purpose |
|---|---|
| Python | Backend logic |
| Flask | Web framework and API |
| SQLite | Relational database |
| pypdf | PDF reading and extraction |
| HTML, CSS and JavaScript | Web interface |

See [Technologies](docs/technologies.md) for details.

## Project structure

```text
PORTFLOW/
├── assets/
│   └── screenshots/
├── docs/
│   ├── architecture.md
│   ├── technologies.md
│   ├── team.md
│   └── workflow.md
├── src/
│   ├── static/
│   ├── templates/
│   ├── app.py
│   ├── database.py
│   ├── extractor.py
│   ├── generate_sample_pdfs.py
│   ├── test_portflow.py
│   └── requirements.txt
├── .gitignore
└── README.md
```

## Requirements

- Python 3.10 or newer.
- pip (Python package installer).
- Windows, macOS or Linux.

## Installation and execution

Open a terminal in the repository root and follow these steps.

### 1. Create a virtual environment

**Windows (PowerShell):**

```powershell
cd src
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
cd src
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Start the application

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser. Keep the terminal open while using the application.

On first startup, the application creates a local file named `.first_run_credentials.txt` inside `src/` containing the generated initial password for the demo accounts. This file is ignored by Git and must never be committed. The usernames are `vitor`, `admin`, `igor`, `julia`, `nicolly`, `maria` and `thales`.

To define your own initial demo password before the first run, set the `PORTFLOW_DEFAULT_PASSWORD` environment variable. Existing databases retain their current passwords, which are upgraded to secure password hashes when the application initializes.

For a stable Flask session key, set `PORTFLOW_SECRET_KEY` before starting the application. Example:

**Windows (PowerShell):**

```powershell
$env:PORTFLOW_SECRET_KEY = "replace-with-a-long-random-secret"
```

**macOS / Linux:**

```bash
export PORTFLOW_SECRET_KEY="replace-with-a-long-random-secret"
```

If this variable is not set, a random key is generated for the current run, so active sessions will not survive an application restart. Never commit real secrets to the repository. The `.env.example` file documents the available variables; the application does not automatically load a `.env` file.

## Automated tests

From the `src/` directory, with the virtual environment activated, run:

```bash
python test_portflow.py
```

The test suite covers authentication and the acceptance scenarios CT01–CT17, as well as additional sample PDF cases. Tests reset the local SQLite database; do not run them against a database containing data you need to keep.

## Documentation

- [System Architecture](docs/architecture.md)
- [Operational Workflow](docs/workflow.md)
- [Technologies](docs/technologies.md)
- [Team and Contributions](docs/team.md)

## Screenshots

The application screenshots are available in [assets/screenshots](assets/screenshots/).

## Project presentation

PORTFLOW was developed as part of the Tech Shark Tank challenge at ISULPAR, within the English for Information Systems course. The presentation PDF is not included in the repository at this time.

## Team

See [Team and Contributions](docs/team.md) for the team's roles and contributions.

---

**PORTFLOW — Making a Shipping Agent's Day Easier.**
