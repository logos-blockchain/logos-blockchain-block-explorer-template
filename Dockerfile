FROM python:3.14-slim

# Project files
COPY . /app
WORKDIR /app

# Environment variables
ENV PYTHONPATH=/app:/app/src
ENV UV_INSTALL_DIR=/usr/local/bin

# Package manager and dependencies
# RUN apt-get update && apt-get install -y curl git
RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y curl git
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN uv pip compile pyproject.toml -o requirements.txt && uv pip install --system -r requirements.txt

# Ports
EXPOSE 8000

# Start application
CMD ["python", "/app/src/main.py"]
