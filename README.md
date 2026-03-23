# ContAI PRO

ContAI PRO is an advanced, AI-powered accounting intelligence platform designed to automate financial reconciliation, document parsing, and Chart of Accounts (Plano de Contas) management. By utilizing strict semantical AI models (OpenAI GPT-4o-mini), ContAI transforms raw and unstructured financial records into standardized accounting data.

## Features

* Automated Financial Reconciliation: Intelligent matching of bank statements against accounting firm records.
* AI-Powered Document Parsing: Dynamic extraction of data from PDF and Excel files, interpreting misaligned columns and complex chronological histories without rigid templates.
* Auto-Classification Engine: Batch processing capabilities for suggesting and confirming Chart of Account alignments for hundreds of records instantly.
* Robust Database Architecture: Built on Supabase (PostgreSQL) ensuring referential integrity, preventing null constraints, and handling UPSERTs for deduplication.
* Premium UI/UX: Custom-built asynchronous tracking modals avoiding blocking browser states, styled consistently with a dark and gold high-contrast theme.

## Tech Stack

* Backend: Python 3, Flask
* Database: Supabase (PostgreSQL), Supabase Python Client
* AI Engine: OpenAI API (gpt-4o-mini), Langchain
* Frontend: HTML5, CSS3, Vanilla JavaScript, Lucide Icons
* Containerization: Docker, Docker Compose

## Installation and Setup

### 1. Requirements

* Docker and Docker Compose
* Python 3.11+
* OpenAI API Key
* Supabase Account / Database Credentials

### 2. Environment Variables

Create a `.env` file in the root directory and populate it with the appropriate credentials:

```
OPENAI_API_KEY=your_openai_api_key
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_api_key
FLASK_APP=app.main
FLASK_ENV=development
```

### 3. Running with Docker (Recommended)

Navigate to the `docker` directory and start the stack:

```bash
cd docker
docker-compose up -d --build
```

The application will be accessible at `http://localhost:5000`.

### 4. Running Locally without Docker

Install the dependencies:

```bash
pip install -r requirements.txt
```

Run the Flask application:

```bash
flask run --host=0.0.0.0 --port=5000
```

## System Architecture

The project follows a clean architectural pattern:

* `app/application/`: Contains the core application services such as PDF parsing, Excel parsing, and AI-driven classification logic.
* `app/domain/`: Contains the conceptual models and rules for the system application.
* `app/infrastructure/`: Connects the application to external services (Supabase adapter, OpenAI adapters, decorators).
* `app/web/`: The Flask routes, controllers, and presentation layer (Jinja2 templates, CSS, JS).

## Development and QA

For quality assurance, a test file generator is provided to create synchronized PDF extracts and Excel accounting files for immediate reconciliation testing.

Execute the following inside the container shell to generate localized test files:

```bash
python /app/app/generate_test_files.py
```

## Maintenance

Ensure all system packages remain aligned with the configurations defined in `requirements.txt`. Frequent audits should be made to verify AI mapping stability logic, particularly against potential hallucination edges in the GPT parameters.
