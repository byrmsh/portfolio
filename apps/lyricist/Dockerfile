FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv==0.10.0

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY lyricist.py schema.py README.md ./

ENV PYTHONUNBUFFERED=1

CMD ["lyricist"]

