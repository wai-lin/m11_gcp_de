FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ARG UV_PYTHON_DOWNLOADS=never

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=${UV_PYTHON_DOWNLOADS}

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

COPY . ./

CMD ["uv", "run", "main.py"]