from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
import logging
import uvicorn

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("almabody")

@app.get("/")
def root():
    return {"status": "ok", "endpoints": {"health": "/health", "say": "POST /say", "did_self": "GET /did/self"}}

@app.get("/health")
def health():
    return {"status": "ok"}

# ===== D-ID CONFIG =====
DID_API_KEY   = (os.getenv("DID_API_KEY") or "").strip()
DID_IMAGE_URL = (os.getenv("DID_IMAGE_URL") or "").strip()
DID_VOICE_ID  = (os.getenv("DID_VOICE_ID") or "pt-PT-FernandaNeural").strip()
DEFAULT_TEXT  = (os.getenv("DEFAULT_TEXT") or "Olá! Sou a Alma. Em que posso ajudar?").strip()
DID_TALKS_URL = "https://api.d-id.com/talks?wait=true"

def infer_scheme(key: str) -> str:
    """Devolve o esquema preferido a partir do valor guardado."""
    if not key:
        return ""
    low = key.lower()
    if low.startswith("basic "):
        return "Basic"
    if low.startswith("bearer "):
        return "Bearer"
    # sem prefixo → muitos tenants aceitam 'Basic', alguns pedem 'Bearer'
    return "Basic"

def header_for(key: str, scheme: str) -> str:
    """Constrói o header Authorization com o esquema pretendido."""
    if not key:
        return ""
    low = key.lower()
    if low.startswith("basic ") or low.startswith("bearer "):
        # já vem com prefixo, respeita-o
        return key
    return f"{scheme} {key}"

def post_did(url: str, json: dict, scheme: str):
    """Faz POST ao D-ID com o esquema pedido."""
    hdr = {
        "Authorization": header_for(DID_API_KEY, scheme),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return requests.post(url, headers=hdr, json=json, timeout=40)

@app.get("/did/self")
def did_self():
    """Teste simples de auth: deve devolver 200 com info da conta."""
    if not DID_API_KEY:
        return {"ok": False, "reason": "Falta DID_API_KEY"}
    scheme = infer_scheme(DID_API_KEY)
    try:
        r = requests.get(
            "https://api.d-id.com/self",
            headers={"Authorization": header_for(DID_API_KEY, scheme), "Accept": "application/json"},
            timeout=15,
        )
        return {"status": r.status_code, "body": r.text[:800], "scheme_used": scheme}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/say")
async def say(request: Request):
    """
    POST /say
    body: { "text": "...", "image_url"?: "...", "voice_id"?: "pt-PT-FernandaNeural" }
    devolve: { "video_url": "...", "raw": {...} }  ou { "error": "...", "status": ... }
    """
    data = await request.json()
    text = (data.get("text") or DEFAULT_TEXT).strip()
    image_url = (data.get("image_url") or DID_IMAGE_URL).strip()
    voice_id = (data.get("voice_id") or DID_VOICE_ID).strip()

    if not DID_API_KEY:
        return {"error": "Falta DID_API_KEY nas variáveis do Railway", "status": 500}
    if not image_url:
        return {"error": "Falta DID_IMAGE_URL (variável ou no body)", "status": 400}

    payload = {
        "script": {
            "type": "text",
            "input": text,
            "provider": {"type": "microsoft", "voice_id": voice_id}
        },
        "source_url": image_url
    }

    # 1ª tentativa com o esquema inferido; se 401, tenta o alternativo
    first = infer_scheme(DID_API_KEY) or "Basic"
    fallback = "Bearer" if first == "Basic" else "Basic"

    for scheme in (first, fallback):
        try:
            r = post_did(DID_TALKS_URL, payload, scheme)
            log.info(f"[D-ID:{scheme}] status={r.status_code} body={r.text[:200]}")
            if r.status_code == 401:
                continue  # tenta com o outro esquema
            r.raise_for_status()
            resp = r.json()
            return {"video_url": resp.get("result_url"), "raw": resp, "scheme_used": scheme}
        except requests.HTTPError as e:
            # Erro diferente de 401 → devolve logo
            return {"error": f"D-ID HTTP {r.status_code}", "body": r.text, "scheme_used": scheme, "status": r.status_code}
        except Exception as e:
            return {"error": str(e), "scheme_used": scheme, "status": 500}

    # se caiu aqui é porque ambas tentativas deram 401
    return {"error": "D-ID 401 em ambos esquemas (Basic/Bearer). Verifica a tua chave.", "status": 401}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
