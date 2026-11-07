FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface \
    WHISPER_MODEL=small \
    WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE_TYPE=int8 \
    WHISPER_CPU_THREADS=4

WORKDIR /app

RUN useradd --create-home --uid 10001 whisper
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && mkdir -p /models \
    && chown -R whisper:whisper /app /models

COPY --chown=whisper:whisper server.py /app/server.py
USER whisper

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
