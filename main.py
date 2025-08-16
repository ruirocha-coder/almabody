from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
import logging
import uvicorn

# ── App & CORS ────────────────────────────────────────────────────────────────
app = FastAPI(title="almabody")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         # afina depois para o teu domínio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Logs ─────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("almabody")

# ── ENV ──────────────────────────────────────────────────────────────────────
# DID_API_KEY: cola A TUA CHAVE CRUA (sem "Basic")
DID_API_KEY   = (os.getenv("DID_API_KEY") or "").strip()
DID_IMAGE_URL = (os.getenv("DID_IMAGE_URL") or "").strip()  # URL RAW público da imagem
DID_VOICE_ID  = (os.getenv("DID_VOICE_ID")  or "pt-PT-FernandaNeural").strip()
DEFAULT_TEXT  = (os.getenv("DEFAULT_TEXT")  or "Olá! Sou a Alma. Em que posso ajudar?").strip()

DID_TALKS_URL = "https://api.d-id.com/talks?wait=true"  # wait=true → devolve já com video pronto

def auth_header():
    """Monta Authorization header no formato exigido pela D-ID."""
    if not DID_API_KEY:
        return None
    # A D-ID espera "Authorization: Basic <API_KEY>"
    if DID_API_KEY.lower().startswith("basic "):
        return DID_API_KEY
    return f"Basic {DID_API_KEY}"

# ── Rotas ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "ok": True,
        "message": "Alma D-ID API online",
        "endpoints": {
            "health": "/health",
            "say": "POST /say  { text, image_url?, voice_id? }"
        }
    }

@app.get("/health")
def health():
    has_all = bool(DID_API_KEY and DID_IMAGE_URL and DID_VOICE_ID)
    return {"ok": has_all, "missing": [k for k,v in {
        "DID_API_KEY": DID_API_KEY,
        "DID_IMAGE_URL": DID_IMAGE_URL,
        "DID_VOICE_ID": DID_VOICE_ID,
    }.items() if not v]}

@app.post("/say")
async def say(request: Request):
    """
    Body JSON:
      {
        "text": "frase a falar",
        "image_url": "opcional (se quiseres override)",
        "voice_id": "opcional (ex. pt-PT-FernandaNeural)"
      }
    Resposta:
      { "ok": true, "video_url": "https://...", "raw": {...} }
    """
    # Validar envs
    if not DID_API_KEY:
        return {"ok": False, "error": "Falta DID_API_KEY nas Variables do Railway."}
    if not DID_IMAGE_URL:
        return {"ok": False, "error": "Falta DID_IMAGE_URL (link RAW público da imagem)."}
    if not DID_VOICE_ID:
        return {"ok": False, "error": "Falta DID_VOICE_ID (ex.: pt-PT-FernandaNeural)."}

    # Ler body
    try:
        body = await request.json()
    except Exception:
        body = {}

    text      = (body.get("text") or DEFAULT_TEXT or "").strip()
    image_url = (body.get("image_url") or DID_IMAGE_URL).strip()
    voice_id  = (body.get("voice_id")  or DID_VOICE_ID).strip()

    if not text:
        return {"ok": False, "error": "Falta 'text' no body e DEFAULT_TEXT está vazio."}

    # Payload no formato recomendado (script + voice fora do script)
    payload = {
        "source_url": image_url,
        "script": {
            "type": "text",
            "input": text
        },
        "voice": {
            "provider": "microsoft",
            "voice_id": voice_id
        },
        # "config": { "stitch": True }  # opcional
    }

    headers = {
        "Authorization": auth_header(),
        "Content-Type": "application/json"
    }
    if not headers["Authorization"]:
        return {"ok": False, "error": "DID_API_KEY inválida."}

    try:
        res = requests.post(DID_TALKS_URL, headers=headers, json=payload, timeout=90)
        status = res.status_code
        try:
            data = res.json()
        except Exception:
            data = {"_raw_text": res.text}

        log.info(f"[D-ID] status={status} body={str(data)[:400]}")

        if status == 401:
            return {
                "ok": False,
                "error": "D-ID 401 Unauthorized. Confirma a key e que o header é Authorization: Basic <KEY>.",
                "raw": data
            }
        if status == 400:
            # Erros de validação (ex.: "'script' is required")
            return {"ok": False, "error": "D-ID 400 ValidationError", "raw": data}
        if not res.ok:
            return {"ok": False, "error": f"D-ID error {status}", "raw": data}

        # D-ID pode responder com 'result_url', 'video', 'video_url'
        video_url = data.get("result_url") or data.get("video") or data.get("video_url")
        if not video_url:
            return {"ok": False, "error": "Resposta sem video_url/result_url", "raw": data}

        return {"ok": True, "video_url": video_url, "raw": data}

    except Exception as e:
        log.exception("Erro no /say")
        return {"ok": False, "error": f"Falha ao criar talk: {e}"}

# ── Local run (dev) ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
