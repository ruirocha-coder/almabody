from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
import uvicorn

# ── App & CORS ───────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # mais tarde podes restringir ao teu domínio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Variáveis de ambiente ────────────────────────────────────────────────────
DID_API_KEY = os.getenv("DID_API_KEY", "").strip()
DID_IMAGE_URL = os.getenv("DID_IMAGE_URL", "").strip()
DID_VOICE_ID = os.getenv("DID_VOICE_ID", "pt-PT-FernandaNeural").strip()

# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True, "service": "almabody"}

# ── Endpoint SAY (texto → vídeo) ─────────────────────────────────────────────
@app.post("/say")
async def say(request: Request):
    """
    Recebe JSON: { "text": "...", "image_url": "...(opcional)...", "voice_id": "...(opcional)..." }
    Devolve o resultado do POST à API da D-ID.
    """
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        image_url = data.get("image_url", DID_IMAGE_URL)
        voice_id = data.get("voice_id", DID_VOICE_ID)

        if not DID_API_KEY:
            return {"error": "Falta DID_API_KEY nas Variables do Railway."}
        if not text:
            return {"error": "Campo 'text' é obrigatório."}

        headers = {
            "Authorization": f"Bearer {DID_API_KEY}",
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

        res = requests.post("https://api.d-id.com/talks", headers=headers, json=payload, timeout=30)
        return {"status": res.status_code, "body": res.text}

    except Exception as e:
        return {"error": str(e)}

# ── Local run ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
