from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
import logging
import uvicorn

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restringe ao teu domínio se quiseres
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("almabody")

# ── ENV ───────────────────────────────────────────────────────────────────────
DID_API_KEY   = os.getenv("DID_API_KEY", "").strip()        # ex: key_********************************
DID_IMAGE_URL = os.getenv("DID_IMAGE_URL", "").strip()      # ex: https://raw.githubusercontent.com/USER/repo/main/avatar.png
DID_VOICE_ID  = os.getenv("DID_VOICE_ID", "pt-PT-FernandaNeural").strip()  # voz MS (Português)
# (Opcional) se quiseres passar texto default quando não vem nada
DEFAULT_TEXT  = os.getenv("DEFAULT_TEXT", "Olá! Sou a Alma, especialista em design de interiores com o método psicoestético. Em que posso ajudar?")

DID_TALKS_URL = "https://api.d-id.com/talks?wait=true"  # espera o processamento e devolve o vídeo pronto

# ── Health ───────────────────────────────────────────────────────────────────
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
    return {"ok": True}

# ── POST /say → cria vídeo na D-ID a partir de texto ─────────────────────────
@app.post("/say")
async def say(request: Request):
    """
    Body esperado (JSON):
    {
      "text": "frase para falar",
      "image_url": "override opcional",
      "voice_id": "override opcional (ex: pt-PT-FernandaNeural)"
    }
    Resposta:
    {
      "ok": true,
      "video_url": "...",
      "talk_id": "...",
      "raw": {...}  # debug
    }
    """
    if not DID_API_KEY:
        return {"ok": False, "error": "Falta DID_API_KEY nas Variables do Railway."}

    try:
        body = await request.json()
    except Exception:
        body = {}

    text      = (body.get("text") or DEFAULT_TEXT or "").strip()
    image_url = (body.get("image_url") or DID_IMAGE_URL or "").strip()
    voice_id  = (body.get("voice_id")  or DID_VOICE_ID or "pt-PT-FernandaNeural").strip()

    if not text:
        return {"ok": False, "error": "Falta 'text' no body e não há DEFAULT_TEXT definido."}

    if not image_url:
        return {"ok": False, "error": "Falta 'image_url' e a variável DID_IMAGE_URL não está definida."}

    # Payload EXACTO que a D-ID espera
    payload = {
        "source_url": image_url,
        "script": {
            "type": "text",
            "subtitles": "false",
            "provider": {
                "type": "microsoft",
                "voice_id": voice_id
            },
            "input": text
        }
    }

    headers = {
        "Authorization": f"Basic {DID_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        res = requests.post(DID_TALKS_URL, headers=headers, json=payload, timeout=90)
        status = res.status_code
        data = {}
        try:
            data = res.json()
        except Exception:
            pass

        log.info(f"[D-ID] status={status} body={str(data)[:400]}")

        # Erros típicos
        if status == 401:
            return {
                "ok": False,
                "error": "D-ID 401 Unauthorized: verifica DID_API_KEY (copiada sem espaços/aspas) e o cabeçalho Authorization: Basic <API_KEY>.",
                "raw": data
            }
        if status == 400:
            return {
                "ok": False,
                "error": f"D-ID 400 ValidationError: {data}",
                "raw": data
            }
        if not res.ok:
            return {
                "ok": False,
                "error": f"D-ID error {status}",
                "raw": data
            }

        # Resposta de sucesso da D-ID (quando ?wait=true) traz result_url / video / assets
        # Em APIs recentes, costuma vir "result_url"; noutros, "video".
        video_url = data.get("result_url") or data.get("video") or data.get("video_url")

        if not video_url:
            # fallback para quando devolvem 'id' e assets em nested; devolvemos raw para debug
            return {
                "ok": False,
                "error": "Resposta sem video_url/result_url. Vê 'raw' para o payload devolvido pela D-ID.",
                "raw": data
            }

        return {
            "ok": True,
            "video_url": video_url,
            "talk_id": data.get("id"),
            "raw": data
        }

    except Exception as e:
        log.exception("Erro ao chamar a D-ID")
        return {"ok": False, "error": f"Falha a criar talk: {e}"}

# ── Local run (opcional) ─────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
