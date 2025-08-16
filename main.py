from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os, requests, logging

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("almabody")

DID_API_KEY  = os.getenv("DID_API_KEY")    # tem de começar por "Basic "
DID_IMAGE_URL= os.getenv("DID_IMAGE_URL")  # imagem pública (raw github, CDN, etc.)
DID_VOICE_ID = os.getenv("DID_VOICE_ID")   # ex: pt-PT-FranciscaNeural

@app.get("/health")
def health():
    ok = all([DID_API_KEY, DID_IMAGE_URL, DID_VOICE_ID])
    return {"ok": ok}

@app.post("/say")
async def say(request: Request):
    try:
        data = await request.json()
        text = (data or {}).get("text", "").strip()
        if not text:
            return {"error": "Falta o campo 'text' no JSON."}

        # valida envs
        missing = [k for k,v in {
            "DID_API_KEY": DID_API_KEY,
            "DID_IMAGE_URL": DID_IMAGE_URL,
            "DID_VOICE_ID": DID_VOICE_ID,
        }.items() if not v]
        if missing:
            return {"error": f"Variáveis em falta: {', '.join(missing)}"}

        if not DID_API_KEY.startswith("Basic "):
            return {"error": "DID_API_KEY deve começar por 'Basic ' (com espaço)."}

        headers = {
            "Authorization": DID_API_KEY,
            "Content-Type": "application/json",
        }

        payload = {
            "source_url": DID_IMAGE_URL,     # retrato
            "script": {
                "type": "text",
                "input": text
            },
            # provider de voz Microsoft + PT-PT
            "audio": {
                "provider": "microsoft",
                "voice_id": DID_VOICE_ID
            },
            # configurar saída mp4
            "config": {
                "result_format": "mp4",
                "stitch": True,         # juntar áudio e vídeo
                "fluent": True,
                "pad_audio": 0.0
            }
        }

        url = "https://api.d-id.com/talks"
        log.info(f"[D-ID] POST {url} text='{text[:80]}'...")
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        log.info(f"[D-ID] status={r.status_code} body={r.text[:400]}")

        # A API pode devolver 201 ou 200. Parseamos e devolvemos um vídeo URL se existir.
        if r.status_code >= 400:
            return {"error": f"D-ID error {r.status_code}", "body": r.text}

        j = {}
        try:
            j = r.json()
        except Exception:
            # fallback, se vier texto cru
            return {"error": "Resposta não-JSON da D-ID", "body": r.text}

        # Alguns planos devolvem diretamente 'result_url'/'video_url'; outros devolvem o 'id' para polling.
        # Tratamos os casos mais comuns:
        video_url = j.get("result_url") or j.get("video_url")

        if not video_url:
            # às vezes vem só um 'id' e é preciso pollar /talks/{id}
            talk_id = j.get("id")
            if talk_id:
                poll_url = f"https://api.d-id.com/talks/{talk_id}"
                for _ in range(20):  # ~20s
                    pr = requests.get(poll_url, headers=headers, timeout=10)
                    log.info(f"[D-ID] poll {poll_url} -> {pr.status_code}")
                    pj = pr.json()
                    video_url = pj.get("result_url") or pj.get("video_url")
                    if video_url:
                        break
                if not video_url:
                    return {"error": "Sem video_url após polling", "raw": pj}
            else:
                return {"error": "Resposta sem video_url e sem id", "raw": j}

        return {"video_url": video_url}

    except Exception as e:
        log.exception("Erro no /say")
        return {"error": f"Exceção no /say: {e}"}
