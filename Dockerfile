FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS build

# pycairo and pyaudio only ship sdists on linux.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config libcairo2-dev portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs libs
COPY clients/websocket-rpi-matrix/pyproject.toml clients/websocket-rpi-matrix/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-install-project


FROM python:3.13-slim-trixie AS app

# fonts-noto-color-emoji: render_emoji() asks cairo for "Apple Color Emoji" and fontconfig falls back to this.
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 libportaudio2 fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1000 -d /app di \
    && install -d -o di /app

WORKDIR /app
# discore writes its font cache inside the package, so the venv must be writable.
COPY --from=build --chown=di /app/.venv .venv
COPY web web
COPY assets assets
COPY disinfo disinfo

ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER di
# Fetch the downloaded fonts (unifont) now, not on every container start.
RUN python -c 'import disinfo.fonts'
EXPOSE 4200
CMD ["uvicorn", "disinfo.web.server:app", "--host", "0.0.0.0", "--port", "4200"]


# Everything in one container with the sample config: docker run -p 4200:4200 ...:demo
FROM app AS demo
USER root
RUN apt-get update && apt-get install -y --no-install-recommends redis-server \
    && rm -rf /var/lib/apt/lists/*
COPY --chown=di .config.sample.json .config.json
COPY config/demo.sh /usr/local/bin/demo
USER di
CMD ["demo"]
