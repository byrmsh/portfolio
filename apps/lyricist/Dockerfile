FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.10.0

WORKDIR /app

COPY packages/schema-py ./packages/schema-py
COPY packages/common-py ./packages/common-py
COPY apps/lyricist/pyproject.toml apps/lyricist/uv.lock apps/lyricist/README.md ./apps/lyricist/
COPY apps/lyricist/*.py ./apps/lyricist/

WORKDIR /app/apps/lyricist

RUN uv sync --frozen

ENV PATH="/app/apps/lyricist/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser
USER appuser
CMD ["lyricist"]
