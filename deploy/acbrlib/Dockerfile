# Worker ACBrLib NFe (Console MT) — Debian, não Alpine.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ACBR_LIB_SO=/opt/acbrlib/Linux/CONSOLE-MT/libacbrnfe64.so \
    ACBR_LIB_SCHEMAS=/opt/acbrlib/Schemas/NFe \
    ACBR_LIB_SERVICOS=/opt/acbrlib/ACBrNFeServicos.ini \
    OPENSSL_CONF=/opt/acbrlib/openssl-legacy.cnf \
    LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu

WORKDIR /opt/worker

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    libssl3 \
    libxml2 \
    ca-certificates \
    curl \
    && ln -sf /usr/lib/x86_64-linux-gnu/libxml2.so.2 /usr/lib/x86_64-linux-gnu/libxml2.so \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/acbrlib/requirements.txt /opt/worker/requirements.txt
RUN pip install --upgrade pip && pip install -r /opt/worker/requirements.txt

COPY vendor/acbrlib /opt/acbrlib
COPY deploy/acbrlib/worker.py /opt/worker/worker.py

RUN mkdir -p /var/acbrlib/work /var/acbrlib/out \
    && chmod +x /opt/acbrlib/Linux/CONSOLE-MT/libacbrnfe64.so || true

EXPOSE 8091

HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=20s \
    CMD curl -f http://127.0.0.1:8091/health || exit 1

CMD ["gunicorn", "worker:app", "--bind", "0.0.0.0:8091", "--workers", "1", "--threads", "1", "--timeout", "180"]
