import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from faster_whisper import WhisperModel

MAX_AUDIO_BYTES = 25 * 1024 * 1024
MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
MODEL_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", "4"))
MODEL_CACHE = os.getenv("WHISPER_MODEL_CACHE", "/models")
state = {"model": None, "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        state["model"] = WhisperModel(
            MODEL_NAME,
            device=MODEL_DEVICE,
            compute_type=COMPUTE_TYPE,
            cpu_threads=CPU_THREADS,
            download_root=MODEL_CACHE,
        )
        state["error"] = None
    except Exception as exc:
        state["error"] = type(exc).__name__
        raise
    yield
    state["model"] = None


app = FastAPI(title="DOLAN Local Whisper", lifespan=lifespan)


@app.get("/healthz")
def health():
    ready = state["model"] is not None
    return {
        "status": "ready" if ready else "starting",
        "model": MODEL_NAME,
        "device": MODEL_DEVICE,
        "error": state["error"],
    }


@app.post("/v1/audio/transcriptions")
def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="local-whisper"),
    language: str = Form(default="es"),
):
    whisper = state["model"]
    if whisper is None:
        raise HTTPException(status_code=503, detail="El modelo local todavía está cargando.")

    audio = file.file.read(MAX_AUDIO_BYTES + 1)
    if not audio:
        raise HTTPException(status_code=400, detail="El audio está vacío.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="El audio supera el máximo de 25 MB.")

    suffix = Path(file.filename or "dictado.webm").suffix[:12] or ".webm"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="dolan-whisper-", suffix=suffix, delete=False) as temp:
            temp.write(audio)
            temp_path = temp.name

        segments, info = whisper.transcribe(
            temp_path,
            language=(language or "es")[:8],
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        return {
            "text": text,
            "language": info.language,
            "language_probability": info.language_probability,
            "model": MODEL_NAME,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="No se pudo decodificar o transcribir el audio.") from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
