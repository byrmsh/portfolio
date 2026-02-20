# Social Card Generation (`og-image.jpg`)

This project uses a dedicated social preview image for link embeds (Open Graph / Twitter), separate from the favicon.

## Output file

- `apps/web/public/og-image.jpg` (`1200x630`)

## Design

Terminal-window card: macOS-style chrome, `~ whois bayram.sh` → name/title, then
`~ git log --all --oneline -2` → the two most recent commits (hash highlighted in blue).

## How it gets regenerated

**In CI** (`build-images.yml`): both `build-amd64` and `build-arm64` jobs run
`apps/web/scripts/gen-og-image.py` with the live `git log` output before the
`docker/build-push-action` step (only for the `web` matrix target). The freshly
generated image is then baked into the Docker image via the normal `COPY . .`
in the Dockerfile.

**Locally / manually**:

```bash
# From repo root — prerequisites: Python 3, Pillow, IBM Plex fonts
pip install pillow
# apt install fonts-ibm-plex   (Debian/Ubuntu)

python3 apps/web/scripts/gen-og-image.py \
  "$(git log --all --oneline -2 | head -1)" \
  "$(git log --all --oneline -2 | tail -1)"
```

The script (`apps/web/scripts/gen-og-image.py`) also accepts the log lines via
the `GIT_LOG_LINES` environment variable (newline-separated) or falls back to
built-in placeholder text when called with no arguments.

## Layout wiring

`apps/web/src/layouts/Layout.astro` references this image through:

- `meta[property="og:image"]`
- `meta[name="twitter:image"]`
