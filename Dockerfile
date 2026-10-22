# Dev image for converting this repo onto the OpenSpiel / playtest layout.
# The project tree is bind-mounted at /workspace, so dependencies live in
# /opt/venv and are not hidden by that mount.
#
# Build:  docker build -t saattue-dev .
# Attach: docker exec -it saattue-dev bash

FROM python:3.12-slim-bookworm

# OpenSpiel wheels sometimes need a compiler and BLAS headers.
# sudo is available so an attached agent can install extra packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        git \
        gfortran \
        libopenblas-dev \
        procps \
        ripgrep \
        sudo \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

# Toolchain stays outside the bind-mounted workspace.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:/home/dev/.local/bin:${PATH}"

RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python \
        "open-spiel>=1.6.0" \
        "numpy>=1.26" \
        "matplotlib>=3.11.2" \
        "fastapi>=0.143.0" \
        "uvicorn>=0.54.0" \
        "pytest>=8.0"

ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} dev \
    && useradd -m -u ${UID} -g ${GID} -s /bin/bash dev \
    && echo "dev ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/dev \
    && chmod 0440 /etc/sudoers.d/dev \
    && chown -R dev:dev /opt/venv /home/dev

USER dev
ENV HOME=/home/dev

# Cursor agent CLI, so conversion work can be run from an attached shell.
RUN curl -fsSL https://cursor.com/install | bash \
    && git config --global --add safe.directory /workspace \
    && git config --global --add safe.directory /reference/consume-space

USER root
RUN printf '%s\n' \
        'export VIRTUAL_ENV=/opt/venv' \
        'export PATH="/opt/venv/bin:/home/dev/.local/bin:$PATH"' \
        > /etc/profile.d/saattue-venv.sh \
    && chmod 644 /etc/profile.d/saattue-venv.sh
USER dev

WORKDIR /workspace

# Stay up for `docker exec` / attach. Override to run the playtest server later.
EXPOSE 8765
CMD ["sleep", "infinity"]
