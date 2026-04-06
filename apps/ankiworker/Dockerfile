FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /app

COPY packages/schema-py ./packages/schema-py
COPY packages/common-py ./packages/common-py
COPY apps/ankiworker/pyproject.toml apps/ankiworker/uv.lock apps/ankiworker/README.md ./apps/ankiworker/
COPY apps/ankiworker/*.py apps/ankiworker/.env.sample ./apps/ankiworker/

WORKDIR /app/apps/ankiworker

RUN uv sync --frozen

ENV PATH="/app/apps/ankiworker/.venv/bin:$PATH"

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser
USER appuser
CMD ["ankiworker-activity"]
