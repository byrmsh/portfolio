FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /app

COPY pyproject.toml README.md ./
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync

COPY __main__.py typex.py job-search.gql __init__.py ./
COPY .env.sample ./

ENV PATH="/app/.venv/bin:$PATH"

CMD ["jobber"]
