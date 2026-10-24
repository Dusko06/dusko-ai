# Dusko AI Prospector

A lightweight commercial prospecting assistant powered by the ScrapeGraphAI API. It extracts public business information from user-provided websites, scores opportunities, and exports structured results.

## Features
- Extract company name, public contact details, services, location, and commercial signals from supplied URLs.
- Qualify prospects against a user-defined offer.
- Batch processing with basic request limits.
- Export results as JSON/CSV.
- API key stored only in environment variables.

## Requirements
- Python 3.11+
- ScrapeGraphAI API key

## Run locally

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # Windows; on macOS/Linux use: cp .env.example .env
# Set SGAI_API_KEY in .env, then:
uvicorn app:app --reload
```

Open `http://127.0.0.1:8000/docs` to test the API.

## API
- `GET /health`
- `POST /api/prospect` — extract and qualify one business website.
- `POST /api/batch` — process a small list of website URLs.

## Important
Never commit `.env` or API keys. ScrapeGraphAI usage may consume paid credits; check your plan before batch runs. Use the tool only on publicly accessible pages and respect applicable laws, site terms, robots rules, and privacy requirements. Results require human verification before outreach.

## Status
Starter implementation. Add your ScrapeGraphAI key locally before running; no key is stored in this repository.