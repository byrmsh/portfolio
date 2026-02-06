FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /app

COPY apps/upworker/pyproject.toml apps/upworker/README.md ./apps/upworker/
COPY packages/schema-py ./packages/schema-py

WORKDIR /app/apps/upworker

RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync

COPY apps/upworker/__main__.py apps/upworker/typex.py apps/upworker/job-search.gql apps/upworker/__init__.py ./
COPY apps/upworker/schema.py ./
COPY apps/upworker/.env.sample ./

ENV PATH="/app/.venv/bin:$PATH"

CMD ["upworker"]
