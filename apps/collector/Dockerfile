FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /app

COPY packages/schema-py ./packages/schema-py
COPY packages/common-py ./packages/common-py
COPY apps/collector/pyproject.toml apps/collector/uv.lock apps/collector/README.md ./apps/collector/
COPY apps/collector/*.py apps/collector/.env.sample ./apps/collector/

WORKDIR /app/apps/collector

RUN uv sync --frozen

ENV PATH="/app/apps/collector/.venv/bin:$PATH"

RUN addgroup --system --gid 1000 appuser && adduser --system --uid 1000 --ingroup appuser appuser
USER appuser
CMD ["collector-github"]
