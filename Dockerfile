FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY . /app
RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "python", "src/main.py"]
