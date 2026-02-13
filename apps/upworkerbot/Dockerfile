FROM python:3.12-slim AS runtime

RUN pip install --no-cache-dir uv==0.4.30

WORKDIR /app

COPY apps/upworkerbot/pyproject.toml apps/upworkerbot/uv.lock apps/upworkerbot/README.md apps/upworkerbot/__main__.py apps/upworkerbot/upworkerbot_app.py ./apps/upworkerbot/

WORKDIR /app/apps/upworkerbot

ENV UV_PROJECT_ENVIRONMENT="/app/.venv"

RUN uv sync --frozen

COPY apps/upworkerbot/.env.sample ./

ENV PATH="/app/.venv/bin:$PATH"

# Avoid relying on console-script stubs which can break if entrypoints are mis-generated.
CMD ["python", "-m", "upworkerbot_app"]
