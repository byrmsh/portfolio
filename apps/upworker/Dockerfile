FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /app

COPY apps/upworker/pyproject.toml apps/upworker/uv.lock apps/upworker/README.md ./apps/upworker/
COPY apps/upworker/__main__.py apps/upworker/upworker_app.py apps/upworker/typex.py apps/upworker/job-search.gql apps/upworker/connects-freelancer.gql apps/upworker/__init__.py ./apps/upworker/
COPY apps/upworker/schema.py ./apps/upworker/
COPY packages/schema-py ./packages/schema-py

WORKDIR /app/apps/upworker

ENV UV_PROJECT_ENVIRONMENT="/app/.venv"

RUN uv sync --frozen

COPY apps/upworker/.env.sample ./

ENV PATH="/app/.venv/bin:$PATH"

CMD ["upworker"]
