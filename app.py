import csv
import io
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()
APP_NAME = os.getenv('APP_NAME', 'Dusko AI Prospector')
API_KEY = os.getenv('SGAI_API_KEY', '')
APP_ACCESS_TOKEN = os.getenv('APP_ACCESS_TOKEN', '')
API_BASE = os.getenv('SGAI_API_BASE', 'https://v2-api.scrapegraphai.com/api').rstrip('/')
MAX_BATCH_URLS = max(1, min(int(os.getenv('MAX_BATCH_URLS', '5')), 10))
app = FastAPI(title=APP_NAME, version='0.1.0', description='Prospecting from public business websites.')

class ProspectRequest(BaseModel):
    url: str
    offer: str = Field(..., min_length=3, max_length=1200)
    target_country: str | None = Field(default=None, max_length=100)

class BatchRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=10)
    offer: str = Field(..., min_length=3, max_length=1200)
    target_country: str | None = Field(default=None, max_length=100)

class ProspectResult(BaseModel):
    source_url: str
    offer: str
    result: Any

def require_access_token(x_app_token: str | None = Header(default=None)) -> None:
    if not APP_ACCESS_TOKEN:
        raise HTTPException(status_code=503, detail='App access token is not configured. Set APP_ACCESS_TOKEN in environment secrets.')
    if x_app_token is None or x_app_token != APP_ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail='Missing or invalid X-App-Token header.')

def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise HTTPException(status_code=400, detail='Provide a complete http:// or https:// website URL.')
    host = parsed.hostname.lower()
    if host in {'localhost', '127.0.0.1', '::1'} or host.endswith('.local'):
        raise HTTPException(status_code=400, detail='Local addresses are not allowed.')
    return url

async def scrape_and_qualify(url: str, offer: str, target_country: str | None = None) -> Any:
    if not API_KEY:
        raise HTTPException(status_code=503, detail='ScrapeGraphAI key missing. Set SGAI_API_KEY in .env or deployment secrets.')
    url = validate_public_url(url)
    prompt = ('Analyze this public business website for B2B prospecting. Return JSON fields: company_name, website, country_or_location, business_activity, products_or_services, public_business_email, public_business_phone, public_contact_page, evidence_snippets, fit_score_0_to_100, fit_reasons, uncertainty_or_missing_fields, recommended_next_action. Only use contact details explicitly published for business contact; do not infer personal data. Do not invent missing details. Include source URLs where available. ' + f'Offer/criteria: {offer}. Target country: {target_country or "not specified"}.')
    # Confirm endpoint and request schema against the current ScrapeGraphAI docs before production use.
    endpoint = f'{API_BASE}/extract'
    headers = {'SGAI-APIKEY': API_KEY, 'Content-Type': 'application/json'}
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
            response = await client.post(endpoint, json={'url': url, 'prompt': prompt}, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail='ScrapeGraphAI request timed out.')
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f'Could not reach ScrapeGraphAI: {type(exc).__name__}')
    if response.status_code in (401, 403):
        raise HTTPException(status_code=502, detail='API key or permissions rejected; verify your ScrapeGraphAI account.')
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail='ScrapeGraphAI rate limit or quota reached.')
    if response.is_error:
        raise HTTPException(status_code=502, detail=f'ScrapeGraphAI returned HTTP {response.status_code}: {response.text[:300]}')
    try:
        return response.json()
    except ValueError:
        return {'raw_text': response.text}

@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok', 'app': APP_NAME, 'scrapegraph_key_configured': str(bool(API_KEY)).lower()}

@app.post('/api/prospect', response_model=ProspectResult, dependencies=[__import__('fastapi').Depends(require_access_token)])
async def prospect(request: ProspectRequest) -> ProspectResult:
    return ProspectResult(source_url=request.url, offer=request.offer, result=await scrape_and_qualify(request.url, request.offer, request.target_country))

@app.post('/api/batch', dependencies=[__import__('fastapi').Depends(require_access_token)])
async def batch(request: BatchRequest) -> dict[str, Any]:
    if len(request.urls) > MAX_BATCH_URLS:
        raise HTTPException(status_code=400, detail=f'Batch limited to {MAX_BATCH_URLS} URLs per request.')
    results = []
    for url in request.urls:
        try:
            results.append({'source_url': url, 'result': await scrape_and_qualify(url, request.offer, request.target_country)})
        except HTTPException as exc:
            results.append({'source_url': url, 'error': exc.detail, 'status_code': exc.status_code})
    return {'count': len(results), 'results': results}

@app.post('/api/export-csv', dependencies=[__import__('fastapi').Depends(require_access_token)])
async def export_csv(request: BatchRequest) -> StreamingResponse:
    if len(request.urls) > MAX_BATCH_URLS:
        raise HTTPException(status_code=400, detail=f'Batch limited to {MAX_BATCH_URLS} URLs per request.')
    rows = []
    for url in request.urls:
        try:
            data = await scrape_and_qualify(url, request.offer, request.target_country)
            rows.append({'source_url': url, 'result': str(data) if not isinstance(data, dict) else '', **(data if isinstance(data, dict) else {})})
        except HTTPException as exc:
            rows.append({'source_url': url, 'error': str(exc.detail)})
    output = io.StringIO()
    columns = sorted({key for row in rows for key in row}) or ['source_url']
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename=prospects.csv'})
