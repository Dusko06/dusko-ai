import csv
import io
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse, HTMLResponse
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


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dusko AI Prospector</title>
<style>
:root{font-family:system-ui,sans-serif;color:#172033;background:#f4f6fa}body{max-width:760px;margin:36px auto;padding:0 16px}
main{background:white;border:1px solid #e2e7f0;border-radius:16px;padding:24px;box-shadow:0 8px 30px #1720330b}
h1{margin-top:0}label{display:block;font-weight:600;margin:16px 0 6px}
input,textarea{width:100%;box-sizing:border-box;padding:12px;border:1px solid #c8d0de;border-radius:8px;font:inherit}
button{margin-top:18px;padding:12px 18px;border:0;border-radius:8px;background:#203d75;color:white;font-weight:700}
small{color:#526078}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6fa;padding:14px;border-radius:8px}
</style></head><body><main><h1>Dusko AI Prospector</h1>
<p>Analyse un site professionnel public et évalue son adéquation avec ton offre commerciale.</p>
<label for="token">Jeton d'accès de l'application</label><input id="token" type="password" autocomplete="off" placeholder="APP_ACCESS_TOKEN">
<label for="url">URL du site à analyser</label><input id="url" type="url" placeholder="https://exemple.fr" required>
<label for="offer">Ton offre ou les critères du prospect</label><textarea id="offer" rows="4" placeholder="Ex. : Je propose des travaux de rénovation aux agences immobilières des Alpes-Maritimes." required></textarea>
<label for="country">Pays ciblé (facultatif)</label><input id="country" placeholder="France">
<button id="run">Analyser le site</button><p id="status" role="status"></p><pre id="result" hidden></pre>
<small>Les analyses peuvent consommer des crédits ScrapeGraphAI. Vérifie les résultats avant toute prospection.</small>
</main><script>
const btn=document.getElementById('run'), status=document.getElementById('status'), out=document.getElementById('result');
btn.addEventListener('click',async()=>{const token=document.getElementById('token').value.trim(),url=document.getElementById('url').value.trim(),offer=document.getElementById('offer').value.trim(),country=document.getElementById('country').value.trim();if(!token||!url||!offer){status.textContent='Renseigne le jeton, une URL et ton offre.';return;}btn.disabled=true;status.textContent='Analyse en cours…';out.hidden=true;try{const r=await fetch('/api/prospect',{method:'POST',headers:{'Content-Type':'application/json','X-App-Token':token},body:JSON.stringify({url,offer,target_country:country||null})});const data=await r.json();if(!r.ok)throw new Error(data.detail||('Erreur HTTP '+r.status));out.textContent=JSON.stringify(data,null,2);out.hidden=false;status.textContent='Analyse terminée.';}catch(e){status.textContent='Échec : '+e.message;}finally{btn.disabled=false;}});
</script></body></html>"""

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
