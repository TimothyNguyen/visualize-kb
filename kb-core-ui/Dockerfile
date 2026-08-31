FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY python/pyproject.toml ./python/pyproject.toml
COPY python/kb_core_ui ./python/kb_core_ui
RUN pip install --no-cache-dir "./python[rag]"

# The web bundle is built on the host (`pnpm -C web build`) so the image stays
# Python-only and no FalkorDB or provider configuration can reach a Vite build.
COPY web/dist ./web/dist
COPY deploy ./deploy

RUN useradd --create-home --uid 10001 kbcore \
    && mkdir -p /app/data \
    && chown -R kbcore:kbcore /app/data
USER kbcore

EXPOSE 8420

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8420/api/stats', timeout=3)"

CMD ["kb-core-ui", "serve", "/app/data", \
     "--host", "0.0.0.0", "--port", "8420", "--open=false", \
     "--web-dir", "/app/web/dist"]
