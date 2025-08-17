from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
import logging
import uvicorn

# ── App & CORS ────────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # podes restringir ao teu domínio depois
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Logs ──────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("almabody")

# ── Rotas básicas ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Almabody ativo. Endpoints: /health, /say"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# ── Configuração D-ID ─────────────────────────────────────────────────────────
DID_API_KEY   = os.getenv("DID_API_KEY", "").strip()
DID_IMAGE_URL = os.getenv("DID_IMAGE_URL", "").strip()
DID_VOICE_ID  = os.getenv("DID_VOICE_ID", "pt-PT-FernandaNeural").strip()
DEFAULT_TEXT  = os.getenv("DEFAULT_TEXT", "Olá! Sou a Alma. Em que posso ajudar?").strip()
DID_TALKS_URL = "https://api.d-id.com/talks?wait=true"

def did_auth_header() -> str:
    """
    Prepara o cabeçalho de autorização para a API do D-ID.
    Aceita tanto chaves começadas por 'Basic' como 'Bearer',
    ou só a chave simples (nesse caso assume 'Basic').
    """
    if not DID_API_KEY:
        return ""
    low = DID_API_KEY.lower()
    if low.startswith("basic ") or low.startswith("bearer "):
        return DID_API_KEY
    return f"Basic {DID_API_KEY}"

# ── Rota: gerar vídeo com D-ID ───────────────────────────────────────────────
@app.post("/say")
async def say(request: Request):
    """
    Exemplo: POST /say
    {
        "text": "Olá, bem-vindo!",
        "image_url": "https://meusite.com/alma.png",   (opcional, usa o default)
        "voice_id": "pt-PT-FernandaNeural"             (opcional, usa o default)
    }
    """
    data = await request.json()
    text = data.get("text", DEFAULT_TEXT)
    image_url = data.get("image_url", DID_IMAGE_URL)
    voice_id = data.get("voice_id", DID_VOICE_ID)

    if not DID_API_KEY:
        return {"error": "Falta DID_API_KEY nas variáveis do Railway"}

    if not image_url:
        return {"error": "Falta DID_IMAGE_URL (variável ou no body)"}

    headers = {
        "Authorization": did_auth_header(),
        "Content-Type": "application/json"
    }

    payload = {
        "script": {
            "type": "text",
            "input": text,
            "provider": {"type": "microsoft", "voice_id": voice_id}
        },
        "source_url": image_url
    }

    try:
        r = requests.post(DID_TALKS_URL, headers=headers, json=payload, timeout=40)
        log.info(f"[D-ID] status={r.status_code}, body={r.text[:300]}")
        r.raise_for_status()
        resp = r.json()
        return {
            "video_url": resp.get("result_url", None),
            "raw": resp
        }
    except Exception as e:
        log.exception("Erro ao chamar D-ID /talks")
        return {"error": str(e)}

# ── Local run ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
        
