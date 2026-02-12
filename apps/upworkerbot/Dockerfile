FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /app

COPY apps/upworkerbot/pyproject.toml apps/upworkerbot/README.md apps/upworkerbot/__main__.py ./apps/upworkerbot/

WORKDIR /app/apps/upworkerbot

RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync

COPY apps/upworkerbot/.env.sample ./

ENV PATH="/app/.venv/bin:$PATH"

CMD ["upworkerbot"]
