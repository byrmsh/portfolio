FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /app

COPY apps/collector/pyproject.toml apps/collector/README.md ./apps/collector/
COPY packages/schema-py ./packages/schema-py

WORKDIR /app/apps/collector

RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync

COPY apps/collector/*.py ./
COPY apps/collector/.env.sample ./

ENV PATH="/app/.venv/bin:$PATH"

CMD ["collector-github"]
