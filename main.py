from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os, requests, logging

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("alma")

XAI_API_KEY   = os.getenv("XAI_API_KEY")
DID_API_KEY   = os.getenv("DID_API_KEY")
DID_IMAGE_URL = os.getenv("DID_IMAGE_URL")
DID_VOICE_ID  = os.getenv("DID_VOICE_ID", "Bella")

XAI_URL       = "https://api.x.ai/v1/chat/completions"
DID_TALKS_URL = "https://api.d-id.com/talks"

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/say")
async def say(req: Request):
    body = await req.json()
    user_text = (body.get("text") or "").strip()
    image_url = (body.get("image_url") or DID_IMAGE_URL or "").strip()
    voice_id  = (body.get("voice_id")  or DID_VOICE_ID).strip()

    if not user_text:
        return {"error": "Falta 'text'."}
    if not XAI_API_KEY:
        return {"error": "Falta XAI_API_KEY nas Variables."}
    if not DID_API_KEY:
        return {"error": "Falta DID_API_KEY nas Variables."}
    if not image_url:
        return {"error": "Falta DID_IMAGE_URL (env) ou 'image_url' no body."}

    # 1) Grok-4 → texto em pt-PT
    g_headers = {"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"}
    g_payload = {
        "model": "grok-4-0709",
        "messages": [
            {"role": "system", "content": "És a Alma (psicoestético). Responde claro e em pt-PT."},
            {"role": "user", "content": user_text}
        ]
    }
    g = requests.post(XAI_URL, headers=g_headers, json=g_payload, timeout=40)
    log.info(f"[xAI] status={g.status_code} body[:160]={g.text[:160]}")
    g.raise_for_status()
    answer = g.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip() or "Sem resposta."

    # 2) D-ID Talks → vídeo com o rosto a falar
    auth = DID_API_KEY if DID_API_KEY.startswith("Bearer ") else f"Bearer {DID_API_KEY}"
    d_headers = {"Authorization": auth, "Content-Type": "application/json"}
    d_payload = {
        "source_url": image_url,
        "script": {"type": "text", "input": answer, "voice_id": voice_id},
        "config": {"stitch": True}
    }
    d = requests.post(DID_TALKS_URL, headers=d_headers, json=d_payload, timeout=90)
    log.info(f"[DID] status={d.status_code} body[:160]={d.text[:160]}")
    d.raise_for_status()
    dj = d.json()
    video_url = dj.get("result_url") or dj.get("url") or dj.get("video_url")

    return {"answer": answer, "video_url": video_url}

@app.get("/")
def root():
    return {
        "ok": True,
        "message": "Alma D-ID API online",
        "endpoints": {
            "health": "/health",
            "talk": "POST /say  { text, image_url?, voice_id? }"
        }
    }


